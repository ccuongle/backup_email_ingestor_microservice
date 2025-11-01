
import pytest
from unittest.mock import MagicMock, patch
from core.polling_service import PollingService

@pytest.fixture
def polling_service():
    """Fixture for PollingService."""
    return PollingService()

def test_fetch_unread_emails_success(polling_service, mocker):
    """Test that _fetch_unread_emails successfully fetches and processes emails."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "value": [{"id": "1", "subject": "Test Email"}],
        "@odata.nextLink": None,
    }

    mock_client = MagicMock()
    mock_client.get.return_value = mock_response

    mocker.patch("httpx.Client", return_value=MagicMock(__enter__=MagicMock(return_value=mock_client), __exit__=MagicMock()))
    mocker.patch("core.token_manager.get_token", return_value="dummy_token")

    messages = polling_service._fetch_unread_emails()

    assert len(messages) == 1
    assert messages[0]["id"] == "1"
    mock_client.get.assert_called_once()

def test_batch_mark_as_read_success(polling_service, mocker):
    """Test that _batch_mark_as_read successfully marks emails as read."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response

    mocker.patch("httpx.Client", return_value=MagicMock(__enter__=MagicMock(return_value=mock_client), __exit__=MagicMock()))
    mocker.patch("core.token_manager.get_token", return_value="dummy_token")

    polling_service._batch_mark_as_read(["1", "2"])

    mock_client.post.assert_called_once()
