"""
MS4 Batch Sender
Consumes payloads from the MS4 outbound queue and sends them in batches to the MS4 Persistence API.
"""
import time
import threading
import httpx
import asyncio
from typing import List, Dict, Optional

from cache.redis_manager import get_redis_storage
from utils.config import MS4_PERSISTENCE_BASE_URL, MS4_BATCH_SIZE

class MS4BatchSender:
    """
    Sends payloads to MS4 in batches.
    """

    def __init__(
        self,
        batch_size: int = MS4_BATCH_SIZE,
        fetch_interval: float = 2.0,
        max_workers: int = 5,
    ):
        """
        Args:
            batch_size: Number of payloads per batch.
            fetch_interval: Seconds between queue checks.
            max_workers: Not used in this implementation, but kept for consistency.
        """
        self.batch_size = batch_size
        self.fetch_interval = fetch_interval
        self.redis_manager = get_redis_storage()
        self.active = False
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Client sẽ được tạo trong thread's event loop
        self.client: Optional[httpx.AsyncClient] = None

    def start(self) -> bool:
        """Start the MS4 batch sender."""
        if self.active:
            print("[MS4BatchSender] Already active")
            return False

        print(f"[MS4BatchSender] Starting...")
        print(f"  Batch size: {self.batch_size}")
        print(f"  Fetch interval: {self.fetch_interval}s")

        self.active = True
        self._stop_event.clear()
        self.thread = threading.Thread(
            target=self._processing_loop,
            daemon=True,
            name="MS4BatchSenderLoop"
        )
        self.thread.start()

        print("[MS4BatchSender] Started successfully")
        return True

    def stop(self):
        """Stop the MS4 batch sender."""
        if not self.active:
            return

        print("[MS4BatchSender] Stopping...")
        self.active = False
        self._stop_event.set()

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=10)
        
        print("[MS4BatchSender] Stopped")

    def _processing_loop(self):
        """Main processing loop - runs in a separate thread with its own event loop."""
        try:
            print("[MS4BatchSender] Processing loop started")
            
            # Tạo event loop mới cho thread này
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            print("[MS4BatchSender] Event loop created")
            
            # Tạo httpx client trong event loop này
            async def create_client():
                return httpx.AsyncClient(
                    base_url=MS4_PERSISTENCE_BASE_URL,
                    timeout=30.0,
                )
            
            self.client = self._loop.run_until_complete(create_client())
            print("[MS4BatchSender] HTTP client created")

            while self.active and not self._stop_event.is_set():
                try:
                    queue_size = self.redis_manager.get_ms4_outbound_queue_size()
                    shutting_down = self._stop_event.is_set()

                    if queue_size < self.batch_size and not (shutting_down and queue_size > 0):
                        time.sleep(self.fetch_interval)
                        continue

                    if queue_size > 0:
                        print(f"\n[MS4BatchSender] Queue size: {queue_size}. Triggering batch sending.")

                    batch_to_send = self.redis_manager.dequeue_ms4_batch(self.batch_size)

                    if not batch_to_send:
                        time.sleep(self.fetch_interval)
                        continue

                    print(f"[MS4BatchSender] Sending batch of {len(batch_to_send)} payloads...")
                    
                    # Chạy async function trong event loop của thread này
                    self._loop.run_until_complete(self._send_batch(batch_to_send))

                except Exception as e:
                    print(f"[MS4BatchSender] Loop error: {e}")
                    import traceback
                    traceback.print_exc()
                    time.sleep(5)
        except Exception as e:
            print(f"[MS4BatchSender] Fatal error in processing loop: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Cleanup client
            try:
                if self.client:
                    async def close_client():
                        await self.client.aclose()
                    self._loop.run_until_complete(close_client())
            except Exception as e:
                print(f"[MS4BatchSender] Error closing client: {e}")
            
            # Close loop
            try:
                if self._loop and not self._loop.is_closed():
                    self._loop.close()
            except Exception as e:
                print(f"[MS4BatchSender] Error closing loop: {e}")

        print("[MS4BatchSender] Processing loop stopped")

    async def _send_batch(self, batch: List[Dict]):
        """
        Sends a batch of payloads to the MS4 API with retry logic.
        """
        endpoint = "/batch-metadata"
        max_retries = 5
        base_delay = 1

        for attempt in range(max_retries):
            try:
                response = await self.client.post(endpoint, json=batch)
                response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes

                if response.status_code == 202:
                    print(f"[MS4BatchSender] Batch of {len(batch)} payloads accepted by MS4.")
                    return

            except httpx.HTTPStatusError as e:
                print(f"[MS4BatchSender] HTTP error on attempt {attempt + 1}: {e.response.status_code} - {e.response.text}")
                if e.response.status_code in [400, 401]:
                    # Non-recoverable errors, don't retry
                    break
                if e.response.status_code == 429:
                    # Rate limited, respect Retry-After header if present
                    retry_after = int(e.response.headers.get("Retry-After", base_delay))
                    print(f"[MS4BatchSender] Rate limited. Retrying after {retry_after} seconds.")
                    await asyncio.sleep(retry_after)
                else:
                    # Other transient errors, use exponential backoff
                    delay = base_delay * (2 ** attempt)
                    print(f"[MS4BatchSender] Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)

            except httpx.RequestError as e:
                print(f"[MS4BatchSender] Request error on attempt {attempt + 1}: {e}")
                delay = base_delay * (2 ** attempt)
                print(f"[MS4BatchSender] Retrying in {delay} seconds...")
                await asyncio.sleep(delay)

        print(f"[MS4BatchSender] Failed to send batch of {len(batch)} payloads after {max_retries} attempts.")


_ms4_batch_sender_instance = None

def get_ms4_batch_sender() -> MS4BatchSender:
    """Get singleton MS4BatchSender"""
    global _ms4_batch_sender_instance
    if _ms4_batch_sender_instance is None:
        _ms4_batch_sender_instance = MS4BatchSender()
    return _ms4_batch_sender_instance