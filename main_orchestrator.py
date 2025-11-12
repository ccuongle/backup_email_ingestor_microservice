"""
main_orchestrator.py
Enhanced Orchestrator with proper error state recovery (Story 1.6 AC2-3)
"""
import asyncio
import signal
import sys
import logging
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
        self._shutdown_event = asyncio.Event()
    
    async def start_session(
        self,
        polling_mode: TriggerMode = TriggerMode.SCHEDULED,
        polling_interval: int = 300,
        enable_webhook: bool = True,
        batch_size: int = 20,
        max_workers: int = 20
    ) -> bool:
        """Khởi động phiên làm việc với batch processing"""
        if self.running:
            print("[Orchestrator] Session already running")
            return False
        
        # ✅ NEW: Check and handle error states (Story 1.6 AC2-3)
        current_session_state = session_manager.get_session_status()["state"]
        
        # List of states that require cleanup before starting new session
        error_states = [
            SessionState.FAILED_TO_START.value,
            SessionState.SESSION_ERROR.value,
            SessionState.ERROR.value
        ]
        
        active_states = [
            SessionState.POLLING_ACTIVE.value,
            SessionState.WEBHOOK_ACTIVE.value,
            SessionState.BOTH_ACTIVE.value
        ]
        
        # ✅ Handle error states with recovery
        if current_session_state in error_states:
            print(f"[Orchestrator] Found session in error state: {current_session_state}")
            print("[Orchestrator] Attempting recovery...")
            
            # Get error details for logging
            session_info = session_manager.get_session_status()
            error_reason = session_info.get("failure_reason") or session_info.get("error_details", "unknown")
            print(f"[Orchestrator] Previous error: {error_reason}")
            
            # Attempt recovery
            if not session_manager.recover_from_error(reason="orchestrator_startup_recovery"):
                print("[Orchestrator] ERROR: Recovery failed, cannot start new session")
                return False
            
            print("[Orchestrator] ✓ Recovery successful, proceeding with new session")
            await asyncio.sleep(1)  # Brief pause after recovery
        
        # ✅ Handle active states (need graceful termination)
        elif current_session_state in active_states:
            print(f"[Orchestrator] Found active session ({current_session_state})")
            print("[Orchestrator] Terminating previous session before starting new one...")
            
            # Gracefully terminate active session
            await self._cleanup_previous_session()
            session_manager.terminate_session(reason="previous_session_cleanup")
            await asyncio.sleep(1)
        
        # IDLE and TERMINATED states are OK to start
        
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
        print("Architecture: Polling/Webhook → Queue → Batch Processor")
        print("=" * 70)
        
        try:
            # Phase 0: Start session
            if not session_manager.start_session(config):
                # ✅ Session start failure already sets FAILED_TO_START state
                print("[Orchestrator] ERROR: Failed to start session")
                return False
            
            self.current_session_id = session_id
            self.running = True
            
            # Phase 1: Start Batch Processor
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
                if not await webhook_service.start():
                    print("[Orchestrator] WARNING: Webhook failed to start")
                    # ✅ Don't fail entire session, just log warning
                else:
                    print("[Orchestrator] ✓ Webhook service started")
            else:
                print("\n[Orchestrator] Webhook disabled, skipping...")
            
            # Phase 3: Start Polling
            print("\n[Orchestrator] Phase 3: Performing initial poll to clear backlog...")
            if polling_mode == TriggerMode.SCHEDULED:
                result = await polling_service.poll_once()
                print(f"[Orchestrator] ✓ Initial poll complete. Found: {result.get('emails_found', 0)}, Enqueued: {result.get('enqueued', 0)}")
                
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
            # ✅ Set SESSION_ERROR state before cleanup
            session_manager.set_session_error(str(e), "session_startup")
            await self._cleanup()
            return False
    
    # ✅ NEW METHOD: Cleanup previous session resources
    async def _cleanup_previous_session(self):
        """
        Cleanup resources from previous session.
        Used when terminating error/active sessions before starting new one.
        """
        print("[Orchestrator] Cleaning up previous session resources...")
        
        try:
            # Stop polling if active
            if polling_service.active:
                polling_service.stop()
                print("[Orchestrator] ✓ Stopped previous polling service")
            
            # Stop webhook if active
            if webhook_service.active:
                await webhook_service.stop()
                print("[Orchestrator] ✓ Stopped previous webhook service")
            
            # Stop batch processor if active
            if self.batch_processor and self.batch_processor.active:
                self.batch_processor.stop()
                print("[Orchestrator] ✓ Stopped previous batch processor")
            
            # Brief pause to ensure cleanup completes
            await asyncio.sleep(2)
            
        except Exception as e:
            print(f"[Orchestrator] WARNING: Error during previous session cleanup: {e}")
            # Continue anyway - best effort cleanup
    
    async def stop_session(self, reason: str = "user_requested"):
        """Dừng phiên làm việc"""
        if not self.running:
            print("[Orchestrator] No active session")
            return
        
        print("\n" + "=" * 70)
        print(f"[Orchestrator] STOPPING SESSION: {reason}")
        print("=" * 70)
        
        # Stop services
        await self._cleanup()
        
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
        
        if self.batch_processor and self.batch_processor.active:
            status["batch_processor"] = self.batch_processor.get_stats()
        
        return status
    
    async def trigger_manual_poll(self) -> dict:
        """Trigger polling thủ công"""
        if not self.running:
            return {"error": "No active session"}
        
        print("\n[Orchestrator] Manual poll triggered")
        result = await polling_service.poll_once()
        
        queue_stats = get_email_queue().get_stats()
        result["queue_size_after"] = queue_stats["queue_size"]
        
        return result
    
    async def wait_for_session(self):
        """Chờ session chạy (blocking)"""
        if not self.running:
            print("[Orchestrator] No active session to wait for")
            return
        
        print("\n[Orchestrator] Session running. Press CTRL+C to stop.")
        print("[Orchestrator] Monitoring every 10s...\n")
        
        try:
            monitor_interval = 10
            
            while self.running:
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=monitor_interval
                    )
                    print("[Orchestrator] Shutdown event detected")
                    await self.stop_session(reason="shutdown_requested")
                    break
                except asyncio.TimeoutError:
                    pass
                
                # Get status
                status = self.get_status()
                session_state = SessionState(status['session']['state'])
                
                # Print monitoring info
                self._print_monitoring(status)
                
                # ✅ Check for error states during monitoring
                if session_state in [SessionState.SESSION_ERROR, SessionState.ERROR]:
                    print("\n[Orchestrator] ERROR: Session entered error state during operation")
                    error_details = status['session'].get('error_details', 'unknown')
                    print(f"[Orchestrator] Error details: {error_details}")
                    await self.stop_session(reason="session_error_detected")
                    break
                
                # Check if terminated
                if session_state == SessionState.TERMINATED:
                    print("[Orchestrator] Session terminated")
                    break
        
        except asyncio.CancelledError:
            print("\n[Orchestrator] Wait cancelled")
            await self.stop_session(reason="cancelled")
        except KeyboardInterrupt:
            print("\n[Orchestrator] Keyboard interrupt in wait loop")
            await self.stop_session(reason="keyboard_interrupt")
    
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
    
    async def _cleanup(self):
        """Cleanup tất cả services"""
        print("[Orchestrator] Cleaning up services...")
        
        if polling_service.active:
            polling_service.stop()
            print("[Orchestrator] ✓ Polling stopped")
        
        if webhook_service.active:
            await webhook_service.stop()
            print("[Orchestrator] ✓ Webhook stopped")
        
        if self.batch_processor and self.batch_processor.active:
            print("[Orchestrator] Waiting for batch processor to finish...")
            await asyncio.sleep(2)
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
    
    async def shutdown(self):
        """Graceful shutdown"""
        print("\n[Orchestrator] Initiating graceful shutdown...")
        self._shutdown_event.set()


# Singleton instance
orchestrator = EmailIngestionOrchestrator()


# ============= CLI Interface =============

async def main():
    """CLI interface với async signal handling"""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    # --- Begin Token Check ---
    from cache.redis_manager import get_redis_storage
    from core.get_access_token import get_ms_graph_tokens_interactively
    
    redis_manager = get_redis_storage()
    if not redis_manager.get_access_token(): # Removed await
        logger.info("No valid MS Graph token found. Starting interactive login...")
        access_token, _ = await get_ms_graph_tokens_interactively()
        if not access_token:
            logger.error("Authentication failed or was cancelled. Exiting.")
            sys.exit(1)
        logger.info("Authentication successful. Proceeding with startup...")
    else:
        logger.info("Valid MS Graph token found. Proceeding with startup...")
    # --- End Token Check ---

    import argparse
    import platform
    
    loop = asyncio.get_running_loop()
    
    def signal_handler(sig):
        print(f"\n[Main] Received signal {sig}")
        asyncio.create_task(orchestrator.shutdown())
    
    if platform.system() == 'Windows':
        def windows_signal_handler(sig, frame):
            print(f"\n[Main] Received signal {sig}")
            loop.call_soon_threadsafe(orchestrator._shutdown_event.set)
        
        signal.signal(signal.SIGINT, windows_signal_handler)
        signal.signal(signal.SIGTERM, windows_signal_handler)
    else:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
    
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
        result = await polling_service.poll_once()
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
    success = await orchestrator.start_session(
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
    await orchestrator.wait_for_session()


if __name__ == "__main__":
    import traceback
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Main] Keyboard interrupt received")
    except Exception as e:
        print(f"\n[Main] Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)