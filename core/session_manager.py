"""
core/session_manager.py
Enhanced Session Manager with proper error state handling (Story 1.6)
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict
from dataclasses import dataclass
from cache.redis_manager import get_redis_storage

class SessionState(Enum):
    """Trạng thái phiên làm việc"""
    IDLE = "idle"
    POLLING_ACTIVE = "polling_active"
    WEBHOOK_ACTIVE = "webhook_active"
    BOTH_ACTIVE = "both_active"
    TERMINATED = "terminated"
    FAILED_TO_START = "failed_to_start"
    SESSION_ERROR = "session_error"
    ERROR = "error"

class TriggerMode(Enum):
    """Cơ chế trigger polling"""
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    FALLBACK = "fallback"

@dataclass
class SessionConfig:
    """Cấu hình phiên làm việc"""
    session_id: str
    start_time: str
    polling_interval: int = 300
    webhook_enabled: bool = True
    polling_mode: str = TriggerMode.SCHEDULED.value
    max_polling_errors: int = 3
    max_webhook_errors: int = 5

class SessionManager:
    """Quản lý phiên làm việc với Redis backend"""
    
    def __init__(self):
        self.redis = get_redis_storage()
        self.config: Optional[SessionConfig] = None
        self.state = SessionState.IDLE
        self._load_state()
    
    def start_session(self, config: SessionConfig) -> bool:
        """Khởi động phiên làm việc mới"""
        current_state = self.redis.get_session_state()
        if current_state and current_state.get("state") not in ["idle", "terminated"]:
            print(f"[SessionManager] Cannot start: current state is {current_state.get('state')}")
            return False
        
        try:
            self.config = config
            
            # Xác định state dựa trên config
            if config.webhook_enabled:
                self.state = SessionState.BOTH_ACTIVE
            else:
                self.state = SessionState.POLLING_ACTIVE
            
            session_data = {
                "session_id": config.session_id,
                "state": self.state.value,
                "start_time": config.start_time,
                "polling_interval": config.polling_interval,
                "webhook_enabled": config.webhook_enabled,
                "polling_mode": config.polling_mode,
                "polling_errors": 0,
                "webhook_errors": 0,
                "processed_count": 0,
                "pending_count": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            self.redis.set_session_state(session_data)
            print(f"[SessionManager] Session {config.session_id} started")
            
            # Hiển thị mode phù hợp
            if config.webhook_enabled:
                print("[SessionManager] Mode: BOTH_ACTIVE (Polling + Webhook)")
            else:
                print("[SessionManager] Mode: POLLING_ACTIVE (Polling only)")
            
            return True
            
        except Exception as e:
            # ✅ NEW: Set FAILED_TO_START state on startup failure
            print(f"[SessionManager] ERROR: Failed to start session: {e}")
            self.set_failed_to_start(str(e))
            return False
    
    # ✅ NEW METHOD: Set FAILED_TO_START state
    def set_failed_to_start(self, reason: str):
        """
        Mark session as failed to start.
        Used when session initialization fails (Story 1.6 AC1-2)
        """
        self.state = SessionState.FAILED_TO_START
        
        session_data = {
            "session_id": self.config.session_id if self.config else "unknown",
            "state": self.state.value,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "end_time": datetime.now(timezone.utc).isoformat(),
            "failure_reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        self.redis.set_session_state(session_data)
        print(f"[SessionManager] Session marked as FAILED_TO_START: {reason}")
    
    # ✅ NEW METHOD: Set SESSION_ERROR state
    def set_session_error(self, error: str, context: str = ""):
        """
        Mark session in error state.
        Used for runtime errors that require session recovery (Story 1.6 AC1-2)
        """
        self.state = SessionState.SESSION_ERROR
        
        self.redis.update_session_field("state", self.state.value)
        self.redis.update_session_field("error_details", error)
        self.redis.update_session_field("error_context", context)
        self.redis.update_session_field("error_timestamp", datetime.now(timezone.utc).isoformat())
        
        print(f"[SessionManager] Session ERROR: {error} (context: {context})")
    
    # ✅ NEW METHOD: Check if session can be recovered
    def can_recover_from_error(self) -> bool:
        """
        Check if current error state can be recovered.
        Returns True if session should be terminated and restarted.
        """
        current_state = self.redis.get_session_state()
        if not current_state:
            return False
        
        state = current_state.get("state")
        
        # FAILED_TO_START and SESSION_ERROR can be recovered
        if state in [SessionState.FAILED_TO_START.value, SessionState.SESSION_ERROR.value]:
            print(f"[SessionManager] Session in recoverable error state: {state}")
            return True
        
        return False
    
    # ✅ NEW METHOD: Attempt recovery from error state
    def recover_from_error(self, reason: str = "error_recovery") -> bool:
        """
        Attempt to recover from error state by:
        1. Terminating current session
        2. Clearing error state
        3. Allowing new session to start
        
        Returns True if recovery successful
        """
        if not self.can_recover_from_error():
            print("[SessionManager] Session not in recoverable error state")
            return False
        
        try:
            # Save error session to history
            current_state = self.redis.get_session_state()
            if current_state:
                self.redis.save_session_history(current_state)
            
            # Clear session state
            self.redis.delete_session()
            self.state = SessionState.IDLE
            
            print(f"[SessionManager] Recovery successful. Reason: {reason}")
            return True
            
        except Exception as e:
            print(f"[SessionManager] Recovery failed: {e}")
            return False
    
    def complete_initial_polling(self) -> bool:
        """Hoàn thành giai đoạn polling ban đầu"""
        current_state = self.redis.get_session_state()
        if not current_state or current_state.get("state") != SessionState.BOTH_ACTIVE.value:
            print(f"[SessionManager] Invalid transition from {current_state.get('state') if current_state else 'None'}")
            return False
        
        self.state = SessionState.WEBHOOK_ACTIVE
        self.redis.update_session_field("state", self.state.value)
        self.redis.update_session_field("timestamp", datetime.now(timezone.utc).isoformat())
        
        print("[SessionManager] Initial polling completed")
        print("[SessionManager] Mode: WEBHOOK_ACTIVE (Webhook only)")
        return True
    
    def activate_fallback_polling(self, reason: str) -> bool:
        """Kích hoạt polling dự phòng khi webhook lỗi"""
        current_state = self.redis.get_session_state()
        if not current_state:
            return False
        
        try:
            if current_state.get("state") == SessionState.WEBHOOK_ACTIVE.value:
                self.state = SessionState.BOTH_ACTIVE
                
                self.redis.update_session_field("state", self.state.value)
                webhook_errors = self.redis.increment_session_counter("webhook_errors")
                self.redis.update_session_field("fallback_reason", reason)
                self.redis.update_session_field("timestamp", datetime.now(timezone.utc).isoformat())
                
                print(f"[SessionManager] FALLBACK activated: {reason}")
                print(f"[SessionManager] Webhook errors: {webhook_errors}")
                return True
            
            return False
            
        except Exception as e:
            # ✅ NEW: Set SESSION_ERROR if fallback activation fails
            self.set_session_error(str(e), "fallback_activation")
            return False
    
    def restore_webhook_only(self) -> bool:
        """Khôi phục cơ chế chỉ webhook sau khi sửa lỗi"""
        current_state = self.redis.get_session_state()
        if not current_state:
            return False
        
        if current_state.get("state") == SessionState.BOTH_ACTIVE.value:
            self.state = SessionState.WEBHOOK_ACTIVE
            
            self.redis.update_session_field("state", self.state.value)
            self.redis.update_session_field("webhook_errors", "0")
            self.redis.update_session_field("timestamp", datetime.now(timezone.utc).isoformat())
            
            print("[SessionManager] Webhook restored, polling deactivated")
            return True
        
        return False
    
    def register_processed_email(self, email_id: str) -> bool:
        """Đăng ký email đã xử lý"""
        is_new = self.redis.mark_email_processed(email_id)
        
        if is_new:
            self.redis.remove_pending(email_id)
            self.redis.increment_session_counter("processed_count")
            self.redis.increment_metric("emails_processed")
            self.redis.increment_counter("total_processed")
        
        return is_new
    
    def register_pending_email(self, email_id: str):
        """Đăng ký email đang chờ xử lý"""
        if not self.redis.is_email_processed(email_id):
            self.redis.add_pending_email(email_id)
            pending_count = self.redis.get_pending_count()
            self.redis.update_session_field("pending_count", pending_count)
    
    def register_failed_email(self, email_id: str, error: str):
        """Đăng ký email xử lý thất bại"""
        self.redis.move_to_failed(email_id, error)
        self.redis.increment_session_counter("failed_count")
        self.redis.increment_metric("emails_failed")
    
    def increment_polling_errors(self) -> int:
        """Increment polling error count"""
        return self.redis.increment_session_counter("polling_errors")
    
    def increment_webhook_errors(self) -> int:
        """Increment webhook error count"""
        return self.redis.increment_session_counter("webhook_errors")
    
    def terminate_session(self, reason: str = "user_requested"):
        """Kết thúc phiên làm việc"""
        current_state = self.redis.get_session_state()
        if not current_state:
            print("[SessionManager] No active session to terminate")
            return
        
        print(f"[SessionManager] Terminating session: {reason}")
        
        processed = self.redis.get_processed_count()
        pending = self.redis.get_pending_count()
        failed = self.redis.get_failed_count()
        
        print(f"[SessionManager] Processed emails: {processed}")
        print(f"[SessionManager] Pending emails: {pending}")
        print(f"[SessionManager] Failed emails: {failed}")
        
        self.state = SessionState.TERMINATED
        self.redis.update_session_field("state", self.state.value)
        self.redis.update_session_field("end_time", datetime.now(timezone.utc).isoformat())
        self.redis.update_session_field("termination_reason", reason)
        
        final_state = self.redis.get_session_state()
        self.redis.save_session_history(final_state)
    
    def get_session_status(self) -> Dict:
        """Lấy trạng thái phiên hiện tại"""
        session_data = self.redis.get_session_state()
        
        if not session_data:
            return {
                "session_id": None,
                "state": SessionState.IDLE.value,
                "processed_count": 0,
                "pending_count": 0,
                "failed_count": 0,
                "polling_errors": 0,
                "webhook_errors": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        processed_count = self.redis.get_processed_count()
        pending_count = self.redis.get_pending_count()
        failed_count = self.redis.get_failed_count()
        
        session_data["processed_count"] = processed_count
        session_data["pending_count"] = pending_count
        session_data["failed_count"] = failed_count
        
        for key in ["polling_errors", "webhook_errors", "polling_interval"]:
            if key in session_data:
                session_data[key] = int(session_data.get(key, 0))
        
        return session_data
    
    def is_email_processed(self, email_id: str) -> bool:
        """Kiểm tra email đã được xử lý chưa"""
        return self.redis.is_email_processed(email_id)
    
    def get_metrics(self) -> Dict:
        """Lấy metrics tổng hợp"""
        today_metrics = self.redis.get_metrics()
        total_processed = self.redis.get_counter("total_processed")
        session_status = self.get_session_status()
        
        return {
            "today": today_metrics,
            "lifetime": {
                "total_processed": total_processed
            },
            "session": session_status
        }
    
    def _load_state(self):
        """Load state từ Redis khi khởi tạo"""
        session_data = self.redis.get_session_state()
        if session_data:
            state_str = session_data.get("state", "idle")
            try:
                self.state = SessionState(state_str)
            except ValueError:
                self.state = SessionState.IDLE

# Singleton instance
session_manager = SessionManager()