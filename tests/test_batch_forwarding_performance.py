"""
Performance tests for batch forwarding to MS4.
"""
import pytest
import time
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from core.batch_processor import get_batch_processor
from core.ms4_batch_sender import get_ms4_batch_sender
from core.queue_manager import get_email_queue
from cache.redis_manager import get_redis_storage
from tests.test_performance import generate_test_emails, _safe_cleanup_test_data

@pytest.fixture(scope="module")
def redis_storage_module():
    """Module-scoped Redis storage fixture with cleanup."""
    redis = get_redis_storage()
    _safe_cleanup_test_data(redis, full=True)
    yield redis
    _safe_cleanup_test_data(redis, full=True)

@pytest.fixture
def email_queue_fixture(redis_storage_module):
    """Fixture to get the email queue."""
    return get_email_queue()

@patch("core.token_manager.get_token", return_value="mock_token")
@patch("httpx.AsyncClient")
def test_batch_forwarding_throughput(mock_async_client, mock_get_token, redis_storage_module, email_queue_fixture):
    """Tests the end-to-end throughput of batch forwarding to MS4."""
    total_emails = 1000
    batch_size = 50
    
    # Mock the async client
    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_async_client.return_value.post = AsyncMock(return_value=mock_response)

    # Start services
    batch_processor = get_batch_processor()
    ms4_sender = get_ms4_batch_sender()
    batch_processor.start()
    ms4_sender.start()

    try:
        # Enqueue emails
        emails = generate_test_emails(total_emails, "perf_batch_fwd")
        email_queue_fixture.enqueue_batch(emails)

        start_time = time.time()

        # Wait for all emails to be processed and sent
        while batch_processor.get_stats()["emails_success"] < total_emails or redis_storage_module.get_ms4_outbound_queue_size() > 0:
            print(f"Waiting... Processed: {batch_processor.get_stats()['emails_success']}, Outbound Queue: {redis_storage_module.get_ms4_outbound_queue_size()}")
            time.sleep(1)
            if time.time() - start_time > 120: # 2 minute timeout
                pytest.fail("Test timed out.")

        end_time = time.time()
        total_time = end_time - start_time
        throughput = total_emails / total_time if total_time > 0 else 0
        print(f"\n--- Batch Forwarding Performance --- ")
        print(f"Total emails: {total_emails}")
        print(f"Total time: {total_time:.2f}s")
        print(f"Throughput: {throughput:.2f} emails/s")

        # Assert a minimum throughput
        assert throughput > 30, "Throughput should be at least 30 emails/s"

    finally:
        batch_processor.stop()
        ms4_sender.stop()
