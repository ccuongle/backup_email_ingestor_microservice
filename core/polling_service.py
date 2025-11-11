"""
Polling Service - Enhanced with Pagination Cursor Tracking
Ensures no emails are missed when pagination exceeds MAX_POLL_PAGES
"""
import time
import threading
import httpx
from typing import List, Dict, Optional
from utils.config import (
    MAX_POLL_PAGES as max_pages,
    GRAPH_API_RATE_LIMIT_THRESHOLD,
    GRAPH_API_RATE_LIMIT_WINDOW_SECONDS,
    GRAPH_API_RATE_LIMIT_RETRY_DELAY_SECONDS,
    GRAPH_API_MAX_RETRIES,
    GRAPH_API_INITIAL_BACKOFF_SECONDS,
    GRAPH_API_BACKOFF_FACTOR
)
from core.session_manager import session_manager, TriggerMode
from core.queue_manager import get_email_queue
from core.token_manager import get_token
from cache.redis_manager import get_redis_storage
from utils.api_retry import api_retry

class PollingService:
    """
    Polling service - optimized with queue and cursor tracking
    """
    
    GRAPH_URL = "https://graph.microsoft.com/v1.0"
    RATE_LIMIT_KEY = "graph_api_polling"
    CURSOR_REDIS_KEY = "polling:pagination_cursor"  # ✅ NEW: Store cursor
    
    def __init__(self):
        self.active = False
        self.mode = TriggerMode.MANUAL
        self.interval = 300
        self.thread: Optional[threading.Thread] = None
        self.queue = get_email_queue()
        self._stop_event = threading.Event()
        self.redis = get_redis_storage()
    
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
        
        print("[PollingService] Stopping...")
        self.active = False
        self._stop_event.set()
        
        if (self.thread and self.thread.is_alive() and 
            threading.current_thread() != self.thread):
            self.thread.join(timeout=5)
        
        print("[PollingService] Stopped")

    def _check_and_wait_for_rate_limit(self) -> bool:
        """Check rate limit before making Graph API call"""
        allowed, current_count = self.redis.check_rate_limit(
            key=self.RATE_LIMIT_KEY,
            limit=GRAPH_API_RATE_LIMIT_THRESHOLD,
            window=GRAPH_API_RATE_LIMIT_WINDOW_SECONDS
        )
        
        if not allowed:
            print(f"[PollingService] Rate limit exceeded ({current_count}/{GRAPH_API_RATE_LIMIT_THRESHOLD})")
            print(f"[PollingService] Pausing for {GRAPH_API_RATE_LIMIT_RETRY_DELAY_SECONDS}s before retry...")
            
            if self._stop_event.wait(timeout=GRAPH_API_RATE_LIMIT_RETRY_DELAY_SECONDS):
                return False
            
            return self._check_and_wait_for_rate_limit()
        
        return True
    
    # ✅ NEW METHOD: Get/Set pagination cursor
    def _get_pagination_cursor(self) -> Optional[str]:
        """Get stored pagination cursor for resuming"""
        try:
            cursor = self.redis.redis.get(self.CURSOR_REDIS_KEY)
            if cursor:
                print("[PollingService] Found pagination cursor, resuming from previous position")
            return cursor
        except Exception as e:
            print(f"[PollingService] Error getting cursor: {e}")
            return None
    
    def _set_pagination_cursor(self, cursor: Optional[str]):
        """Store pagination cursor for next poll"""
        try:
            if cursor:
                # Store with 1 hour TTL (cursor expires after some time)
                self.redis.redis.setex(self.CURSOR_REDIS_KEY, 3600, cursor)
                print("[PollingService] Stored pagination cursor for next poll")
            else:
                # Clear cursor when pagination complete
                self.redis.redis.delete(self.CURSOR_REDIS_KEY)
        except Exception as e:
            print(f"[PollingService] Error setting cursor: {e}")
    
    async def poll_once(self) -> Dict:
        """
        Fetch emails và enqueue (không xử lý)
        Processing sẽ do BatchProcessor đảm nhận
        """
        try:
            print("[PollingService] Fetching unread emails...")
            start_time = time.time()
            
            # ✅ NEW: Check for existing cursor
            resume_cursor = self._get_pagination_cursor()
            
            # Fetch emails (with cursor support)
            messages, next_cursor = await self._fetch_unread_emails(resume_from=resume_cursor)
            fetch_time = time.time() - start_time
            
            if not messages:
                print("[PollingService] No unread emails found")
                # ✅ Clear cursor if no messages
                self._set_pagination_cursor(None)
                return {
                    "status": "success",
                    "emails_found": 0,
                    "enqueued": 0,
                    "skipped": 0,
                    "fetch_time": fetch_time,
                    "has_more": False
                }
            
            print(f"[PollingService] Found {len(messages)} unread emails (took {fetch_time:.2f}s)")
            
            # ✅ NEW: Save cursor if pagination incomplete
            if next_cursor:
                print("[PollingService] More emails available, cursor saved for next poll")
                self._set_pagination_cursor(next_cursor)
            else:
                print("[PollingService] All emails fetched")
                self._set_pagination_cursor(None)
            
            # Batch enqueue
            enqueue_start = time.time()
            emails_to_enqueue = [
                (msg.get("id"), msg, None)
                for msg in messages
            ]
            
            enqueued_ids = self.queue.enqueue_batch(emails_to_enqueue)
            enqueue_time = time.time() - enqueue_start
            
            enqueued = len(enqueued_ids)
            skipped = len(messages) - enqueued
            
            print(f"[PollingService] Enqueued {enqueued} emails (took {enqueue_time:.2f}s)")
            if skipped > 0:
                print(f"[PollingService] Skipped {skipped} emails (already processed/queued)")
            
            # Mark enqueued emails as read immediately
            if enqueued_ids:
                await self._batch_mark_as_read(enqueued_ids)
            
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
                "total_time": time.time() - start_time,
                "has_more": bool(next_cursor)  # ✅ NEW: Indicate if more emails available
            }
        
        except Exception as e:
            print(f"[PollingService] Poll error: {e}")
            session_manager.increment_polling_errors()
            return {
                "status": "error",
                "error": str(e),
                "emails_found": 0,
                "enqueued": 0,
                "skipped": 0,
                "has_more": False
            }
    
    def _polling_loop(self):
        """Background loop cho scheduled/fallback polling"""
        print("[PollingService] Background polling started")
                
        while self.active and not self._stop_event.is_set():
            try:
                # Vòng lặp này chỉ dành cho FALLBACK mode
                if self.mode != TriggerMode.FALLBACK:
                    print(f"[PollingService] Loop paused (mode: {self.mode.value}). Only runs in FALLBACK mode.")
                    time.sleep(self.interval)
                    continue
                
                # Poll
                print("[PollingService] Fallback poll running...")
                self.poll_once()
                
                # Wait before next poll
                print(f"[PollingService] Waiting {self.interval}s until next poll...")
                self._stop_event.wait(timeout=self.interval)
            
            except Exception as e:
                print(f"[PollingService] Loop error: {e}")
                time.sleep(30)
        
        print("[PollingService] Background polling stopped")
    
    @api_retry(max_retries=GRAPH_API_MAX_RETRIES, initial_backoff=GRAPH_API_INITIAL_BACKOFF_SECONDS, backoff_factor=GRAPH_API_BACKOFF_FACTOR)
    async def _fetch_unread_emails(
        self, 
        max_results: int = 100,
        resume_from: Optional[str] = None
    ) -> tuple[List[Dict], Optional[str]]:
        """
        Fetch unread emails from Graph API with cursor support
        
        Args:
            max_results: Max results per page
            resume_from: Cursor to resume from previous poll
        
        Returns:
            (messages, next_cursor) - next_cursor is None if pagination complete
        """
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        all_messages = []
        page_count = 0
        
        # ✅ NEW: Use cursor if provided, otherwise start fresh
        if resume_from:
            url = resume_from  # Resume from stored cursor
            params = None  # No params needed for cursor URL
            print("[PollingService] Resuming pagination from stored cursor")
        else:
            url = f"{self.GRAPH_URL}/me/messages"
            params = {
                "$filter": "isRead eq false",
                "$top": max_results,
                "$orderby": "receivedDateTime desc"
            }

        while url and page_count < max_pages:
            if not self._check_and_wait_for_rate_limit():
                break
            
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(url, headers=headers, params=params, timeout=30)
                
                # Clear params after first request
                if params:
                    params = None 

                if resp.status_code != 200:
                    print(f"[PollingService] API error during pagination: {resp.status_code} - {resp.text}")
                    break

                data = resp.json()
                messages = data.get("value", [])
                all_messages.extend(messages)
                
                page_count += 1
                url = data.get("@odata.nextLink")

                if url:
                    print(f"[PollingService] Fetched page {page_count}, more emails available...")
                else:
                    print(f"[PollingService] Fetched final page ({page_count}). No more pages.")
                    
            except httpx.RequestError as e:
                print(f"[PollingService] Network error during pagination: {e}")
                raise

        # ✅ NEW: Return cursor if hit max_pages limit
        if page_count >= max_pages and url:
            print(f"[PollingService] ⚠️ Reached max poll pages limit ({max_pages})")
            print("[PollingService] Cursor saved to continue in next poll")
            return all_messages, url  # Return nextLink as cursor
        
        # Pagination complete
        return all_messages, None

    @api_retry(max_retries=GRAPH_API_MAX_RETRIES, initial_backoff=GRAPH_API_INITIAL_BACKOFF_SECONDS, backoff_factor=GRAPH_API_BACKOFF_FACTOR)
    async def _batch_mark_as_read(self, email_ids: List[str]):
        """Mark a batch of emails as read using Microsoft Graph batching"""
        if not email_ids:
            return

        print(f"[PollingService] Marking {len(email_ids)} emails as read...")
        token = get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        batch_payload = {
            "requests": [
                {
                    "id": str(i + 1),
                    "method": "PATCH",
                    "url": f"/me/messages/{email_id}",
                    "body": {"isRead": True},
                    "headers": {"Content-Type": "application/json"}
                } for i, email_id in enumerate(email_ids)
            ]
        }

        try:
            if not self._check_and_wait_for_rate_limit():
                return
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.GRAPH_URL}/$batch",
                    headers=headers,
                    json=batch_payload,
                    timeout=60
                )
            await response.raise_for_status()
            print(f"[PollingService] ✓ Successfully marked {len(email_ids)} as read.")
        except httpx.RequestError as e:
            print(f"[PollingService] ERROR: Failed to batch mark as read: {e}")
    
    def get_status(self) -> Dict:
        """Lấy trạng thái hiện tại"""
        queue_stats = self.queue.get_stats()
        
        # ✅ NEW: Include cursor status
        has_cursor = bool(self._get_pagination_cursor())
        
        return {
            "active": self.active,
            "mode": self.mode.value if self.mode else None,
            "interval": self.interval,
            "thread_alive": self.thread.is_alive() if self.thread else False,
            "queue_size": queue_stats["queue_size"],
            "pagination_pending": has_cursor  # ✅ NEW field
        }


# Singleton instance
polling_service = PollingService()