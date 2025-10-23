"""
Polling Service
Xử lý email theo cơ chế polling (định kỳ hoặc thủ công)
"""
import time
import threading
import requests
from typing import List, Dict, Optional
from datetime import datetime, timezone
from core.session_manager import session_manager, SessionState, TriggerMode
from core.unified_email_processor import EmailProcessor
from core.token_manager import get_token

class PollingService:
    """Dịch vụ polling email"""
    
    GRAPH_URL = "https://graph.microsoft.com/v1.0"
    
    def __init__(self):
        self.active = False
        self.mode = TriggerMode.MANUAL
        self.interval = 300  # 5 phút
        self.thread: Optional[threading.Thread] = None
        self.processor: Optional[EmailProcessor] = None
        self._stop_event = threading.Event()
    
    def start(self, mode: TriggerMode = TriggerMode.SCHEDULED, interval: int = 300):
        """Khởi động polling service"""
        if self.active:
            print(f"[PollingService] Already active in {self.mode.value} mode")
            return False
        
        self.mode = mode
        self.interval = interval
        self.active = True
        self._stop_event.clear()
        
        token = get_token()
        self.processor = EmailProcessor(token)
        
        print(f"[PollingService] Starting in {mode.value} mode")
        print(f"[PollingService] Interval: {interval}s ({interval/60:.1f}min)")
        
        if mode == TriggerMode.SCHEDULED or mode == TriggerMode.FALLBACK:
            self.thread = threading.Thread(target=self._polling_loop, daemon=True)
            self.thread.start()
        
        return True
    
    def stop(self):
        """Dừng polling service"""
        if not self.active:
            return
        
        print(f"[PollingService] Stopping...")
        self.active = False
        self._stop_event.set()
        
        if (self.thread and self.thread.is_alive() and 
            threading.current_thread() != self.thread):
            self.thread.join(timeout=5)
        
        print(f"[PollingService] Stopped")
    
    def poll_once(self) -> Dict:
        """Thực hiện 1 lần polling thủ công"""
        if not self.processor:
            token = get_token()
            self.processor = EmailProcessor(token)
        
        try:
            print(f"[PollingService] Starting manual poll...")
            messages = self._fetch_unread_emails()
            
            if not messages:
                print(f"[PollingService] No unread emails found")
                return {
                    "status": "success",
                    "emails_found": 0,
                    "processed": 0,
                    "failed": 0,
                    "skipped": 0
                }
            
            print(f"[PollingService] Found {len(messages)} unread emails")
            result = self.processor.batch_process_emails(messages, source="polling")
            
            print(f"[PollingService] Poll completed:")
            print(f"  Total: {result['total']}")
            print(f"  Success: {result['success']}")
            print(f"  Failed: {result['failed']}")
            print(f"  Skipped: {result['skipped']}")
            
            return {
                "status": "success",
                "emails_found": len(messages),
                **result
            }
        except Exception as e:
            print(f"[PollingService] Poll error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "emails_found": 0,
                "processed": 0,
                "failed": 0,
                "skipped": 0
            }
    
    def _polling_loop(self):
        """Background loop cho scheduled/fallback polling"""
        print(f"[PollingService] Background polling started")
        
        while self.active and not self._stop_event.is_set():
            try:
                session_status = session_manager.get_session_status()
                current_state = SessionState(session_status["state"])
                
                if current_state != SessionState.BOTH_ACTIVE:
                    print(f"[PollingService] Paused (state: {current_state.value})")
                    time.sleep(self.interval)
                    continue
                
                result = self.poll_once()
                
                if self.mode == TriggerMode.SCHEDULED and result["emails_found"] == 0:
                    print(f"[PollingService] Initial polling completed, no more emails")
                    session_manager.complete_initial_polling()
                    self.stop()
                    break
                
                print(f"[PollingService] Waiting {self.interval}s until next poll...")
                self._stop_event.wait(timeout=self.interval)
            
            except Exception as e:
                print(f"[PollingService] Loop error: {e}")
                time.sleep(30)
        
        print(f"[PollingService] Background polling stopped")
    
    def _fetch_unread_emails(self) -> List[Dict]:
        """Lấy danh sách email chưa đọc từ Graph API"""
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.GRAPH_URL}/me/messages?$filter=isRead eq false"
        
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                print(f"[PollingService] API error: {resp.status_code}")
                return []
            
            messages = resp.json().get("value", [])
            return messages
        except requests.exceptions.RequestException as e:
            print(f"[PollingService] Network error: {e}")
            return []
    
    def get_status(self) -> Dict:
        """Lấy trạng thái hiện tại"""
        return {
            "active": self.active,
            "mode": self.mode.value if self.mode else None,
            "interval": self.interval,
            "thread_alive": self.thread.is_alive() if self.thread else False
        }

# Singleton instance
polling_service = PollingService()