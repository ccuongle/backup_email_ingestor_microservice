
import pytest
from unittest.mock import MagicMock, patch
from core.webhook_service import WebhookService

@pytest.fixture
def webhook_service():
    """Fixture for WebhookService."""
    return WebhookService()

def test_fetch_email_detail_success(webhook_service, mocker):
    """Test that _fetch_email_detail successfully fetches email details."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "1", "subject": "Test Email"}

    mock_client = MagicMock()
    mock_client.get.return_value = mock_response

    mocker.patch("httpx.Client", return_value=MagicMock(__enter__=MagicMock(return_value=mock_client), __exit__=MagicMock()))
    mocker.patch("core.token_manager.get_token", return_value="dummy_token")

    message = webhook_service._fetch_email_detail("1")

    assert message is not None
    assert message["id"] == "1"
    mock_client.get.assert_called_once()

def test_create_subscription_success(webhook_service, mocker):
    """Test that _create_subscription successfully creates a subscription."""
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"id": "sub123"}

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response

    mocker.patch("httpx.Client", return_value=MagicMock(__enter__=MagicMock(return_value=mock_client), __exit__=MagicMock()))
    mocker.patch("core.token_manager.get_token", return_value="dummy_token")
    mocker.patch("concurrent_storage.redis_manager.RedisStorageManager.save_subscription")

    webhook_service.public_url = "https://dummy.ngrok.io"
    subscription_id = webhook_service._create_subscription()

    assert subscription_id == "sub123"
    mock_client.post.assert_called_once()
