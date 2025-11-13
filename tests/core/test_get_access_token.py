import pytest
from unittest.mock import MagicMock, patch
from msal import ConfidentialClientApplication
from core.get_access_token import get_ms_graph_tokens_interactively
from utils.config import SCOPES, REDIRECT_URI

@pytest.fixture
def mock_redis_manager():
    """Fixture to mock the RedisStorageManager."""
    with patch('core.get_access_token.get_redis_storage') as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        yield mock_redis

@pytest.fixture
def mock_msal_app():
    """Fixture to mock the MSAL ConfidentialClientApplication."""
    with patch('core.get_access_token.ConfidentialClientApplication') as mock_app_class:
        mock_app_instance = MagicMock()
        mock_app_instance.get_authorization_request_url.return_value = "https://login.microsoftonline.com/auth_url"
        mock_app_class.return_value = mock_app_instance
        yield mock_app_instance

@pytest.mark.asyncio
@patch('webbrowser.open')
@patch('builtins.input', return_value="http://localhost:8000/callback?code=test_auth_code")
async def test_get_tokens_success(mock_input, mock_webbrowser, mock_msal_app, mock_redis_manager):
    """
    Tests the successful interactive acquisition of tokens.
    """
    # Arrange
    mock_msal_app.acquire_token_by_authorization_code.return_value = {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "expires_in": 3600
    }

    # Act
    access_token, refresh_token = await get_ms_graph_tokens_interactively()

    # Assert
    assert access_token == "test_access_token"
    assert refresh_token == "test_refresh_token"
    mock_msal_app.get_authorization_request_url.assert_called_once()
    mock_webbrowser.assert_called_once_with("https://login.microsoftonline.com/auth_url")
    mock_input.assert_called_once()
    mock_msal_app.acquire_token_by_authorization_code.assert_called_once_with(
        code="test_auth_code",
        scopes= SCOPES,
        redirect_uri=REDIRECT_URI
    )
    mock_redis_manager.save_tokens.assert_called_once_with(
        access_token="test_access_token",
        expires_in=3600,
        refresh_token="test_refresh_token"
    )

@pytest.mark.asyncio
@patch('webbrowser.open')
@patch('builtins.input', return_value="")
async def test_get_tokens_no_input(mock_input, mock_webbrowser, mock_msal_app, mock_redis_manager):
    """
    Tests the flow where the user provides no input.
    """
    # Arrange

    # Act
    access_token, refresh_token = await get_ms_graph_tokens_interactively()

    # Assert
    assert access_token is None
    assert refresh_token is None
    mock_msal_app.acquire_token_by_authorization_code.assert_not_called()
    mock_redis_manager.save_tokens.assert_not_called()

@pytest.mark.asyncio
@patch('webbrowser.open')
@patch('builtins.input', return_value="http://localhost:8000/callback?code=test_auth_code")
async def test_get_tokens_api_error(mock_input, mock_webbrowser, mock_msal_app, mock_redis_manager):
    """
    Tests the flow where the MSAL API returns an error.
    """
    # Arrange
    mock_msal_app.acquire_token_by_authorization_code.return_value = {
        "error": "invalid_grant",
        "error_description": "The authorization code is invalid."
    }

    # Act
    access_token, refresh_token = await get_ms_graph_tokens_interactively()

    # Assert
    assert access_token is None
    assert refresh_token is None
    mock_msal_app.acquire_token_by_authorization_code.assert_called_once()
    mock_redis_manager.save_tokens.assert_not_called()

@pytest.mark.asyncio
@patch('webbrowser.open')
@patch('builtins.input', return_value="http://localhost:8000/callback?code=test_auth_code")
async def test_get_tokens_exception_on_acquire(mock_input, mock_webbrowser, mock_msal_app, mock_redis_manager):
    """
    Tests the flow where acquire_token_by_authorization_code raises an exception.
    """
    # Arrange
    mock_msal_app.acquire_token_by_authorization_code.side_effect = Exception("Network Error")

    # Act
    access_token, refresh_token = await get_ms_graph_tokens_interactively()

    # Assert
    assert access_token is None
    assert refresh_token is None
    mock_msal_app.acquire_token_by_authorization_code.assert_called_once()
    mock_redis_manager.save_tokens.assert_not_called()

@pytest.mark.asyncio
@patch('webbrowser.open')
@patch('builtins.input', return_value="invalid_url")
async def test_get_tokens_invalid_url(mock_input, mock_webbrowser, mock_msal_app, mock_redis_manager):
    """
    Tests the flow where the user provides an invalid URL.
    """
    # Arrange

    # Act
    access_token, refresh_token = await get_ms_graph_tokens_interactively()

    # Assert
    assert access_token is None
    assert refresh_token is None
    mock_msal_app.acquire_token_by_authorization_code.assert_not_called()
    mock_redis_manager.save_tokens.assert_not_called()
