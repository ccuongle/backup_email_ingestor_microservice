
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

# Mock the orchestrator and redis_manager before importing the app
with patch('main_orchestrator.orchestrator', new_callable=AsyncMock) as mock_orchestrator, \
     patch('cache.redis_manager.get_redis_storage') as mock_get_redis_storage:
    
    from api.ms1_apiHanlder import app

    # Configure the mock for get_redis_storage
    mock_redis = AsyncMock()
    mock_get_redis_storage.return_value = mock_redis

    @pytest.fixture
    def client():
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def reset_mocks():
        mock_redis.reset_mock()
        mock_orchestrator.reset_mock()

    # Tests for /health endpoint
    def test_health_check_healthy(client):
        mock_redis.check_redis_connection = AsyncMock(return_value=True)
        
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
        mock_redis.check_redis_connection.assert_awaited_once()

    def test_health_check_unhealthy(client):
        mock_redis.check_redis_connection = AsyncMock(return_value=False)
        
        response = client.get("/health")
        
        assert response.status_code == 503
        assert response.json() == {"status": "unhealthy", "dependencies": {"redis": "unhealthy"}}
        mock_redis.check_redis_connection.assert_awaited_once()

    # Tests for /metrics endpoint
    def test_get_metrics_success(client):
        mock_redis.get_total_emails_processed = AsyncMock(return_value=123)
        mock_redis.get_total_emails_failed = AsyncMock(return_value=4)
        mock_redis.get_inbound_queue_size = AsyncMock(return_value=56)
        
        response = client.get("/metrics")
        
        assert response.status_code == 200
        assert response.json() == {
            "emails_processed": 123,
            "emails_failed": 4,
            "current_queue_size": 56
        }
        mock_redis.get_total_emails_processed.assert_awaited_once()
        mock_redis.get_total_emails_failed.assert_awaited_once()
        mock_redis.get_inbound_queue_size.assert_awaited_once()

    def test_get_metrics_zero_values(client):
        mock_redis.get_total_emails_processed = AsyncMock(return_value=0)
        mock_redis.get_total_emails_failed = AsyncMock(return_value=0)
        mock_redis.get_inbound_queue_size = AsyncMock(return_value=0)
        
        response = client.get("/metrics")
        
        assert response.status_code == 200
        assert response.json() == {
            "emails_processed": 0,
            "emails_failed": 0,
            "current_queue_size": 0
        }

