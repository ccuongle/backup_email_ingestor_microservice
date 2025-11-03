"""
Webhook Service
Xử lý email theo cơ chế webhook với ngrok tunnel riêng biệt
"""
import asyncio
import json
import httpx
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict
from pyngrok import ngrok
import psutil
import time
from core.session_manager import session_manager, SessionState
from core.queue_manager import get_email_queue
from core.token_manager import get_token
from cache.redis_manager import get_redis_storage
from utils.config import (
    GRAPH_API_RATE_LIMIT_THRESHOLD,
    GRAPH_API_RATE_LIMIT_WINDOW_SECONDS,
    GRAPH_API_RATE_LIMIT_RETRY_DELAY_SECONDS,
    GRAPH_API_MAX_RETRIES,
    GRAPH_API_INITIAL_BACKOFF_SECONDS,
    GRAPH_API_BACKOFF_FACTOR
)
from utils.api_retry import api_retry

class WebhookService:
    """Dịch vụ webhook cho email notifications"""
    
    GRAPH_URL = "https://graph.microsoft.com/v1.0"
    WEBHOOK_PORT = 8100  # Port riêng cho webhook
    RATE_LIMIT_KEY = "graph_api_webhook"
    
    def __init__(self):
        self.active = False
        self.public_url: Optional[str] = None
        self.subscription_id: Optional[str] = None
        self.queue = get_email_queue()
        self.ngrok_tunnel = None
        self.error_count = 0
        self.max_errors = 5
        self.app = None
        self.server_process = None
        self.redis = get_redis_storage()
        self._stop_event = threading.Event()

    def _check_and_wait_for_rate_limit(self) -> bool:
        """
        Check rate limit before making Graph API call.
        If limit exceeded, pause execution for configured duration.
        
        Returns:
            True if request is allowed, False if service should stop
        """
        allowed, current_count = self.redis.check_rate_limit(
            key=self.RATE_LIMIT_KEY,
            limit=GRAPH_API_RATE_LIMIT_THRESHOLD,
            window=GRAPH_API_RATE_LIMIT_WINDOW_SECONDS
        )
        
        if not allowed:
            print(f"[WebhookService] Rate limit exceeded ({current_count}/{GRAPH_API_RATE_LIMIT_THRESHOLD})")
            print(f"[WebhookService] Pausing for {GRAPH_API_RATE_LIMIT_RETRY_DELAY_SECONDS}s before retry...")
            
            # Wait with ability to check stop event
            if self._stop_event.wait(timeout=GRAPH_API_RATE_LIMIT_RETRY_DELAY_SECONDS):
                # Stop event was set during wait
                return False
            
            # After wait, check rate limit again
            return self._check_and_wait_for_rate_limit()
        
        return True

    
    async def start(self) -> bool:
        """Khởi động webhook service"""
        if self.active:
            print(f"[WebhookService] Already active")
            return False
        
        try:
            print(f"[WebhookService] Starting on port {self.WEBHOOK_PORT}...")
            
            # Step 1: Kill existing processes
            self._kill_port_process(self.WEBHOOK_PORT)
            self._kill_existing_ngrok()
            
            # Step 2: Start ngrok tunnel
            self.public_url = self._start_ngrok()
            print(f"[WebhookService] Public URL: {self.public_url}")
            
            # Step 3: Start FastAPI server
            self._start_fastapi_server()
            time.sleep(3)  # Đợi server khởi động
            
            # Step 4: Create subscription
            self.subscription_id = await self._create_subscription()
            if not self.subscription_id:
                raise Exception("Failed to create subscription")
            
            print(f"[WebhookService] Subscription created: {self.subscription_id}")
            
            # Step 5: Start renewal watcher
            self._start_renewal_watcher()
            
            self.active = True
            self.error_count = 0
            
            print(f"[WebhookService] Started successfully")
            return True
        
        except Exception as e:
            print(f"[WebhookService] Start error: {e}")
            self.stop()
            return False
    
    async def stop(self):
        """Dừng webhook service"""
        if not self.active:
            return
        
        print(f"[WebhookService] Stopping...")
        
        # Delete subscription
        if self.subscription_id:
            await self._delete_subscription()
        
        # Stop FastAPI server
        if self.server_process:
            self.server_process.terminate()
            self.server_process = None
        
        # Close ngrok tunnel
        if self.ngrok_tunnel:
            ngrok.disconnect(self.ngrok_tunnel.public_url)
            self.ngrok_tunnel = None
        
        self.active = False
        print(f"[WebhookService] Stopped")
    
    async def handle_notification(self, notification_data: Dict) -> Dict:
        """Xử lý notification từ Microsoft Graph"""
        try:
            enqueued_count = 0
            skipped_count = 0
            notifications = notification_data.get("value", [])
            
            # Group notifications by email ID to handle duplicates
            seen_ids = set()
            unique_notifications = []
            
            for notif in notifications:
                msg_id = notif.get("resourceData", {}).get("id")
                if not msg_id:
                    continue
                
                # Skip if already seen in this batch
                if msg_id in seen_ids:
                    continue
                
                seen_ids.add(msg_id)
                unique_notifications.append((msg_id, notif))
            
            # Process unique notifications
            for msg_id, notif in unique_notifications:
                # Kiểm tra duplicate (already queued or processed)
                if self.queue.is_in_queue(msg_id):
                    skipped_count += 1
                    # Only log if verbose mode or first time
                    if skipped_count == 1:
                        print(f"[WebhookService] Skipping {len(unique_notifications) - enqueued_count} duplicate(s) in queue")
                    continue
                
                if session_manager.is_email_processed(msg_id):
                    skipped_count += 1
                    if skipped_count == 1:
                        print(f"[WebhookService] Skipping {len(unique_notifications) - enqueued_count} already processed email(s)")
                    continue
                
                # Fetch email detail
                message = await self._fetch_email_detail(msg_id)
                if message:
                    # Enqueue email for batch processing
                    enqueued_id = self.queue.enqueue(msg_id, message)
                    if enqueued_id:
                        session_manager.register_pending_email(msg_id)
                        enqueued_count += 1
                        print(f"[WebhookService] ✓ Enqueued: {msg_id[:50]}...")
                        
                        # Mark as read immediately (fire and forget)
                        asyncio.create_task(self._mark_as_read(enqueued_id))
                    else:
                        # enqueue returned None - already in queue or processed
                        skipped_count += 1
            
            # Summary log
            if enqueued_count > 0 or skipped_count > 0:
                print(f"[WebhookService] Notification batch: {enqueued_count} enqueued, {skipped_count} skipped")
            
            # Reset error count khi thành công
            self.error_count = 0
            
            return {
                "status": "success",
                "enqueued": enqueued_count,
                "skipped": skipped_count
            }
        
        except Exception as e:
            print(f"[WebhookService] Notification handling error: {e}")
            self.error_count += 1
            
            # Kích hoạt fallback nếu quá nhiều lỗi
            if self.error_count >= self.max_errors:
                self._activate_fallback()
            
            return {
                "status": "error",
                "error": str(e)
            }
        
    def _activate_fallback(self):
        """Kích hoạt fallback polling khi webhook lỗi"""
        print(f"[WebhookService] Too many errors ({self.error_count}), activating fallback")
        
        session_manager.activate_fallback_polling(
            reason=f"webhook_errors_{self.error_count}"
        )
        
        # Import polling service để kích hoạt
        from core.polling_service import polling_service, TriggerMode
        polling_service.start(mode=TriggerMode.FALLBACK, interval=300)
    
    @api_retry(max_retries=GRAPH_API_MAX_RETRIES, initial_backoff=GRAPH_API_INITIAL_BACKOFF_SECONDS, backoff_factor=GRAPH_API_BACKOFF_FACTOR)
    async def _fetch_email_detail(self, message_id: str) -> Optional[Dict]:
        """Lấy chi tiết email từ Graph API"""
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.GRAPH_URL}/me/messages/{message_id}"
        
        if not self._check_and_wait_for_rate_limit():
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=10)            
            if resp.status_code == 200:
                return resp.json()
        except httpx.RequestError as e:
            print(f"[WebhookService] Fetch email error: {e}")
            return None
    
    @api_retry(max_retries=GRAPH_API_MAX_RETRIES, initial_backoff=GRAPH_API_INITIAL_BACKOFF_SECONDS, backoff_factor=GRAPH_API_BACKOFF_FACTOR)
    async def _mark_as_read(self, message_id: str):
        """Mark a single email as read."""
        token = get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        url = f"{self.GRAPH_URL}/me/messages/{message_id}"
        body = {"isRead": True}

        try:
            if not self._check_and_wait_for_rate_limit():
                return
            async with httpx.AsyncClient() as client:
                await client.patch(url, headers=headers, json=body, timeout=10)
            print(f"[WebhookService] ✓ Marked {message_id} as read.")
        except httpx.RequestError as e:
            print(f"[WebhookService] ERROR: Failed to mark {message_id} as read: {e}")
    
    def _start_ngrok(self) -> str:
        """Khởi động ngrok tunnel riêng cho webhook"""
        try:
            self.ngrok_tunnel = ngrok.connect(
                self.WEBHOOK_PORT,
                bind_tls=True,
                proto="http"
            )
            time.sleep(1.5)
            return self.ngrok_tunnel.public_url
        except Exception as e:
            raise Exception(f"Failed to start ngrok: {e}")
    
    def _kill_existing_ngrok(self):
        """Kill tất cả ngrok processes"""
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and "ngrok" in proc.info['name'].lower():
                    proc.kill()
            except:
                pass
    
    def _kill_port_process(self, port: int):
        """Kill process đang dùng port"""
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for conn in proc.net_connections():
                    if conn.laddr.port == port:
                        print(f"[WebhookService] Killing process on port {port}")
                        proc.kill()
                        time.sleep(2)
                        break
            except:
                pass
    
    def _start_fastapi_server(self):
        """Khởi động FastAPI server trong subprocess"""
        import subprocess
        cmd = [
            "uvicorn",
            "api.webhook_app:app",
            "--host", "0.0.0.0",
            "--port", str(self.WEBHOOK_PORT)
        ]
        self.server_process = subprocess.Popen(cmd)
    
    @api_retry(max_retries=GRAPH_API_MAX_RETRIES, initial_backoff=GRAPH_API_INITIAL_BACKOFF_SECONDS, backoff_factor=GRAPH_API_BACKOFF_FACTOR)
    async def _create_subscription(self) -> Optional[str]:
        """Tạo Microsoft Graph subscription"""
        token = get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        notification_url = f"{self.public_url}/webhook/notifications"
        exp = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        
        payload = {
            "changeType": "created",
            "notificationUrl": notification_url,
            "resource": "me/mailfolders('inbox')/messages",
            "expirationDateTime": exp,
            "clientState": "webhook_secret_state"
            }

        try:
            if not self._check_and_wait_for_rate_limit():
                return None
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.GRAPH_URL}/subscriptions",
                    headers=headers,
                    json=payload,
                    timeout=30
                    )            
            if resp.status_code == 201:
                data = resp.json()
                sub_id = data.get("id")
                
                # Save subscription to Redis
                session_manager.redis.save_subscription(data)
                
                return sub_id
            
            print(f"[WebhookService] Subscription creation failed: {resp.text}")
            return None
        
        except httpx.RequestError as e:
            print(f"[WebhookService] Subscription error: {e}")
            return None
    
    @api_retry(max_retries=GRAPH_API_MAX_RETRIES, initial_backoff=GRAPH_API_INITIAL_BACKOFF_SECONDS, backoff_factor=GRAPH_API_BACKOFF_FACTOR)
    async def _delete_subscription(self):
        """Xóa subscription"""
        if not self.subscription_id:
            return
        
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            if not self._check_and_wait_for_rate_limit():
                return
            async with httpx.AsyncClient() as client:
                await client.delete(
                    f"{self.GRAPH_URL}/subscriptions/{self.subscription_id}",
                    headers=headers,
                    timeout=10
                        )            
                print(f"[WebhookService] Subscription deleted")
        except httpx.RequestError as e:
            print(f"[WebhookService] Delete subscription error: {e}")
    
    @api_retry(max_retries=GRAPH_API_MAX_RETRIES, initial_backoff=GRAPH_API_INITIAL_BACKOFF_SECONDS, backoff_factor=GRAPH_API_BACKOFF_FACTOR)
    async def _renew_subscription(self) -> bool:
        """Renew subscription"""
        if not self.subscription_id:
            return False
        
        token = get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        new_exp = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        payload = {"expirationDateTime": new_exp}
        try:
            if not self._check_and_wait_for_rate_limit():
                return False
            async with httpx.AsyncClient() as client:
                        resp = await client.patch(
                            f"{self.GRAPH_URL}/subscriptions/{self.subscription_id}",
                            headers=headers,
                            json=payload,
                            timeout=10
                        )            
            if resp.status_code == 200:
                print(f"[WebhookService] Subscription renewed until {new_exp}")
                return True
            
            return False
        except httpx.RequestError as e:
            print(f"[WebhookService] Renew error: {e}")
            return False
    
    def _start_renewal_watcher(self):
        """Khởi động watcher tự động renew subscription"""
        async def renewal_loop():
            check_interval = 300  # 5 phút
            threshold_hours = 1
            
            while self.active:
                try:
                    await asyncio.sleep(check_interval)
                    
                    # Get subscription status
                    if not self._check_and_wait_for_rate_limit():
                        continue
                    token = get_token()
                    headers = {"Authorization": f"Bearer {token}"}
                    
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            f"{self.GRAPH_URL}/subscriptions/{self.subscription_id}",
                            headers=headers,
                            timeout=10
                        )
                    
                    if resp.status_code != 200:
                        print(f"[WebhookService] Subscription not found, recreating...")
                        self.subscription_id = await self._create_subscription()
                        continue
                    
                    sub = resp.json()
                    exp_str = sub.get("expirationDateTime")
                    exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                    remaining = exp_dt - datetime.now(timezone.utc)
                    hours_left = remaining.total_seconds() / 3600
                    
                    # Renew if needed
                    if hours_left < threshold_hours:
                        print(f"[WebhookService] Renewing (only {hours_left:.1f}h left)")
                        await self._renew_subscription()
                
                except Exception as e:
                    print(f"[WebhookService] Renewal watcher error: {e}")
        
        asyncio.create_task(renewal_loop())
    
    def get_status(self) -> Dict:
        """Lấy trạng thái webhook service"""
        return {
            "active": self.active,
            "public_url": self.public_url,
            "subscription_id": self.subscription_id,
            "error_count": self.error_count,
            "port": self.WEBHOOK_PORT
        }

# Singleton instance
webhook_service = WebhookService()