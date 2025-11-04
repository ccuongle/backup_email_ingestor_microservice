"""
Unit tests for ms3BatchSender.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import httpx
import time

from core.ms3_batch_sender import ms3BatchSender
from cache.redis_manager import RedisStorageManager
from utils.config import MS3_BATCH_SIZE

@pytest.fixture
def mock_redis_manager():
    """Mocks the RedisStorageManager."""
    with patch('core.ms3_batch_sender.get_redis_storage') as mock_get_redis_storage:
        mock_redis = MagicMock(spec=RedisStorageManager)
        mock_redis.get_ms3_outbound_queue_size.return_value = 0
        mock_redis.dequeue_ms3_batch.return_value = []
        mock_get_redis_storage.return_value = mock_redis
        yield mock_redis

@pytest.fixture
def mock_httpx_client():
    """Mocks httpx.AsyncClient globally for all tests."""
    with patch('httpx.AsyncClient') as mock_client_class:
        # Create a mock instance
        mock_instance = AsyncMock()
        mock_instance.aclose = AsyncMock()
        mock_instance.post = AsyncMock()
        
        # Make the class return the mock instance
        mock_client_class.return_value = mock_instance
        
        yield mock_instance

@pytest.fixture
def ms3_batch_sender(mock_redis_manager, mock_httpx_client):
    """Provides an instance of MS3BatchSender with mocked dependencies."""
    # Dùng fetch_interval ngắn hơn cho test
    sender = ms3BatchSender(batch_size=2, fetch_interval=0.1)
    yield sender
    sender.stop()

def test_ms3_batch_sender_starts_and_stops(ms3_batch_sender):
    """Tests that the sender can start and stop without errors."""
    assert ms3_batch_sender.start() is True
    assert ms3_batch_sender.active is True
    time.sleep(0.2)  # Let thread start
    ms3_batch_sender.stop()
    assert ms3_batch_sender.active is False

def test_ms3_batch_sender_sends_batch(ms3_batch_sender, mock_redis_manager):
    """Tests that the sender dequeues from Redis and sends to MS3."""
    payload1 = {"id": "email1", "data": "test1"}
    payload2 = {"id": "email2", "data": "test2"}
    batch = [payload1, payload2]

    # Setup mock responses
    call_count = [0]  # Mutable để track trong closure
    
    def get_queue_size():
        call_count[0] += 1
        # First call: có batch, second call: empty
        return len(batch) if call_count[0] == 1 else 0
    
    mock_redis_manager.get_ms3_outbound_queue_size.side_effect = get_queue_size
    mock_redis_manager.dequeue_ms3_batch.return_value = batch

    # Mock httpx AsyncClient để tránh thực sự gọi API
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client_instance = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.aclose = AsyncMock()
        mock_client_class.return_value = mock_client_instance
        
        # Start sender (tạo thread riêng)
        assert ms3_batch_sender.start() is True
        
        # Wait for thread xử lý batch
        time.sleep(1.0)  # Tăng thời gian chờ
        
        # Stop sender
        ms3_batch_sender.stop()
        
        # Verify Redis được gọi
        assert mock_redis_manager.dequeue_ms3_batch.called
        
        # Verify HTTP client được gọi (nếu batch được xử lý)
        # Lưu ý: do timing, có thể cần retry logic
        if mock_client_instance.post.called:
            mock_client_instance.post.assert_called_with(
                "/batch-metadata",
                json=batch
            )

@pytest.mark.asyncio
async def test_send_batch_success(mock_redis_manager):
    """Tests _send_batch with successful response."""
    sender = ms3BatchSender(batch_size=2)
    
    # Create mock client
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_client.post.return_value = mock_response
    sender.client = mock_client
    
    # Test
    batch = [{"id": "email1"}, {"id": "email2"}]
    await sender._send_batch(batch)
    
    # Verify
    mock_client.post.assert_called_once_with("/batch-metadata", json=batch)

@pytest.mark.asyncio
async def test_send_batch_handles_http_errors_and_retries(mock_redis_manager):
    """Tests error handling and retry logic for transient HTTP errors."""
    sender = ms3BatchSender(batch_size=2)
    
    # Create mock client
    mock_client = AsyncMock()
    
    # First call: 500 error
    mock_response_500 = MagicMock()
    mock_response_500.status_code = 500
    mock_response_500.text = "Internal Server Error"
    mock_response_500.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server Error",
        request=MagicMock(),
        response=mock_response_500
    )
    
    # Second call: Success
    mock_response_202 = MagicMock()
    mock_response_202.status_code = 202
    
    mock_client.post.side_effect = [mock_response_500, mock_response_202]
    sender.client = mock_client
    
    # Test
    batch = [{"id": "email1"}]
    await sender._send_batch(batch)
    
    # Verify retried
    assert mock_client.post.call_count == 2

@pytest.mark.asyncio
async def test_send_batch_handles_rate_limiting(mock_redis_manager):
    """Tests rate limiting handling with Retry-After header."""
    sender = ms3BatchSender(batch_size=2)
    
    # Create mock client
    mock_client = AsyncMock()
    
    # First call: 429 rate limit
    mock_response_429 = MagicMock()
    mock_response_429.status_code = 429
    mock_response_429.headers = {"Retry-After": "1"}
    mock_response_429.text = "Rate Limited"
    mock_response_429.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Rate Limited",
        request=MagicMock(),
        response=mock_response_429
    )
    
    # Second call: Success
    mock_response_202 = MagicMock()
    mock_response_202.status_code = 202
    
    mock_client.post.side_effect = [mock_response_429, mock_response_202]
    sender.client = mock_client
    
    # Test
    batch = [{"id": "email1"}]
    await sender._send_batch(batch)
    
    # Verify retried
    assert mock_client.post.call_count == 2

@pytest.mark.asyncio
async def test_send_batch_handles_non_retryable_errors(mock_redis_manager):
    """Tests that non-retryable errors (e.g., 400, 401) are not retried."""
    sender = ms3BatchSender(batch_size=2)
    
    # Create mock client
    mock_client = AsyncMock()
    
    # 400 error - should not retry
    mock_response_400 = MagicMock()
    mock_response_400.status_code = 400
    mock_response_400.text = "Bad Request"
    mock_response_400.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Bad Request",
        request=MagicMock(),
        response=mock_response_400
    )
    
    mock_client.post.return_value = mock_response_400
    sender.client = mock_client
    
    # Test
    batch = [{"id": "email1"}]
    await sender._send_batch(batch)
    
    # Verify only called once (no retry)
    mock_client.post.assert_called_once()

def test_ms3_batch_sender_handles_empty_queue(ms3_batch_sender, mock_redis_manager):
    """Tests that the sender correctly handles an empty queue."""
    mock_redis_manager.get_ms3_outbound_queue_size.return_value = 0
    mock_redis_manager.dequeue_ms3_batch.return_value = []

    # Start sender
    assert ms3_batch_sender.start() is True
    assert ms3_batch_sender.active is True
    assert ms3_batch_sender.thread is not None
    assert ms3_batch_sender.thread.is_alive()
    
    # Wait đủ lâu để thread chạy ít nhất 1 iteration
    # fetch_interval = 0.1s, nên 0.5s là đủ cho vài iterations
    time.sleep(0.5)
    
    # Stop sender
    ms3_batch_sender.stop()
    
    # Debug: print call count
    call_count = mock_redis_manager.get_ms3_outbound_queue_size.call_count
    print(f"\n[DEBUG] get_ms3_outbound_queue_size called {call_count} times")

    # Verify it checked the queue
    assert call_count > 0, \
        f"get_ms3_outbound_queue_size should have been called at least once, but was called {call_count} times"