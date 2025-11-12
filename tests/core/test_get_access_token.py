import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import webbrowser

from core.get_access_token import get_ms_graph_tokens_interactively

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

@patch('core.get_access_token.CLIENT_ID', 'test_client_id')
@patch('core.get_access_token.CLIENT_SECRET', 'test_client_secret')
@patch('core.get_access_token.SCOPES', ['Mail.Read'])
@patch('core.get_access_token.REDIRECT_URI', 'http://localhost/redirect')
@patch('core.get_access_token.ConfidentialClientApplication')
@patch('core.get_access_token.webbrowser')
@patch('core.get_access_token.get_redis_storage')
@patch('builtins.input', return_value='http://localhost/redirect?code=test_auth_code')
async def test_get_tokens_interactively_success(
    mock_input, mock_get_redis, mock_webbrowser, mock_msal_app_class
):
    """
    Tests the successful interactive token acquisition flow.
    """
    # Arrange
    mock_auth_url = 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=test_client_id'
    mock_token_result = {
        'access_token': 'test_access_token',
        'refresh_token': 'test_refresh_token',
        'expires_in': 3600
    }

    # Mock the MSAL application instance
    mock_msal_app_instance = MagicMock()
    mock_msal_app_instance.get_authorization_request_url.return_value = mock_auth_url
    mock_msal_app_instance.acquire_token_by_authorization_code.return_value = mock_token_result
    mock_msal_app_class.return_value = mock_msal_app_instance

    # Mock the Redis manager
    mock_redis_manager = MagicMock()
    mock_get_redis.return_value = mock_redis_manager

    # Act
    access_token, refresh_token = await get_ms_graph_tokens_interactively()

    # Assert
    # 1. MSAL app was initialized correctly
    mock_msal_app_class.assert_called_once_with(
        client_id='test_client_id',
        client_credential='test_client_secret'
    )
    # 2. Authorization URL was requested
    mock_msal_app_instance.get_authorization_request_url.assert_called_once_with(
        scopes=['Mail.Read'],
        redirect_uri='http://localhost/redirect'
    )
    # 3. Web browser was opened with the correct URL
    mock_webbrowser.open.assert_called_once_with(mock_auth_url)
    # 4. User was prompted for input
    mock_input.assert_called_once()
    # 5. Token was acquired with the provided auth code
    mock_msal_app_instance.acquire_token_by_authorization_code.assert_called_once_with(
        code='http://localhost/redirect?code=test_auth_code',
        scopes=['Mail.Read'],
        redirect_uri='http://localhost/redirect'
    )
    # 6. Tokens were saved to Redis
    mock_redis_manager.set_access_token.assert_called_once_with('test_access_token', 3600)
    mock_redis_manager.set_refresh_token.assert_called_once_with('test_refresh_token')
    # 7. Function returned the correct tokens
    assert access_token == 'test_access_token'
    assert refresh_token == 'test_refresh_token'

@patch('core.get_access_token.CLIENT_ID', 'test_client_id')
@patch('core.get_access_token.CLIENT_SECRET', 'test_client_secret')
@patch('core.get_access_token.SCOPES', ['Mail.Read'])
@patch('core.get_access_token.REDIRECT_URI', 'http://localhost/redirect')
async def test_get_tokens_browser_error_fallback(caplog):
    """
    Tests the fallback mechanism when the web browser fails to open.
    
    Expected behavior:
    - webbrowser.open() raises exception
    - Warning is logged with the auth URL
    - User can still proceed by manually opening the URL and pasting the code
    - The rest of the flow continues normally
    """
    from core.get_access_token import get_ms_graph_tokens_interactively
    
    mock_auth_url = 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=test_client_id'
    mock_token_result = {
        'access_token': 'test_access_token',
        'refresh_token': 'test_refresh_token',
        'expires_in': 3600
    }
    
    with patch('core.get_access_token.ConfidentialClientApplication') as mock_msal:
        mock_app = MagicMock()
        mock_app.get_authorization_request_url.return_value = mock_auth_url
        mock_app.acquire_token_by_authorization_code.return_value = mock_token_result
        mock_msal.return_value = mock_app
        
        with patch('core.get_access_token.get_redis_storage') as mock_redis:
            mock_redis.return_value = MagicMock()
            
            with patch('core.get_access_token.webbrowser.open', side_effect=Exception("Could not open browser")) as mock_browser:
                with patch('builtins.input', return_value='http://localhost/redirect?code=test_auth_code'):
                    # Don't mock print - let it run naturally
                    
                    # Act
                    result = await get_ms_graph_tokens_interactively()
                    
                    # Assert - Verify fallback mechanism worked
                    # 1. Browser open was attempted
                    mock_browser.assert_called_once_with(mock_auth_url)
                    
                    # 2. Exception was caught and warning logged with URL for manual access
                    assert "Could not open browser automatically: Could not open browser" in caplog.text
                    assert mock_auth_url in caplog.text, "Auth URL should be logged so user can manually open it"
                    
                    # 3. Flow continued successfully (didn't crash or return None)
                    assert result != (None, None), "Function should continue after browser failure"
                    assert result[0] == 'test_access_token'
                    assert result[1] == 'test_refresh_token'