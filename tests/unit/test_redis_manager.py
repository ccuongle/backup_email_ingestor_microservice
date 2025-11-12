import pytest
from unittest.mock import MagicMock, patch
from cache.redis_manager import RedisStorageManager

@pytest.fixture
def mock_redis_client():
    """Fixture to mock the redis.Redis client."""
    with patch('redis.Redis') as mock:
        yield mock.return_value

@pytest.fixture
def redis_storage_manager(mock_redis_client):
    """Fixture to provide an instance of RedisStorageManager with a mocked Redis client."""
    manager = RedisStorageManager(host="test_host", port=6379, db=0)
    # Ensure the internal redis client is the mock
    manager.redis = mock_redis_client
    return manager

def test_set_access_token(redis_storage_manager, mock_redis_client):
    """Test that set_access_token correctly stores the token with expiration."""
    token = "test_access_token"
    expires_in = 3600
    redis_storage_manager.set_access_token(token, expires_in)
    mock_redis_client.set.assert_called_once_with(
        redis_storage_manager.KEY_ACCESS_TOKEN, token, ex=expires_in
    )

def test_get_access_token(redis_storage_manager, mock_redis_client):
    """Test that get_access_token retrieves the token."""
    mock_redis_client.get.return_value = "retrieved_access_token"
    token = redis_storage_manager.get_access_token()
    mock_redis_client.get.assert_called_once_with(redis_storage_manager.KEY_ACCESS_TOKEN)
    assert token == "retrieved_access_token"

def test_get_access_token_none(redis_storage_manager, mock_redis_client):
    """Test that get_access_token returns None if no token is set."""
    mock_redis_client.get.return_value = None
    token = redis_storage_manager.get_access_token()
    assert token is None

def test_set_refresh_token(redis_storage_manager, mock_redis_client):
    """Test that set_refresh_token correctly stores the token."""
    token = "test_refresh_token"
    redis_storage_manager.set_refresh_token(token)
    mock_redis_client.set.assert_called_once_with(
        redis_storage_manager.KEY_REFRESH_TOKEN, token
    )

def test_get_refresh_token(redis_storage_manager, mock_redis_client):
    """Test that get_refresh_token retrieves the token."""
    mock_redis_client.get.return_value = "retrieved_refresh_token"
    token = redis_storage_manager.get_refresh_token()
    mock_redis_client.get.assert_called_once_with(redis_storage_manager.KEY_REFRESH_TOKEN)
    assert token == "retrieved_refresh_token"

def test_get_refresh_token_none(redis_storage_manager, mock_redis_client):
    """Test that get_refresh_token returns None if no token is set."""
    mock_redis_client.get.return_value = None
    token = redis_storage_manager.get_refresh_token()
    assert token is None
