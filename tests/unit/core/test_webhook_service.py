
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from core.webhook_service import WebhookService

@pytest.fixture
def webhook_service():
    """Fixture for WebhookService."""
    return WebhookService()

@pytest.mark.asyncio
async def test_fetch_email_detail_success(webhook_service, mocker):
    """Test that _fetch_email_detail successfully fetches email details."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "1", "subject": "Test Email"}

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=AsyncMock(status_code=200, json=lambda: mock_response.json.return_value))

    mocker.patch("httpx.AsyncClient", return_value=MagicMock(__aenter__=AsyncMock(return_value=mock_client), __aexit__=AsyncMock(return_value=False)))
    mocker.patch("core.token_manager.get_token", return_value="dummy_token")

    message = await webhook_service._fetch_email_detail("1")

    assert message is not None
    assert message["id"] == "1"
    mock_client.get.assert_called_once()

@pytest.mark.asyncio
async def test_create_subscription_success(webhook_service, mocker):
    """Test that _create_subscription successfully creates a subscription."""
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"id": "sub123"}

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=AsyncMock(status_code=201, json=lambda: mock_response.json.return_value))

    mocker.patch("httpx.AsyncClient", return_value=MagicMock(__aenter__=AsyncMock(return_value=mock_client), __aexit__=AsyncMock(return_value=False)))
    mocker.patch("core.token_manager.get_token", return_value="dummy_token")
    mocker.patch("concurrent_storage.redis_manager.RedisStorageManager.save_subscription")

    webhook_service.public_url = "https://dummy.ngrok.io"
    subscription_id = await webhook_service._create_subscription()

    assert subscription_id == "sub123"
    mock_client.post.assert_called_once()
