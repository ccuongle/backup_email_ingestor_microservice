"""
Main Orchestrator - Updated
Điều phối với Queue + Batch Processing architecture
"""
import time
import signal
import sys
from datetime import datetime, timezone
from typing import Optional

from core.session_manager import session_manager, SessionConfig, SessionState, TriggerMode
from core.polling_service import polling_service
from core.webhook_service import webhook_service
from core.batch_processor import get_batch_processor
from core.queue_manager import get_email_queue


class EmailIngestionOrchestrator:
    """
    Orchestrator với kiến trúc mới:
    Polling/Webhook → Queue → Batch Processor (parallel)
    """
    
    def __init__(self):
        self.running = False
        self.current_session_id: Optional[str] = None
        self.batch_processor = None
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def start_session(
        self,
        polling_mode: TriggerMode = TriggerMode.SCHEDULED,
        polling_interval: int = 300,
        enable_webhook: bool = True,
        batch_size: int = 50,
        max_workers: int = 20
    ) -> bool:
        """
        Khởi động phiên làm việc với batch processing
        
        Args:
            polling_mode: Manual/Scheduled polling
            polling_interval: Polling interval (seconds)
            enable_webhook: Enable webhook notifications
            batch_size: Number of emails per batch
            max_workers: Number of parallel workers
        """
        if self.running:
            print("[Orchestrator] Session already running")
            return False
        
        # Tạo session config
        session_id = f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        config = SessionConfig(
            session_id=session_id,
            start_time=datetime.now(timezone.utc).isoformat(),
            polling_interval=polling_interval,
            webhook_enabled=enable_webhook,
            polling_mode=polling_mode.value
        )
        
        print("=" * 70)
        print("[Orchestrator] STARTING EMAIL INGESTION SESSION")
        print("=" * 70)
        print(f"Session ID: {session_id}")
        print(f"Polling Mode: {polling_mode.value}")
        print(f"Polling Interval: {polling_interval}s ({polling_interval/60:.1f}min)")
        print(f"Webhook Enabled: {enable_webhook}")
        print("-" * 70)
        print(f"Batch Size: {batch_size} emails")
        print(f"Parallel Workers: {max_workers}")
        print(f"Architecture: Polling/Webhook → Queue → Batch Processor")
        print("=" * 70)
        
        try:
            # Phase 0: Start session
            if not session_manager.start_session(config):
                return False
            
            self.current_session_id = session_id
            self.running = True
            
            # Phase 1: Start Batch Processor (CRITICAL - must start first)
            print("\n[Orchestrator] Phase 1: Starting Batch Processor...")
            self.batch_processor = get_batch_processor(
                batch_size=batch_size,
                max_workers=max_workers
            )
            
            if not self.batch_processor.start():
                raise Exception("Failed to start batch processor")
            
            print("[Orchestrator] ✓ Batch Processor started")
            
            # Phase 2: Start Webhook (if enabled)
            if enable_webhook:
                print("\n[Orchestrator] Phase 2: Starting Webhook Service...")
                if not webhook_service.start():
                    print("[Orchestrator] WARNING: Webhook failed to start")
                else:
                    print("[Orchestrator] ✓ Webhook service started")
            else:
                print("\n[Orchestrator] Webhook disabled, skipping...")
            
            # Phase 3: Start Polling
            print("\n[Orchestrator] Phase 3: Performing initial poll to clear backlog...")
            # Chỉ poll 1 lần duy nhất khi khởi động để dọn backlog
            # Polling định kỳ chỉ được kích hoạt khi fallback
            if polling_mode == TriggerMode.SCHEDULED:
                result = polling_service.poll_once()
                print(f"[Orchestrator] ✓ Initial poll complete. Found: {result.get('emails_found', 0)}, Enqueued: {result.get('enqueued', 0)}")
                
                # Nếu có webhook, chuyển sang chế độ webhook-only ngay lập tức
                if enable_webhook:
                    session_manager.complete_initial_polling()
            else:
                print("[Orchestrator] Manual mode: Skipping initial poll.")
            
            # Summary
            print("\n" + "=" * 70)
            print("[Orchestrator] SESSION ACTIVE")
            print("=" * 70)
            
            if enable_webhook:
                print("Status: BOTH_ACTIVE (Polling + Webhook)")
                print("Flow: Initial Poll -> Webhook → Queue → Batch Processor")
            else:
                print("Status: POLLING_ACTIVE (Polling only)")
                print("Flow: Polling → Queue → Batch Processor")
            
            print("=" * 70)
            
            return True
        
        except Exception as e:
            print(f"[Orchestrator] Session start error: {e}")
            self._cleanup()
            return False
    
    def stop_session(self, reason: str = "user_requested"):
        """Dừng phiên làm việc"""
        if not self.running:
            print("[Orchestrator] No active session")
            return
        
        print("\n" + "=" * 70)
        print(f"[Orchestrator] STOPPING SESSION: {reason}")
        print("=" * 70)
        
        # Stop services
        self._cleanup()
        
        # Terminate session
        session_manager.terminate_session(reason)
        
        # Show summary
        status = self.get_status()
        print("\n[Orchestrator] Session Summary:")
        print(f"  Session ID: {status['session']['session_id']}")
        print(f"  Emails Processed: {status['session']['processed_count']}")
        print(f"  Emails Pending: {status['session']['pending_count']}")
        print(f"  Queue Size: {status['queue']['queue_size']}")
        
        if 'batch_processor' in status:
            print(f"  Batches Processed: {status['batch_processor']['batches_processed']}")
            print(f"  Success Rate: {self._calculate_success_rate(status['batch_processor'])}%")
        
        print("=" * 70)
        
        self.running = False
        self.current_session_id = None
    
    def get_status(self) -> dict:
        """Lấy trạng thái tổng quan"""
        session_status = session_manager.get_session_status()
        polling_status = polling_service.get_status()
        webhook_status = webhook_service.get_status()
        
        queue = get_email_queue()
        queue_stats = queue.get_stats()
        
        status = {
            "running": self.running,
            "session": session_status,
            "polling": polling_status,
            "webhook": webhook_status,
            "queue": queue_stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Add batch processor stats if active
        if self.batch_processor and self.batch_processor.active:
            status["batch_processor"] = self.batch_processor.get_stats()
        
        return status
    
    def trigger_manual_poll(self) -> dict:
        """Trigger polling thủ công"""
        if not self.running:
            return {"error": "No active session"}
        
        print("\n[Orchestrator] Manual poll triggered")
        result = polling_service.poll_once()
        
        # Show queue status after poll
        queue_stats = get_email_queue().get_stats()
        result["queue_size_after"] = queue_stats["queue_size"]
        
        return result
    
    def wait_for_session(self):
        """Chờ session chạy (blocking)"""
        if not self.running:
            print("[Orchestrator] No active session to wait for")
            return
        
        print("\n[Orchestrator] Session running. Press CTRL+C to stop.")
        print("[Orchestrator] Monitoring every 10s...\n")
        
        try:
            monitor_interval = 10
            
            while self.running:
                time.sleep(monitor_interval)
                
                # Get status
                status = self.get_status()
                session_state = SessionState(status['session']['state'])
                
                # Print monitoring info
                self._print_monitoring(status)
                
                # Check if terminated
                if session_state == SessionState.TERMINATED:
                    print("[Orchestrator] Session terminated")
                    break
        
        except KeyboardInterrupt:
            print("\n[Orchestrator] Interrupted by user")
            self.stop_session(reason="user_interrupt")
    
    def _print_monitoring(self, status: dict):
        """Print monitoring information"""
        queue = status.get('queue', {})
        batch = status.get('batch_processor', {})
        
        print(f"[Monitor] State: {status['session']['state']}")
        print(f"  Queue: {queue.get('queue_size', 0)} pending, "
              f"{queue.get('processing_size', 0)} processing")
        
        if batch:
            print(f"  Processor: {batch.get('emails_success', 0)} success, "
                  f"{batch.get('emails_failed', 0)} failed")
            
            if batch.get('avg_batch_time', 0) > 0:
                print(f"  Performance: {batch['avg_batch_time']:.2f}s/batch")
    
    def _cleanup(self):
        """Cleanup tất cả services"""
        print("[Orchestrator] Cleaning up services...")
        
        # Stop polling first (stop feeding queue)
        if polling_service.active:
            polling_service.stop()
            print("[Orchestrator] ✓ Polling stopped")
        
        # Stop webhook
        if webhook_service.active:
            webhook_service.stop()
            print("[Orchestrator] ✓ Webhook stopped")
        
        # Let batch processor finish current batch
        if self.batch_processor and self.batch_processor.active:
            print("[Orchestrator] Waiting for batch processor to finish...")
            time.sleep(2)  # Grace period
            self.batch_processor.stop()
            print("[Orchestrator] ✓ Batch Processor stopped")
    
    def _calculate_success_rate(self, batch_stats: dict) -> float:
        """Calculate success rate"""
        success = batch_stats.get('emails_success', 0)
        failed = batch_stats.get('emails_failed', 0)
        total = success + failed
        
        if total == 0:
            return 0.0
        
        return round((success / total) * 100, 1)
    
    def _signal_handler(self, signum, frame):
        """Handle SIGINT/SIGTERM"""
        print(f"\n[Orchestrator] Received signal {signum}")
        self.stop_session(reason="signal_interrupt")
        sys.exit(0)


# Singleton instance
orchestrator = EmailIngestionOrchestrator()


# ============= CLI Interface =============

def main():
    """CLI interface với batch processing options"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Email Ingestion Microservice with Batch Processing"
    )
    
    parser.add_argument(
        "--mode",
        choices=["manual", "scheduled"],
        default="scheduled",
        help="Polling mode: manual or scheduled"
    )
    
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Polling interval in seconds (default: 300)"
    )
    
    parser.add_argument(
        "--no-webhook",
        action="store_true",
        help="Disable webhook, use polling only"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for processing (default: 50)"
    )
    
    parser.add_argument(
        "--workers",
        type=int,
        default=20,
        help="Number of parallel workers (default: 20)"
    )
    
    parser.add_argument(
        "--poll-once",
        action="store_true",
        help="Run one-time polling and exit"
    )
    
    args = parser.parse_args()
    
    # One-time poll mode
    if args.poll_once:
        print("[Orchestrator] One-time polling mode")
        
        mode = TriggerMode.MANUAL
        config = SessionConfig(
            session_id=f"onetime_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            start_time=datetime.now(timezone.utc).isoformat(),
            polling_mode=mode.value,
            webhook_enabled=False,
            polling_interval=0
        )
        
        session_manager.start_session(config)
        result = polling_service.poll_once()
        session_manager.terminate_session("one_time_complete")
        
        print("\n" + "=" * 70)
        print("POLL RESULT:")
        print(f"  Status: {result['status']}")
        print(f"  Emails Found: {result.get('emails_found', 0)}")
        print(f"  Enqueued: {result.get('enqueued', 0)}")
        print(f"  Skipped: {result.get('skipped', 0)}")
        print(f"  Fetch Time: {result.get('fetch_time', 0):.2f}s")
        print(f"  Enqueue Time: {result.get('enqueue_time', 0):.2f}s")
        print("=" * 70)
        return
    
    # Normal session mode
    polling_mode = TriggerMode.MANUAL if args.mode == "manual" else TriggerMode.SCHEDULED
    enable_webhook = not args.no_webhook
    
    # Start session
    success = orchestrator.start_session(
        polling_mode=polling_mode,
        polling_interval=args.interval,
        enable_webhook=enable_webhook,
        batch_size=args.batch_size,
        max_workers=args.workers
    )
    
    if not success:
        print("[Orchestrator] Failed to start session")
        sys.exit(1)
    
    # Wait for session
    orchestrator.wait_for_session()


if __name__ == "__main__":
    main()