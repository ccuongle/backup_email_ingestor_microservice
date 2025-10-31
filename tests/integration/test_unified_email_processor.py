from unittest.mock import MagicMock, patch
import pytest
from core.unified_email_processor import EmailProcessor

@pytest.fixture
def email_processor():
    return EmailProcessor(token="test_token")

def test_forward_to_persistence_uses_httpx(email_processor):
    """Tests that _forward_to_persistence uses httpx to send data to MS4."""
    mock_post = MagicMock()
    email_processor.client.post = mock_post
    mock_post.return_value.status_code = 200

    message = {
        "id": "test_id",
        "subject": "test_subject",
        "hasAttachments": False,
        "from": {"emailAddress": {"address": "sender@example.com"}},
        "receivedDateTime": "2025-10-31T10:00:00Z"
    }

    email_processor._forward_to_persistence(message)

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert 'metadata' in args[0]
    assert kwargs['json']['id'] == 'test_id'
