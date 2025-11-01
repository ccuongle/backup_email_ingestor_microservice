import pytest
from unittest.mock import MagicMock, patch
from core.polling_service import PollingService
from core.webhook_service import WebhookService

@pytest.fixture
def polling_service():
    """Fixture for PollingService."""
    return PollingService()

@pytest.fixture
def webhook_service():
    """Fixture for WebhookService."""
    return WebhookService()

def test_polling_service_rate_limit(polling_service, mocker):
    """Test that PollingService pauses and retries when rate limit is exceeded."""
    mock_redis = MagicMock()
    mock_redis.check_rate_limit.side_effect = [(False, 110), (True, 10)]
    polling_service.redis = mock_redis

    mocker.patch("time.sleep")  # To avoid actual sleep

    with patch.object(polling_service, '_stop_event') as mock_stop_event:
        mock_stop_event.wait.return_value = False
        polling_service._check_and_wait_for_rate_limit()

    assert mock_redis.check_rate_limit.call_count == 2
    mock_stop_event.wait.assert_called_once()

def test_webhook_service_rate_limit(webhook_service, mocker):
    """Test that WebhookService pauses and retries when rate limit is exceeded."""
    mock_redis = MagicMock()
    mock_redis.check_rate_limit.side_effect = [(False, 110), (True, 10)]
    webhook_service.redis = mock_redis

    mocker.patch("time.sleep")  # To avoid actual sleep

    with patch.object(webhook_service, '_stop_event') as mock_stop_event:
        mock_stop_event.wait.return_value = False
        webhook_service._check_and_wait_for_rate_limit()

    assert mock_redis.check_rate_limit.call_count == 2
    mock_stop_event.wait.assert_called_once()
