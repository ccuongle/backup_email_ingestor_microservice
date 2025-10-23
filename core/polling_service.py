"""
Polling Service - Updated
Fetch emails và đẩy vào queue thay vì xử lý trực tiếp
"""
import time
import threading
import requests
from typing import List, Dict, Optional
from datetime import datetime, timezone

from core.session_manager import session_manager, SessionState, TriggerMode
from core.queue_manager import get_email_queue
from core.token_manager import get_token


class PollingService:
    """
    Polling service - optimized with queue
    Chỉ fetch và enqueue, không xử lý
    """
    
    GRAPH_URL = "https://graph.microsoft.com/v1.0"
    
    def __init__(self):
        self.active = False
        self.mode = TriggerMode.MANUAL
        self.interval = 300
        self.thread: Optional[threading.Thread] = None
        self.queue = get_email_queue()
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
        """
        Fetch emails và enqueue (không xử lý)
        Processing sẽ do BatchProcessor đảm nhận
        """
        try:
            print(f"[PollingService] Fetching unread emails...")
            start_time = time.time()
            
            # Fetch emails
            messages = self._fetch_unread_emails()
            fetch_time = time.time() - start_time
            
            if not messages:
                print(f"[PollingService] No unread emails found")
                return {
                    "status": "success",
                    "emails_found": 0,
                    "enqueued": 0,
                    "skipped": 0,
                    "fetch_time": fetch_time
                }
            
            print(f"[PollingService] Found {len(messages)} unread emails (took {fetch_time:.2f}s)")
            
            # Batch enqueue
            enqueue_start = time.time()
            emails_to_enqueue = [
                (msg.get("id"), msg, None)  # (id, data, priority)
                for msg in messages
            ]
            
            enqueued = self.queue.enqueue_batch(emails_to_enqueue)
            enqueue_time = time.time() - enqueue_start
            
            skipped = len(messages) - enqueued
            
            print(f"[PollingService] Enqueued {enqueued} emails (took {enqueue_time:.2f}s)")
            if skipped > 0:
                print(f"[PollingService] Skipped {skipped} emails (already processed/queued)")
            
            # Update session stats
            for msg in messages:
                msg_id = msg.get("id")
                if not session_manager.is_email_processed(msg_id):
                    session_manager.register_pending_email(msg_id)
            
            return {
                "status": "success",
                "emails_found": len(messages),
                "enqueued": enqueued,
                "skipped": skipped,
                "fetch_time": fetch_time,
                "enqueue_time": enqueue_time,
                "total_time": time.time() - start_time
            }
        
        except Exception as e:
            print(f"[PollingService] Poll error: {e}")
            session_manager.increment_polling_errors()
            return {
                "status": "error",
                "error": str(e),
                "emails_found": 0,
                "enqueued": 0,
                "skipped": 0
            }
    
    def _polling_loop(self):
        """Background loop cho scheduled/fallback polling"""
        print(f"[PollingService] Background polling started")
        
        consecutive_empty = 0
        max_empty_before_stop = 3  # Stop sau 3 lần liên tiếp không có email
        
        while self.active and not self._stop_event.is_set():
            try:
                session_status = session_manager.get_session_status()
                current_state = SessionState(session_status["state"])
                
                # Chỉ poll khi ở BOTH_ACTIVE state
                if current_state != SessionState.BOTH_ACTIVE:
                    print(f"[PollingService] Paused (state: {current_state.value})")
                    time.sleep(self.interval)
                    continue
                
                # Poll
                result = self.poll_once()
                
                # Check if should transition to webhook-only
                if self.mode == TriggerMode.SCHEDULED:
                    if result["emails_found"] == 0:
                        consecutive_empty += 1
                        print(f"[PollingService] No emails found ({consecutive_empty}/{max_empty_before_stop})")
                        
                        if consecutive_empty >= max_empty_before_stop:
                            print(f"[PollingService] Backlog cleared, transitioning to webhook-only")
                            session_manager.complete_initial_polling()
                            self.stop()
                            break
                    else:
                        consecutive_empty = 0  # Reset counter
                
                # Wait before next poll
                print(f"[PollingService] Waiting {self.interval}s until next poll...")
                self._stop_event.wait(timeout=self.interval)
            
            except Exception as e:
                print(f"[PollingService] Loop error: {e}")
                time.sleep(30)
        
        print(f"[PollingService] Background polling stopped")
    
    def _fetch_unread_emails(self, max_results: int = 100) -> List[Dict]:
        """
        Fetch unread emails from Graph API
        
        Args:
            max_results: Maximum emails to fetch per call
        """
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Fetch with pagination support
        url = f"{self.GRAPH_URL}/me/messages"
        params = {
            "$filter": "isRead eq false",
            "$top": max_results,
            "$orderby": "receivedDateTime desc"
        }
        
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            
            if resp.status_code != 200:
                print(f"[PollingService] API error: {resp.status_code} - {resp.text}")
                return []
            
            data = resp.json()
            messages = data.get("value", [])
            
            # TODO: Handle pagination if needed (@odata.nextLink)
            next_link = data.get("@odata.nextLink")
            if next_link:
                print(f"[PollingService] More emails available (pagination not implemented)")
            
            return messages
        
        except requests.exceptions.RequestException as e:
            print(f"[PollingService] Network error: {e}")
            return []
    
    def get_status(self) -> Dict:
        """Lấy trạng thái hiện tại"""
        queue_stats = self.queue.get_stats()
        
        return {
            "active": self.active,
            "mode": self.mode.value if self.mode else None,
            "interval": self.interval,
            "thread_alive": self.thread.is_alive() if self.thread else False,
            "queue_size": queue_stats["queue_size"]
        }


# Singleton instance
polling_service = PollingService()