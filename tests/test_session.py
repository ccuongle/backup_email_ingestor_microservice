"""
Integration Tests for Email Ingestion Microservice
Tests polling, hybrid ingestion, and fallback scenarios
"""
import pytest
import time
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict
import httpx

# Import components to test
from core.polling_service import PollingService, TriggerMode
from core.webhook_service import WebhookService
from core.batch_processor import BatchEmailProcessor
from core.queue_manager import EmailQueue
from core.session_manager import SessionManager, SessionState, SessionConfig
from concurrent_storage.redis_manager import RedisStorageManager




@pytest.fixture
def redis_storage():
    """Fixture cung cấp Redis storage với cleanup an toàn"""
    redis = RedisStorageManager()
    # Safe cleanup - chỉ xóa test data
    _safe_cleanup_test_data(redis, full = True)
    yield redis
    # Cleanup after test
    _safe_cleanup_test_data(redis, full = True)


def _safe_cleanup_test_data(redis: RedisStorageManager, dry_run=False, full=False):
    """
    Safe cleanup - chỉ xóa test data.
    Nếu full=True, xóa thêm cả email:processed để tránh skipped email.
    """
    redis.delete_session()

    # --- 1️⃣ Xóa email data ---
    test_patterns = [
        "email:processed:*",
        "email:pending:*",
        "email:failed:*"
    ]
    if full:
        test_patterns.append("email:processed")  # Xóa set tổng khi full cleanup

    for pattern in test_patterns:
        keys = redis.redis.keys(pattern)
        if keys:
            print(f"🧹 Cleaning {len(keys)} keys matching '{pattern}'")
            if not dry_run:
                redis.redis.delete(*keys)
    
    # --- 2️⃣ Xóa queue test emails ---
    queue_keys = ["queue:emails", "queue:processing", "queue:failed"]
    test_prefixes = [
        "test_", "mock_", "batch_", "perf_", "enqueue_",
        "dequeue_", "concurrent_", "e2e_", "scale_",
        "fallback_", "lifecycle_"
    ]

    for q in queue_keys:
        all_items = redis.redis.zrange(q, 0, -1)
        test_items = [e for e in all_items if any(prefix in e for prefix in test_prefixes)]
        if test_items:
            print(f"🧹 Removed {len(test_items)} test items from {q}")
            if not dry_run:
                redis.redis.zrem(q, *test_items)

    # --- 3️⃣ Xóa lock, metrics, counter test data ---
    for pattern in ["lock:test_*", "metrics:test_*", "counter:test_*", "ratelimit:test_*"]:
        keys = redis.redis.keys(pattern)
        if keys:
            print(f"🧹 Cleaning {len(keys)} keys matching '{pattern}'")
            if not dry_run:
                redis.redis.delete(*keys)

    print(f"[Test Cleanup] Cleaned test data safely (full={full})")

@pytest.fixture
def email_queue(redis_storage):
    """Fixture cung cấp EmailQueue"""
    return EmailQueue()


@pytest.fixture
def session_manager_instance(redis_storage):
    """Fixture cung cấp SessionManager"""
    return SessionManager()


@pytest.fixture
def mock_graph_api():
    """Mock Microsoft Graph API responses"""
    with patch('httpx.Client') as mock_httpx_client:
            mock_client_instance = MagicMock()
            mock_httpx_client.return_value.__enter__.return_value = mock_client_instance
            
            # Mock email fetch response
            mock_client_instance.get.return_value.status_code = 200
            mock_client_instance.get.return_value.json.return_value = {
                "value": [
                    {
                        "id": "test_email_1",
                        "subject": "Test Email 1",
                        "from": {"emailAddress": {"address": "sender1@test.com"}},
                        "receivedDateTime": datetime.now(timezone.utc).isoformat(),
                        "isRead": False,
                        "hasAttachments": False,
                        "bodyPreview": "Test body preview 1"
                    },
                    {
                        "id": "test_email_2",
                        "subject": "Test Email 2",
                        "from": {"emailAddress": {"address": "sender2@test.com"}},
                        "receivedDateTime": datetime.now(timezone.utc).isoformat(),
                        "isRead": False,
                        "hasAttachments": True,
                        "bodyPreview": "Test body preview 2"
                    }
                ],
                "@odata.nextLink": None
            }
            
            # Mock mark as read
            mock_client_instance.patch.return_value.status_code = 200
            
            # Mock batch mark as read
            mock_client_instance.post.return_value.status_code = 200
            mock_client_instance.post.return_value.json.return_value = {
                "responses": [
                    {"id": "1", "status": 200},
                    {"id": "2", "status": 200}
                ]
            }
            
            yield {
                "get": mock_client_instance.get,
                "post": mock_client_instance.post,
                "patch": mock_client_instance.patch
            }


@pytest.fixture
def mock_token():
    """Mock token manager"""
    with patch('core.token_manager.get_token') as mock:
        mock.return_value = "mock_access_token_12345"
        yield mock


class TestPollingOnce:
    """Test trường hợp polling một lần (manual trigger)"""
    
    def test_polling_once_success(self, redis_storage, email_queue, mock_graph_api, mock_token):
        """Test polling thành công và enqueue emails"""
        # Setup
        polling_service = PollingService()
        
        # Execute
        result = polling_service.poll_once()
        
        # Verify
        assert result["status"] == "success"
        assert result["emails_found"] == 2
        assert result["enqueued"] == 2
        assert result["skipped"] == 0
        
        # Verify queue
        queue_stats = email_queue.get_stats()
        assert queue_stats["queue_size"] == 2
        
        # Verify emails in queue
        emails = email_queue.dequeue_batch(10)
        assert len(emails) == 2
        assert emails[0][0] == "test_email_1"
        assert emails[1][0] == "test_email_2"
        
        print("✅ Test polling once success - PASSED")
    
    def test_polling_once_duplicate_skip(self, redis_storage, email_queue, 
                                         session_manager_instance, mock_graph_api, mock_token):
        """Test polling bỏ qua emails đã processed"""
        # Setup - mark one email as processed
        session_manager_instance.register_processed_email("test_email_1")
        
        polling_service = PollingService()
        
        # Execute
        result = polling_service.poll_once()
        
        # Verify
        assert result["status"] == "success"
        assert result["emails_found"] == 2
        assert result["enqueued"] == 1  # Chỉ enqueue email 2
        assert result["skipped"] == 1   # Skip email 1
        
        print("✅ Test polling duplicate skip - PASSED")
    
    def test_polling_once_no_emails(self, redis_storage, email_queue, mock_token):
        """Test polling khi không có email mới"""
        # Setup - mock empty response
        with patch('httpx.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "value": [],
                "@odata.nextLink": None
            }
            
            polling_service = PollingService()
            
            # Execute
            result = polling_service.poll_once()
            
            # Verify
            assert result["status"] == "success"
            assert result["emails_found"] == 0
            assert result["enqueued"] == 0
            
        print("✅ Test polling no emails - PASSED")
    
    def test_polling_once_api_error(self, redis_storage, email_queue, mock_token):
        """Test polling xử lý lỗi API"""
        with patch('httpx.Client') as mock_httpx_client:
            mock_client_instance = MagicMock()
            mock_httpx_client.return_value.__enter__.return_value = mock_client_instance
            mock_client_instance.get.side_effect = httpx.RequestError("API Connection Error", request=MagicMock())
            
            polling_service = PollingService()
            
            # Execute
            result = polling_service.poll_once()
            
            # Verify
            assert result["status"] == "error"
            assert "API Connection Error" in result["error"]
            assert result["enqueued"] == 0
            
        print("✅ Test polling API error - PASSED")


class TestHybridIngestion:
    """Test trường hợp hybrid: Polling initial + Webhook active"""
    
    def test_hybrid_initial_polling_then_webhook(self, redis_storage, email_queue, 
                                                  session_manager_instance, mock_graph_api, mock_token):
        """Test luồng hybrid: polling ban đầu -> chuyển sang webhook"""
        # Step 1: Start session in BOTH_ACTIVE mode
        config = SessionConfig(
            session_id=f"test_session_{int(time.time())}",
            start_time=datetime.now(timezone.utc).isoformat(),
            webhook_enabled=True,
            polling_mode=TriggerMode.SCHEDULED.value,
            polling_interval=300
        )
        
        session_manager_instance.start_session(config)
        
        # Verify initial state
        status = session_manager_instance.get_session_status()
        assert status["state"] == SessionState.BOTH_ACTIVE.value
        
        print("✅ Step 1: Session started in BOTH_ACTIVE mode")
        
        # Step 2: Perform initial polling
        polling_service = PollingService()
        result = polling_service.poll_once()
        
        assert result["status"] == "success"
        assert result["enqueued"] == 2
        
        print("✅ Step 2: Initial polling completed, 2 emails enqueued")
        
        # Step 3: Complete initial polling phase
        success = session_manager_instance.complete_initial_polling()
        assert success is True
        
        status = session_manager_instance.get_session_status()
        assert status["state"] == SessionState.WEBHOOK_ACTIVE.value
        
        print("✅ Step 3: Transitioned to WEBHOOK_ACTIVE mode")
        
        # Step 4: Simulate webhook notification
        webhook_service = WebhookService()
        
        # Mock webhook notification data
        notification_data = {
            "value": [
                {
                    "subscriptionId": "test_sub_123",
                    "clientState": "webhook_secret_state",
                    "changeType": "created",
                    "resource": "me/mailfolders('inbox')/messages/test_email_3",
                    "resourceData": {
                        "id": "test_email_3"
                    }
                }
            ]
        }
        
        # Mock fetch email detail
        with patch.object(webhook_service, '_fetch_email_detail') as mock_fetch:
            mock_fetch.return_value = {
                "id": "test_email_3",
                "subject": "Webhook Email 3",
                "from": {"emailAddress": {"address": "webhook@test.com"}},
                "receivedDateTime": datetime.now(timezone.utc).isoformat(),
                "hasAttachments": False,
                "bodyPreview": "Webhook test"
            }
            
            # Mock mark as read
            with patch.object(webhook_service, '_mark_as_read'):
                result = webhook_service.handle_notification(notification_data)
        
        assert result["status"] == "success"
        assert result["enqueued"] == 1
        
        print("✅ Step 4: Webhook notification processed successfully")
        
        # Verify queue has all emails
        queue_stats = email_queue.get_stats()
        assert queue_stats["queue_size"] == 3  # 2 from polling + 1 from webhook
        
        print("✅ Test hybrid ingestion - PASSED")
    
    def test_hybrid_webhook_duplicate_skip(self, redis_storage, email_queue, 
                                           session_manager_instance, mock_token):
        """Test webhook bỏ qua email đã được polling xử lý"""
        # Setup: Mark email as processed from polling
        session_manager_instance.register_processed_email("test_email_1")
        
        webhook_service = WebhookService()
        
        # Simulate webhook notification for same email
        notification_data = {
            "value": [
                {
                    "resourceData": {"id": "test_email_1"}
                }
            ]
        }
        
        result = webhook_service.handle_notification(notification_data)
        
        # Verify: Should skip (0 enqueued)
        assert result["status"] == "success"
        assert result["enqueued"] == 0
        
        print("✅ Test hybrid duplicate skip - PASSED")


class TestFallbackNoWebhook:
    """Test trường hợp fallback: Webhook fail -> Polling takes over"""
    
    def test_fallback_activation_on_webhook_errors(self, redis_storage, session_manager_instance, mock_token):
        """Test kích hoạt fallback khi webhook có nhiều lỗi"""
        # Step 1: Start in WEBHOOK_ACTIVE mode
        config = SessionConfig(
            session_id=f"test_session_{int(time.time())}",
            start_time=datetime.now(timezone.utc).isoformat(),
            webhook_enabled=True,
            max_webhook_errors=3
        )
        
        session_manager_instance.start_session(config)
        session_manager_instance.complete_initial_polling()
        
        status = session_manager_instance.get_session_status()
        assert status["state"] == SessionState.WEBHOOK_ACTIVE.value
        
        print("✅ Step 1: Started in WEBHOOK_ACTIVE mode")
        
        # Step 2: Simulate webhook errors
        webhook_service = WebhookService()
        webhook_service.error_count = 5  # Exceed max_errors
        
        # Activate fallback manually (normally done by webhook service)
        success = session_manager_instance.activate_fallback_polling(
            reason="webhook_errors_5"
        )
        
        assert success is True
        status = session_manager_instance.get_session_status()
        assert status["state"] == SessionState.BOTH_ACTIVE.value
        
        print("✅ Step 2: Fallback activated, now in BOTH_ACTIVE mode")
        
        # Step 3: Verify polling can now work
        with patch('httpx.Client') as mock_httpx_client:
            mock_client_instance = MagicMock()
            mock_httpx_client.return_value.__enter__.return_value = mock_client_instance
            mock_client_instance.get.return_value.status_code = 200
            mock_client_instance.get.return_value.json.return_value = {
                "value": [
                    {
                        "id": "fallback_email_1",
                        "subject": "Fallback Email",
                        "from": {"emailAddress": {"address": "fallback@test.com"}},
                        "receivedDateTime": datetime.now(timezone.utc).isoformat(),
                        "isRead": False,
                        "hasAttachments": False
                    }
                ],
                "@odata.nextLink": None
            }
            
            # Mock batch mark as read
            with patch.object(mock_client_instance, 'post') as mock_post:
                mock_post.return_value.status_code = 200
                
                polling_service = PollingService()
                result = polling_service.poll_once()
        
        assert result["status"] == "success"
        assert result["enqueued"] == 1
        
        print("✅ Step 3: Fallback polling working successfully")
        print("✅ Test fallback activation - PASSED")
    
    def test_fallback_restore_webhook(self, redis_storage, session_manager_instance):
        """Test khôi phục webhook sau khi fallback"""
        # Setup: In BOTH_ACTIVE (fallback) mode
        config = SessionConfig(
            session_id=f"test_session_{int(time.time())}",
            start_time=datetime.now(timezone.utc).isoformat(),
            webhook_enabled=True
        )
        
        session_manager_instance.start_session(config)
        session_manager_instance.complete_initial_polling()
        session_manager_instance.activate_fallback_polling("test_reason")
        
        status = session_manager_instance.get_session_status()
        assert status["state"] == SessionState.BOTH_ACTIVE.value
        
        print("✅ Setup: In fallback mode (BOTH_ACTIVE)")
        
        # Restore webhook
        success = session_manager_instance.restore_webhook_only()
        assert success is True
        
        status = session_manager_instance.get_session_status()
        assert status["state"] == SessionState.WEBHOOK_ACTIVE.value
        assert status["webhook_errors"] == 0
        
        print("✅ Test fallback restore - PASSED")


class TestBatchProcessing:
    """Test batch processing của emails từ queue"""
    
    def test_batch_processor_processes_queue(self, redis_storage, email_queue, 
                                             session_manager_instance, mock_token):
        """Test BatchProcessor xử lý emails từ queue"""
        # Setup: Add emails to queue
        emails = [
            ("batch_email_1", {
                "id": "batch_email_1",
                "subject": "Batch Test 1",
                "from": {"emailAddress": {"address": "batch1@test.com"}},
                "receivedDateTime": datetime.now(timezone.utc).isoformat(),
                "hasAttachments": False
            }, None),
            ("batch_email_2", {
                "id": "batch_email_2",
                "subject": "Batch Test 2",
                "from": {"emailAddress": {"address": "batch2@test.com"}},
                "receivedDateTime": datetime.now(timezone.utc).isoformat(),
                "hasAttachments": False
            }, None)
        ]
        
        enqueued = email_queue.enqueue_batch(emails)
        assert len(enqueued) == 2
        
        print("✅ Setup: 2 emails enqueued")
        
        # Mock MS2 and MS4 endpoints
        with patch('httpx.post') as mock_post:
            mock_post.return_value.status_code = 200
            
            # Create processor
            processor = BatchEmailProcessor(batch_size=10, max_workers=5)
            processor.start()  

            # Dequeue and process
            batch = email_queue.dequeue_batch(10)
            result = processor._process_batch_parallel(batch)
        
        # Verify
        assert result["success"] == 2
        assert result["failed"] == 0
        
        # Verify processed
        assert session_manager_instance.is_email_processed("batch_email_1")
        assert session_manager_instance.is_email_processed("batch_email_2")
        
        print("✅ Test batch processing - PASSED")


class TestSessionLifecycle:
    """Test vòng đời của session"""
    
    def test_complete_session_lifecycle(self, redis_storage, session_manager_instance, mock_token):
        """Test vòng đời hoàn chỉnh của session"""
        config = SessionConfig(
            session_id=f"lifecycle_test_{int(time.time())}",
            start_time=datetime.now(timezone.utc).isoformat(),
            webhook_enabled=True
        )

        # Step 1: Start session
        success = session_manager_instance.start_session(config)
        assert success is True
        status = session_manager_instance.get_session_status()
        assert status["state"] == SessionState.BOTH_ACTIVE.value
        print("✅ Step 1: Session started")

        # Step 2: Process some emails
        session_manager_instance.register_processed_email("email_1")
        session_manager_instance.register_processed_email("email_2")
        status = session_manager_instance.get_session_status()
        assert status["processed_count"] == 2
        print("✅ Step 2: Processed 2 emails")

        # Step 3: Complete initial polling
        session_manager_instance.complete_initial_polling()
        status = session_manager_instance.get_session_status()
        assert status["state"] == SessionState.WEBHOOK_ACTIVE.value
        print("✅ Step 3: Completed initial polling")

        # Step 4: Terminate session
        session_manager_instance.terminate_session("test_complete")

        # ✅ Đọc lại từ Redis thay vì gọi get_session_status()
        history = redis_storage.get_session_history(limit=1)
        assert len(history) == 1
        last_session = history[0]
        assert last_session["session_id"] == config.session_id
        assert last_session["state"] == SessionState.TERMINATED.value

        print("✅ Step 4: Session terminated and saved to history")
        print("✅ Test complete session lifecycle - PASSED")


# Run all tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])