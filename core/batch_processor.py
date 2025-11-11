"""
Batch Email Processor - Fixed Race Condition
Xử lý email song song với ThreadPoolExecutor
"""
import time
import threading
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional

from core.queue_manager import get_email_queue
from core.unified_email_processor import EmailProcessor
from core.token_manager import get_token
from cache.redis_manager import get_redis_storage
from utils.rabbitmq import RabbitMQConnection


class BatchEmailProcessor:
    """
    High-performance batch processor
    Xử lý N emails song song với ThreadPool
    """
    
    def __init__(
        self,
        batch_size: int = 20,
        max_workers: int = 20,
        fetch_interval: float = 2.0,
        email_processor: Optional[EmailProcessor] = None,
        rabbitmq_manager: Optional[RabbitMQConnection] = None
    ):
        """
        Args:
            batch_size: Number of emails per batch
            max_workers: Parallel workers
            fetch_interval: Seconds between queue checks
            email_processor: Optional pre-injected EmailProcessor (for testing)
            rabbitmq_manager: Optional pre-injected RabbitMQ (for testing)
        """
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.fetch_interval = fetch_interval
        self.queue = get_email_queue()
        self.redis_manager = get_redis_storage()
        self.processor = email_processor 
        self.rabbitmq_manager = rabbitmq_manager or RabbitMQConnection()
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
        
        print("[BatchProcessor] Starting...")
        print(f"  Batch size: {self.batch_size}")
        print(f"  Workers: {self.max_workers}")
        print(f"  Fetch interval: {self.fetch_interval}s")
        
        # Initialize processor
        if self.processor is None:
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
                # ✅ FIX: Get fresh queue stats before dequeue
                queue_stats = self.queue.get_stats()
                queue_size = queue_stats["queue_size"]
                shutting_down = self._stop_event.is_set()
                
                # Process if: queue has enough for a full batch OR (shutting down AND there are emails)
                if queue_size < self.batch_size and not (shutting_down and queue_size > 0):
                    # Not enough for a full batch and not shutting down
                    time.sleep(self.fetch_interval)
                    continue
                
                if queue_size > 0:
                    print(f"\n[BatchProcessor] Queue size: {queue_size}. Triggering batch processing.")
                
                # ✅ FIX: Fetch batch and immediately check if empty
                batch = self.queue.dequeue_batch(self.batch_size)
                
                # ✅ CRITICAL FIX: Check batch after dequeue (race condition fix)
                if not batch:
                    print("[BatchProcessor] Dequeued empty batch (race condition), retrying...")
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
                print(f"  Rate: {len(batch)/batch_time:.1f} emails/s")

                # Re-queue timeouts periodically
                if self.stats["batches_processed"] % 10 == 0:
                    self.queue.requeue_timeouts()
                
                # Brief pause before next batch
                time.sleep(0.5)
            
            except Exception as e:
                print(f"[BatchProcessor] Loop error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(5)
        
        print("[BatchProcessor] Processing loop stopped")
    
    def _process_batch_parallel(self, batch: List[tuple]) -> Dict:
        """
        Process batch of emails in parallel
        
        Args:
            batch: List of (email_id, email_data)
        
        Returns:
            {"success": int, "failed": int}
        """
        # ✅ VALIDATION: Ensure batch is not empty
        if not batch:
            print("[BatchProcessor] WARNING: Empty batch received in parallel processing")
            return {"success": 0, "failed": 0}
        
        result = {"success": 0, "failed": 0}
        
        # ✅ VALIDATION: Ensure executor exists
        if not self.executor:
            print("[BatchProcessor] ERROR: Executor not initialized, reinitializing...")
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
                    # ✅ ADD: Try-catch for RabbitMQ publish
                    try:
                        self.rabbitmq_manager.publish(
                            'email_exchange', 
                            'extracted_data', 
                            json.dumps(payload)
                        )
                    except Exception as pub_error:
                        print(f"[BatchProcessor] WARNING: RabbitMQ publish failed for {email_id}: {pub_error}")
                        # Still mark as processed locally, but log the issue
                    
                    processed_ids.append(email_id)
                else:
                    result["failed"] += 1
                    self.queue.mark_failed(email_id, "Processing failed or returned no payload")
            
            except Exception as e:
                import traceback
                traceback.print_exc()
                result["failed"] += 1
                self.queue.mark_failed(email_id, str(e))
                print(f"[BatchProcessor] Error processing {email_id}: {e}")
        
        # ✅ Mark processed after all futures complete
        if processed_ids:
            try:
                self.queue.mark_processed(processed_ids)
            except Exception as mark_error:
                print(f"[BatchProcessor] WARNING: Failed to mark emails as processed: {mark_error}")
        
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
                print("[BatchProcessor] WARNING: Processor not initialized, creating new instance")
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