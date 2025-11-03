"""
Batch Email Processor
Xử lý email song song với ThreadPoolExecutor
Tối ưu hóa I/O operations
"""
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from datetime import datetime, timezone

from core.queue_manager import get_email_queue
from core.unified_email_processor import EmailProcessor
from core.session_manager import session_manager
from core.token_manager import get_token


class BatchEmailProcessor:
    """
    High-performance batch processor
    Xử lý N emails song song với ThreadPool
    """
    
    def __init__(
    self,
    batch_size: int = 50,
    max_workers: int = 20,
    fetch_interval: float = 2.0,
    email_processor: Optional[EmailProcessor] = None
):
        """
        Args:
            batch_size: Number of emails per batch
            max_workers: Parallel workers
            fetch_interval: Seconds between queue checks
            email_processor: Optional pre-injected EmailProcessor (for testing)
        """
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.fetch_interval = fetch_interval

        self.queue = get_email_queue()
        self.processor = email_processor  # 👈 Không khởi tạo ngay, chỉ lưu nếu test cung cấp
        self.executor: Optional[ThreadPoolExecutor] = None

        self.active = False
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Stats
        self.stats = {
            "batches_processed": 0,
            "emails_success": 0,
            "emails_failed": 0,
            "total_processing_time": 0.0,
            "avg_batch_time": 0.0
        }

    def start(self) -> bool:
        """Start batch processor"""
        if self.active:
            print("[BatchProcessor] Already active")
            return False
        
        print(f"[BatchProcessor] Starting...")
        print(f"  Batch size: {self.batch_size}")
        print(f"  Workers: {self.max_workers}")
        print(f"  Fetch interval: {self.fetch_interval}s")
        
        # Initialize processor
        token = get_token()
        self.processor = EmailProcessor(token)
        
        # Initialize executor
        self.executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="EmailWorker"
        )
        
        # Start processing loop
        self.active = True
        self._stop_event.clear()
        self.thread = threading.Thread(
            target=self._processing_loop,
            daemon=True,
            name="BatchProcessorLoop"
        )
        self.thread.start()
        
        print("[BatchProcessor] Started successfully")
        return True
    
    def stop(self):
        """Stop batch processor"""
        if not self.active:
            return
        
        print("[BatchProcessor] Stopping...")
        self.active = False
        self._stop_event.set()
        
        # Wait for thread
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=10)
        
        # Shutdown executor
        if self.executor:
            self.executor.shutdown(wait=True, cancel_futures=False)
            self.executor = None

        # Close the email processor client
        if self.processor:
            self.processor.close()
        
        print("[BatchProcessor] Stopped")
        self._print_stats()
    
    def _processing_loop(self):
        """Main processing loop"""
        print("[BatchProcessor] Processing loop started")
        
        while self.active and not self._stop_event.is_set():
            try:
                # Check queue stats
                queue_stats = self.queue.get_stats()
                queue_size = queue_stats["queue_size"]
                shutting_down = self._stop_event.is_set()
                
                # Chỉ xử lý khi có đủ 1 batch, hoặc khi đang shutdown và có email tồn
                if queue_size < self.batch_size and not (shutting_down and queue_size > 0):
                    # Chưa đủ batch, đợi
                    time.sleep(self.fetch_interval)
                    continue
                
                if queue_size > 0:
                    print(f"\n[BatchProcessor] Queue size: {queue_size}. Triggering batch processing.")
                
                # Fetch batch
                batch = self.queue.dequeue_batch(self.batch_size)
                
                if not batch:
                    time.sleep(self.fetch_interval)
                    continue
                
                print(f"[BatchProcessor] Processing batch of {len(batch)} emails...")
                
                # Process batch
                batch_start = time.time()
                result = self._process_batch_parallel(batch)
                batch_time = time.time() - batch_start
                
                # Update stats
                self.stats["batches_processed"] += 1
                self.stats["emails_success"] += result["success"]
                self.stats["emails_failed"] += result["failed"]
                self.stats["total_processing_time"] += batch_time
                self.stats["avg_batch_time"] = (
                    self.stats["total_processing_time"] / 
                    self.stats["batches_processed"]
                )
                
                print(f"[BatchProcessor] Batch completed in {batch_time:.2f}s")
                print(f"  Success: {result['success']}")
                print(f"  Failed: {result['failed']}")
                print(f"  Payloads received: {len(result['payloads'])}") # Placeholder for batching
                print(f"  Rate: {len(batch)/batch_time:.1f} emails/s")
                
                # Re-queue timeouts periodically
                if self.stats["batches_processed"] % 10 == 0:
                    self.queue.requeue_timeouts()
                
                # Brief pause before next batch
                time.sleep(0.5)
            
            except Exception as e:
                print(f"[BatchProcessor] Loop error: {e}")
                time.sleep(5)
        
        print("[BatchProcessor] Processing loop stopped")
    
    def _process_batch_parallel(self, batch: List[tuple]) -> Dict:
        """
        Process batch of emails in parallel
        
        Args:
            batch: List of (email_id, email_data)
        
        Returns:
            {"success": int, "failed": int, "payloads": List[Dict]}
        """
        result = {"success": 0, "failed": 0, "payloads": []}
        if not self.executor:
            # Fallback initialization, should be done in start()
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

        futures = {
            self.executor.submit(self._process_single_email, email_id, email_data): email_id
            for email_id, email_data in batch
        }
        
        processed_ids = []
        
        for future in as_completed(futures):
            email_id = futures[future]
            try:
                payload = future.result(timeout=30)
                
                if payload:
                    result["success"] += 1
                    result["payloads"].append(payload)
                    processed_ids.append(email_id)
                else:
                    result["failed"] += 1
                    self.queue.mark_failed(email_id, "Processing failed or returned no payload")
            
            except Exception as e:
                result["failed"] += 1
                self.queue.mark_failed(email_id, str(e))
                print(f"[BatchProcessor] Error processing {email_id}: {e}")
        
        if processed_ids:
            self.queue.mark_processed(processed_ids)
        
        return result
    
    def _process_single_email(self, email_id: str, email_data: Dict) -> Optional[Dict]:
        """
        Process single email (runs in thread pool)
        
        Args:
            email_id: Email ID
            email_data: Email data dict
        
        Returns:
            JSON payload if successful, otherwise None
        """
        try:
            if self.processor is None:
                # This is a fallback, should be initialized in start()
                token = get_token()
                self.processor = EmailProcessor(token)

            # Use the unified processor, which now returns a payload or None
            payload = self.processor.process_email(
                message=email_data,
                source="batch_processor"
            )
            
            return payload
        
        except Exception as e:
            print(f"[BatchProcessor] Email {email_id} error: {e}")
            return None
    
    def get_stats(self) -> Dict:
        """Get processor statistics (with KPI metrics)"""
        total_emails = self.stats["emails_success"] + self.stats["emails_failed"]
        throughput = (
            total_emails / self.stats["total_processing_time"]
            if self.stats["total_processing_time"] > 0 else 0
        )
        success_rate = (
            (self.stats["emails_success"] / total_emails) * 100
            if total_emails > 0 else 0
        )

        base = {
            "active": self.active,
            "batch_size": self.batch_size,
            "max_workers": self.max_workers,
            **self.stats,
            "throughput": round(throughput, 2),
            "success_rate": round(success_rate, 2),
            "queue_stats": self.queue.get_stats()
        }
        return base

    
    def _print_stats(self):
        """Print final statistics & export KPI"""
        print("\n" + "=" * 70)
        print("BATCH PROCESSOR STATISTICS (FINAL KPI)")
        print("=" * 70)
        
        total_emails = self.stats["emails_success"] + self.stats["emails_failed"]
        throughput = (
            total_emails / self.stats["total_processing_time"]
            if self.stats["total_processing_time"] > 0 else 0
        )
        success_rate = (
            (self.stats["emails_success"] / total_emails) * 100
            if total_emails > 0 else 0
        )

        print(f"🧩 Batches Processed : {self.stats['batches_processed']}")
        print(f"✅ Emails Success    : {self.stats['emails_success']}")
        print(f"❌ Emails Failed     : {self.stats['emails_failed']}")
        print(f"⚙️ Avg Batch Time    : {self.stats['avg_batch_time']:.2f}s")
        print(f"🚀 Throughput        : {throughput:.1f} emails/s")
        print(f"🎯 Success Rate      : {success_rate:.1f}%")
        
        print("=" * 70)
        

# Singleton
_batch_processor_instance = None

def get_batch_processor(
    batch_size: int = 50,
    max_workers: int = 20
) -> BatchEmailProcessor:
    """Get singleton BatchEmailProcessor"""
    global _batch_processor_instance
    if _batch_processor_instance is None:
        _batch_processor_instance = BatchEmailProcessor(
            batch_size=batch_size,
            max_workers=max_workers
        )
    return _batch_processor_instance