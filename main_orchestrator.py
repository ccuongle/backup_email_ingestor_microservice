"""
Main Orchestrator
Điều phối toàn bộ workflow của microservice email ingestion
"""
import time
import signal
import sys
from datetime import datetime, timezone
from typing import Optional

from core.session_manager import session_manager, SessionConfig, SessionState, TriggerMode
from core.polling_service import polling_service
from core.webhook_service import webhook_service

class EmailIngestionOrchestrator:
    """Orchestrator điều phối toàn bộ email ingestion workflow"""
    
    def __init__(self):
        self.running = False
        self.current_session_id: Optional[str] = None
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def start_session(
        self,
        polling_mode: TriggerMode = TriggerMode.SCHEDULED,
        polling_interval: int = 300,
        enable_webhook: bool = True
    ) -> bool:
        """Khởi động phiên làm việc mới"""
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
        print("=" * 70)
        
        try:
            # Phase 1: Start session với state phù hợp
            if not session_manager.start_session(config):
                return False
            
            self.current_session_id = session_id
            self.running = True
            
            # Phase 1a: Start webhook service (nếu được enable)
            if enable_webhook:
                print("\n[Orchestrator] Phase 1a: Starting Webhook Service...")
                if not webhook_service.start():
                    print("[Orchestrator] WARNING: Webhook failed to start")
                else:
                    print("[Orchestrator] ✓ Webhook service started")
            else:
                print("\n[Orchestrator] Webhook disabled, skipping...")
            
            # Phase 1b: Start initial polling
            print("\n[Orchestrator] Phase 1b: Starting Initial Polling...")
            if not polling_service.start(mode=polling_mode, interval=polling_interval):
                raise Exception("Failed to start polling service")
            
            print("[Orchestrator] ✓ Polling service started")
            print("\n" + "=" * 70)
            print("[Orchestrator] SESSION ACTIVE")
            print("=" * 70)
            
            # Hiển thị trạng thái phù hợp
            if enable_webhook:
                print("Status: BOTH_ACTIVE (Polling + Webhook)")
                print("Polling will process backlog, then switch to Webhook-only")
            else:
                print("Status: POLLING_ACTIVE (Polling only)")
                print("Running in polling-only mode")
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
        status = session_manager.get_session_status()
        print("\n[Orchestrator] Session Summary:")
        print(f"  Session ID: {status['session_id']}")
        print(f"  Emails Processed: {status['processed_count']}")
        print(f"  Emails Pending: {status['pending_count']}")
        print(f"  Polling Errors: {status['polling_errors']}")
        print(f"  Webhook Errors: {status['webhook_errors']}")
        print("=" * 70)
        
        self.running = False
        self.current_session_id = None
    
    def get_status(self) -> dict:
        """Lấy trạng thái tổng quan"""
        session_status = session_manager.get_session_status()
        polling_status = polling_service.get_status()
        webhook_status = webhook_service.get_status()
        
        return {
            "running": self.running,
            "session": session_status,
            "polling": polling_status,
            "webhook": webhook_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def trigger_manual_poll(self) -> dict:
        """Trigger một lần polling thủ công"""
        if not self.running:
            return {"error": "No active session"}
        
        print("\n[Orchestrator] Manual poll triggered")
        result = polling_service.poll_once()
        return result
    
    def wait_for_session(self):
        """Chờ session chạy (blocking)"""
        if not self.running:
            print("[Orchestrator] No active session to wait for")
            return
        
        print("\n[Orchestrator] Session running. Press CTRL+C to stop.")
        
        try:
            while self.running:
                time.sleep(5)
                
                # Kiểm tra health
                status = self.get_status()
                session_state = SessionState(status['session']['state'])
                
                if session_state == SessionState.TERMINATED:
                    print("[Orchestrator] Session terminated")
                    break
        
        except KeyboardInterrupt:
            print("\n[Orchestrator] Interrupted by user")
            self.stop_session(reason="user_interrupt")
    
    def _cleanup(self):
        """Cleanup tất cả services"""
        print("[Orchestrator] Cleaning up services...")
        
        # Stop polling
        if polling_service.active:
            polling_service.stop()
            print("[Orchestrator] ✓ Polling stopped")
        
        # Stop webhook
        if webhook_service.active:
            webhook_service.stop()
            print("[Orchestrator] ✓ Webhook stopped")
    
    def _signal_handler(self, signum, frame):
        """Handle SIGINT/SIGTERM"""
        print(f"\n[Orchestrator] Received signal {signum}")
        self.stop_session(reason="signal_interrupt")
        sys.exit(0)

# Singleton instance
orchestrator = EmailIngestionOrchestrator()

# ============= CLI Interface =============

def main():
    """CLI interface cho orchestrator"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Email Ingestion Microservice"
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
        "--poll-once",
        action="store_true",
        help="Run one-time polling and exit"
    )
    
    args = parser.parse_args()
    
    # One-time poll mode
    if args.poll_once:
        print("[Orchestrator] One-time polling mode")
        
        # Start minimal session (POLLING_ACTIVE only)
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
        if result['emails_found'] != 0:
            print(f"  Emails Found: {result['emails_found']}")
            print(f"  Successed: {result['success']}")
            print(f"  Failed: {result['failed']}")
            print(f"  Skipped: {result['skipped']}")
        else:
            print(f"  Emails Found: {result['emails_found']}")
        print("=" * 70)
        return
    
    # Normal session mode
    polling_mode = TriggerMode.MANUAL if args.mode == "manual" else TriggerMode.SCHEDULED
    enable_webhook = not args.no_webhook
    
    # Start session
    success = orchestrator.start_session(
        polling_mode=polling_mode,
        polling_interval=args.interval,
        enable_webhook=enable_webhook
    )
    
    if not success:
        print("[Orchestrator] Failed to start session")
        sys.exit(1)
    
    # Wait for session
    orchestrator.wait_for_session()

if __name__ == "__main__":
    main()