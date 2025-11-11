"""
tests/unit/core/test_polling_service.py - Fixed version
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from core.polling_service import PollingService

@pytest.fixture
def polling_service():
    """Fixture for PollingService."""
    with patch('core.polling_service.get_redis_storage') as mock_redis:
        
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance
        
        ps = PollingService()
        ps.redis = mock_redis_instance
        
        yield ps

@pytest.mark.asyncio
async def test_fetch_unread_emails_success(polling_service, mocker):
    """Test that _fetch_unread_emails successfully fetches and processes emails."""
    mock_response_data = {
        "value": [{"id": "1", "subject": "Test Email"}],
        "@odata.nextLink": None,
    }

    mock_client = MagicMock()
    # ✅ FIX: Create proper async mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data
    
    mock_client.get = AsyncMock(return_value=mock_response)

    # ✅ FIX: Properly mock the async context manager
    mocker.patch(
        "httpx.AsyncClient", 
        return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_client), 
            __aexit__=AsyncMock(return_value=False)
        )
    )
    mocker.patch("core.token_manager.get_token", return_value="dummy_token")
    
    # Mock rate limit check
    polling_service.redis.check_rate_limit.return_value = (True, 0)

    # ✅ FIX: _fetch_unread_emails now returns (messages, cursor) tuple
    messages, cursor = await polling_service._fetch_unread_emails()

    assert len(messages) == 1
    assert messages[0]["id"] == "1"
    assert cursor is None  # No next page
    mock_client.get.assert_called_once()

@pytest.mark.asyncio
async def test_batch_mark_as_read_success(polling_service, mocker):
    """Test that _batch_mark_as_read successfully marks emails as read."""
    mock_response = MagicMock()
    mock_response.raise_for_status = AsyncMock(return_value=None)
    mock_response.status_code = 200

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    mocker.patch(
        "httpx.AsyncClient",
        return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_client),
            __aexit__=AsyncMock(return_value=False)
        )
    )
    mocker.patch("core.token_manager.get_token", return_value="dummy_token")
    polling_service.redis.check_rate_limit.return_value = (True, 0)

    await polling_service._batch_mark_as_read(["1", "2"])

    mock_client.post.assert_called_once()


# ✅ NEW TEST: Test cursor tracking
@pytest.mark.asyncio
async def test_fetch_unread_emails_with_cursor(polling_service, mocker):
    """Test that _fetch_unread_emails can resume from cursor"""
    cursor_url = "https://graph.microsoft.com/v1.0/me/messages?$skip=100"
    
    mock_response_data = {
        "value": [{"id": "101", "subject": "Email from cursor"}],
        "@odata.nextLink": None,
    }

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data
    
    mock_client.get = AsyncMock(return_value=mock_response)

    mocker.patch(
        "httpx.AsyncClient",
        return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_client),
            __aexit__=AsyncMock(return_value=False)
        )
    )
    mocker.patch("core.token_manager.get_token", return_value="dummy_token")
    
    # Mock rate limit check
    polling_service.redis.check_rate_limit.return_value = (True, 0)

    # Test with resume_from cursor
    messages, next_cursor = await polling_service._fetch_unread_emails(resume_from=cursor_url)

    assert len(messages) == 1
    assert messages[0]["id"] == "101"
    assert next_cursor is None
    
    # Verify it used the cursor URL
    call_args = mock_client.get.call_args
    assert call_args.args[0] == cursor_url


# ✅ NEW TEST: Test pagination limit
@pytest.mark.asyncio
async def test_fetch_unread_emails_returns_cursor_at_max_pages(polling_service, mocker):
    """Test that cursor is returned when MAX_POLL_PAGES is hit"""
    from utils.config import MAX_POLL_PAGES
    
    # Create responses for MAX_POLL_PAGES + 1 pages
    mock_responses = []
    for i in range(MAX_POLL_PAGES + 1):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "value": [{"id": f"email_{i}", "subject": f"Email {i}"}],
            "@odata.nextLink": f"https://graph.com/page{i+1}" if i < MAX_POLL_PAGES else None
        }
        mock_responses.append(mock_resp)

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=mock_responses)

    mocker.patch(
        "httpx.AsyncClient",
        return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_client),
            __aexit__=AsyncMock(return_value=False)
        )
    )
    mocker.patch("core.token_manager.get_token", return_value="dummy_token")
    
    # Mock rate limit check
    polling_service.redis.check_rate_limit.return_value = (True, 0)

    messages, cursor = await polling_service._fetch_unread_emails()

    # Should only fetch MAX_POLL_PAGES, not all
    assert len(messages) == MAX_POLL_PAGES
    assert cursor is not None  # Cursor should be set
    assert f"page{MAX_POLL_PAGES}" in cursor  # Should be next page URL