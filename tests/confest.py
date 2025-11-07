"""
conftest.py
Shared pytest fixtures and configuration
"""
import pytest
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture(scope="session", autouse=True)
def mock_env_and_redis(session_mocker):
    """Global fixture to mock environment variables and Redis connection."""
    session_mocker.patch.dict(os.environ, {"CLIENT_ID": "dummy_id", "CLIENT_SECRET": "dummy_secret"})
    session_mocker.patch("cache.redis_manager.RedisStorageManager", MagicMock())
    session_mocker.patch("cache.redis_manager.get_redis_storage", MagicMock())



@pytest.fixture(scope="session")
def test_config():
    """Test configuration"""
    return {
        "redis_host": os.getenv("TEST_REDIS_HOST", "localhost"),
        "redis_port": int(os.getenv("TEST_REDIS_PORT", "6379")),
        "redis_db": int(os.getenv("TEST_REDIS_DB", "15")),  # Use separate DB for tests
        "mock_token": "test_access_token_12345",
        "graph_api_url": "https://graph.microsoft.com/v1.0"
    }


@pytest.fixture(scope="function")
def redis_storage(test_config):
    """
    Redis storage fixture với safe cleanup
    Scope: function (mỗi test có instance riêng)
    
    KHÔNG xóa:
    - Session history (sessions:history, sessions:by_time)
    - Refresh token (auth:refresh_token)  
    - Webhook subscription (webhook:subscription)
    - Production processed emails tracking
    """
    from cache.redis_manager import RedisStorageManager
    
    # Create Redis instance with test DB
    redis = RedisStorageManager(
        host=test_config["redis_host"],
        port=test_config["redis_port"],
        db=test_config["redis_db"]
    )
    
    # Safe cleanup before test
    _safe_cleanup_test_data(redis)
    
    yield redis
    
    # Safe cleanup after test
    _safe_cleanup_test_data(redis)
    redis.close()


def _safe_cleanup_test_data(redis):
    """
    Safe cleanup - chỉ xóa test data, bảo vệ data quan trọng:
    ✅ GIỮ LẠI: Session history, Refresh token, Webhook subscription, Processed emails
    ❌ XÓA: Test emails, test queues, test sessions, test metrics
    """
    # 1. Xóa current session NẾU là test session
    session_data = redis.get_session_state()
    if session_data:
        session_id = session_data.get("session_id", "")
        if any(prefix in session_id for prefix in ["test_", "mock_", "lifecycle_", "perf_"]):
            redis.delete_session()
    
    # 2. Xóa test email data
    test_email_patterns = [
        "email:data:test_*",
        "email:data:mock_*",
        "email:data:batch_*",
        "email:data:perf_*",
        "email:data:enqueue_*",
        "email:data:dequeue_*",
        "email:data:concurrent_*",
        "email:data:e2e_*",
        "email:data:scale_*",
        "email:data:fallback_*",
        "email:data:lifecycle_*",
        "email:data:latency_*",
        "email:retry:test_*",
        "email:retry:mock_*",
        "email:retry:perf_*"
    ]
    
    for pattern in test_email_patterns:
        keys = redis.redis.keys(pattern)
        if keys:
            redis.redis.delete(*keys)
    
    # 3. Xóa test emails từ queues (chỉ test emails)
    queue_keys = ["queue:emails", "queue:processing", "queue:failed"]
    test_prefixes = ["test_", "mock_", "batch_", "perf_", "enqueue_", 
                     "dequeue_", "concurrent_", "e2e_", "scale_", 
                     "fallback_", "lifecycle_", "latency_"]
    
    for queue_key in queue_keys:
        all_items = redis.redis.zrange(queue_key, 0, -1)
        test_items = [item for item in all_items 
                     if any(prefix in item for prefix in test_prefixes)]
        if test_items:
            redis.redis.zrem(queue_key, *test_items)
    
    # 4. Xóa test emails từ processed set
    processed_items = redis.redis.smembers("email:processed")
    test_processed = [item for item in processed_items 
                     if any(prefix in item for prefix in test_prefixes)]
    if test_processed:
        redis.redis.srem("email:processed", *test_processed)
    
    # 5. Xóa test locks
    lock_keys = redis.redis.keys("lock:test_*")
    if lock_keys:
        redis.redis.delete(*lock_keys)
    
    # 6. Xóa test metrics và counters
    test_keys_patterns = ["metrics:test_*", "counter:test_*", "counter:perf_*"]
    for pattern in test_keys_patterns:
        keys = redis.redis.keys(pattern)
        if keys:
            redis.redis.delete(*keys)
    
    # ✅ KHÔNG XÓA (được bảo vệ):
    # - sessions:history (lịch sử các session)
    # - sessions:by_time (index sessions theo thời gian)
    # - auth:refresh_token (refresh token cache - QUAN TRỌNG!)
    # - webhook:subscription (subscription info - QUAN TRỌNG!)
    # - email:processed (processed emails tracking - có TTL tự động)
    # - Production session data
    # - Production metrics
    
    print("[Safe Cleanup] Test data cleaned, production data preserved")


@pytest.fixture(scope="function")
def email_queue(redis_storage):
    """Email queue fixture"""
    from core.queue_manager import EmailQueue
    return EmailQueue()


@pytest.fixture(scope="function")
def session_manager_instance(redis_storage):
    """Session manager fixture"""
    from core.session_manager import SessionManager
    return SessionManager()


@pytest.fixture(scope="function")
def mock_token(test_config):
    """Mock token manager"""
    with patch('core.token_manager.get_token') as mock:
        mock.return_value = test_config["mock_token"]
        yield mock


@pytest.fixture(scope="function")
def mock_graph_api_success():
    """Mock successful Graph API responses"""
    with patch('requests.get') as mock_get, \
         patch('requests.post') as mock_post, \
         patch('requests.patch') as mock_patch, \
         patch('requests.delete') as mock_delete:
        
        # Mock successful email fetch
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "value": [
                {
                    "id": "mock_email_1",
                    "subject": "Mock Email 1",
                    "from": {"emailAddress": {"address": "sender1@test.com"}},
                    "receivedDateTime": datetime.now(timezone.utc).isoformat(),
                    "isRead": False,
                    "hasAttachments": False,
                    "bodyPreview": "Mock body 1"
                },
                {
                    "id": "mock_email_2",
                    "subject": "Mock Email 2",
                    "from": {"emailAddress": {"address": "sender2@test.com"}},
                    "receivedDateTime": datetime.now(timezone.utc).isoformat(),
                    "isRead": False,
                    "hasAttachments": True,
                    "bodyPreview": "Mock body 2"
                }
            ],
            "@odata.nextLink": None
        }
        
        # Mock successful operations
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"id": "success"}
        
        mock_patch.return_value.status_code = 200
        mock_delete.return_value.status_code = 204
        
        yield {
            "get": mock_get,
            "post": mock_post,
            "patch": mock_patch,
            "delete": mock_delete
        }


@pytest.fixture(scope="function")
def mock_graph_api_error():
    """Mock Graph API error responses"""
    with patch('requests.get') as mock_get, \
         patch('requests.post') as mock_post:
        
        mock_get.side_effect = Exception("Graph API Connection Error")
        mock_post.side_effect = Exception("Graph API Connection Error")
        
        yield {
            "get": mock_get,
            "post": mock_post
        }


@pytest.fixture(scope="function")
def sample_emails():
    """Generate sample email data"""
    def _generate(count=10, prefix="test"):
        emails = []
        for i in range(count):
            email_id = f"{prefix}_email_{i}"
            email_data = {
                "id": email_id,
                "subject": f"Test Email {i}",
                "from": {"emailAddress": {"address": f"sender{i}@test.com"}},
                "receivedDateTime": datetime.now(timezone.utc).isoformat(),
                "isRead": False,
                "hasAttachments": i % 3 == 0,
                "bodyPreview": f"Test body preview {i}",
                "body": {
                    "content": f"<html><body>Test email body {i}</body></html>",
                    "contentType": "html"
                }
            }
            emails.append((email_id, email_data))
        return emails
    
    return _generate


@pytest.fixture(scope="function")
def mock_external_services():
    """Mock MS2 (Classifier) and MS4 (Persistence) services"""
    with patch('requests.post') as mock_post:
        # Mock successful responses from downstream services
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "status": "success",
            "message": "Received"
        }
        yield mock_post


@pytest.fixture(scope="function")
def polling_service_instance(mock_token):
    """Polling service fixture"""
    from core.polling_service import PollingService
    service = PollingService()
    yield service
    # Cleanup
    if service.active:
        service.stop()


@pytest.fixture(scope="function")
def webhook_service_instance(mock_token):
    """Webhook service fixture"""
    from core.webhook_service import WebhookService
    service = WebhookService()
    yield service
    # Cleanup
    if service.active:
        service.stop()


@pytest.fixture(scope="function")
def batch_processor_instance(mock_token, mock_external_services):
    """Batch processor fixture"""
    from core.batch_processor import BatchEmailProcessor
    processor = BatchEmailProcessor(batch_size=10, max_workers=5)
    yield processor
    # Cleanup
    if processor.active:
        processor.stop()


@pytest.fixture(scope="function")
def test_session_config():
    """Generate test session configuration"""
    from core.session_manager import SessionConfig
    import time
    
    return SessionConfig(
        session_id=f"test_session_{int(time.time())}",
        start_time=datetime.now(timezone.utc).isoformat(),
        polling_interval=300,
        webhook_enabled=True,
        polling_mode="scheduled",
        max_polling_errors=3,
        max_webhook_errors=5
    )


# Pytest hooks for custom behavior

def pytest_configure(config):
    """Configure pytest"""
    # Add custom markers
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as performance test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "redis: mark test as requiring Redis"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection"""
    # Auto-mark tests based on filename
    for item in items:
        if "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.redis)
        
        if "performance" in item.nodeid:
            item.add_marker(pytest.mark.performance)
            item.add_marker(pytest.mark.slow)
            item.add_marker(pytest.mark.redis)


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment (runs once per session)"""
    print("\n🔧 Setting up test environment...")
    
    # Set test environment variables
    os.environ["TESTING"] = "true"
    os.environ["LOG_LEVEL"] = "INFO"
    
    # Verify Redis is available
    try:
        from cache.redis_manager import RedisStorageManager
        test_redis = RedisStorageManager(db=15)
        test_redis.redis.ping()
        print("✅ Redis connection OK")
        test_redis.close()
    except Exception as e:
        pytest.exit(f"❌ Redis not available: {e}")
    
    yield
    
    print("\n🧹 Cleaning up test environment...")


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton instances between tests"""
    # Reset global instances to avoid state leakage
    import core.queue_manager as qm
    import core.batch_processor as bp
    
    qm._queue_instance = None
    bp._batch_processor_instance = None
    
    yield


# Performance testing helpers

@pytest.fixture
def benchmark_timer():
    """Simple benchmark timer"""
    import time
    
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = time.time()
        
        def stop(self):
            self.end_time = time.time()
        
        @property
        def elapsed(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return 0
    
    return Timer()


@pytest.fixture
def performance_metrics():
    """Collect performance metrics"""
    metrics = {
        "throughput": [],
        "latency": [],
        "errors": 0
    }
    
    return metrics