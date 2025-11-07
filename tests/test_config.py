import pytest
import os
from unittest.mock import patch
from utils.rabbitmq import RabbitMQConnection
from utils.config import validate_config


@pytest.fixture(autouse=True)
def clear_rabbitmq_env_vars():
    """Fixture to clear RabbitMQ related environment variables before each test."""
    original_env = os.environ.copy()
    for var in [
        "RABBITMQ_HOST",
        "RABBITMQ_PORT",
        "RABBITMQ_USERNAME",
        "RABBITMQ_PASSWORD",
        "RABBITMQ_VIRTUAL_HOST",
    ]:
        if var in os.environ:
            del os.environ[var]
    yield
    os.environ.clear()
    os.environ.update(original_env)


class TestRabbitMQConfig:
    """
    Tests for RabbitMQ configuration loading and validation.
    """

    def test_rabbitmq_default_config_loading(self):
        """Test that RabbitMQConnection loads default config values correctly."""
        conn = RabbitMQConnection()
        assert conn.host == "localhost"
        assert conn.port == 5672
        assert conn.username == "guest"
        assert conn.password == "guest"
        assert conn.virtual_host == "/"

    def test_rabbitmq_env_var_config_loading(self):
        """Test that RabbitMQConnection loads config values from environment variables."""
        with patch.dict(
            os.environ,
            {
                "RABBITMQ_HOST": "my_host",
                "RABBITMQ_PORT": "1234",
                "RABBITMQ_USERNAME": "my_user",
                "RABBITMQ_PASSWORD": "my_pass",
                "RABBITMQ_VIRTUAL_HOST": "/my_vhost",
            },
        ):
            # Reload config module to pick up new env vars
            import importlib
            from utils import config
            importlib.reload(config)

            conn = RabbitMQConnection()
            assert conn.host == "my_host"
            assert conn.port == 1234
            assert conn.username == "my_user"
            assert conn.password == "my_pass"
            assert conn.virtual_host == "/my_vhost"

    def test_validate_config_success(self):
        """Test that validate_config passes with all required env vars set."""
        with patch.dict(
            os.environ,
            {
                "CLIENT_ID": "test_client_id",
                "CLIENT_SECRET": "test_client_secret",
                "RABBITMQ_HOST": "test_host",
                "RABBITMQ_USERNAME": "test_user",
                "RABBITMQ_PASSWORD": "test_pass",
            },
        ):
            # Reload config module to pick up new env vars
            import importlib
            from utils import config
            importlib.reload(config)

            try:
                validate_config()
            except ValueError as e:
                pytest.fail(f"validate_config raised ValueError unexpectedly: {e}")

    @pytest.mark.parametrize(
        "missing_var, expected_error_msg",
        [
            ("CLIENT_ID", "CLIENT_ID is required"),
            ("CLIENT_SECRET", "CLIENT_SECRET is required"),
            ("RABBITMQ_HOST", "RABBITMQ_HOST is required"),
            ("RABBITMQ_USERNAME", "RABBITMQ_USERNAME is required"),
            ("RABBITMQ_PASSWORD", "RABBITMQ_PASSWORD is required"),
        ],
    )
    def test_validate_config_missing_required_vars(self, missing_var, expected_error_msg):
        """Test that validate_config raises ValueError for missing required environment variables."""
        env_vars = {
            "CLIENT_ID": "test_client_id",
            "CLIENT_SECRET": "test_client_secret",
            "RABBITMQ_HOST": "test_host",
            "RABBITMQ_USERNAME": "test_user",
            "RABBITMQ_PASSWORD": "test_pass",
        }
        if missing_var in env_vars:
            del env_vars[missing_var]

        with patch.dict(os.environ, env_vars):
            # Reload config module to pick up new env vars
            import importlib
            from utils import config
            importlib.reload(config)

            with pytest.raises(ValueError) as excinfo:
                validate_config()
            assert expected_error_msg in str(excinfo.value))

    def test_api_webhook_port_same_error(self):
        """Test that validate_config raises ValueError if API_PORT and WEBHOOK_PORT are the same."""
        with patch.dict(
            os.environ,
            {
                "CLIENT_ID": "test_client_id",
                "CLIENT_SECRET": "test_client_secret",
                "RABBITMQ_HOST": "test_host",
                "RABBITMQ_USERNAME": "test_user",
                "RABBITMQ_PASSWORD": "test_pass",
                "API_PORT": "8000",
                "WEBHOOK_PORT": "8000",
            },
        ):
            # Reload config module to pick up new env vars
            import importlib
            from utils import config
            importlib.reload(config)

            with pytest.raises(ValueError) as excinfo:
                validate_config()
            assert "API_PORT (8000) and WEBHOOK_PORT (8000) must be different" in str(excinfo.value))

    @pytest.mark.parametrize(
        "env_var, value, expected_error_msg",
        [
            ("GRAPH_API_RATE_LIMIT_THRESHOLD", "0", "GRAPH_API_RATE_LIMIT_THRESHOLD must be positive (got 0)"),
            ("GRAPH_API_RATE_LIMIT_THRESHOLD", "-1", "GRAPH_API_RATE_LIMIT_THRESHOLD must be positive (got -1)"),
            ("GRAPH_API_RATE_LIMIT_WINDOW_SECONDS", "0", "GRAPH_API_RATE_LIMIT_WINDOW_SECONDS must be positive (got 0)"),
            ("GRAPH_API_RATE_LIMIT_WINDOW_SECONDS", "-1", "GRAPH_API_RATE_LIMIT_WINDOW_SECONDS must be positive (got -1)"),
            ("GRAPH_API_RATE_LIMIT_RETRY_DELAY_SECONDS", "-1", "GRAPH_API_RATE_LIMIT_RETRY_DELAY_SECONDS must be non-negative (got -1)"),
        ],
    )
    def test_validate_config_rate_limit_errors(self, env_var, value, expected_error_msg):
        """Test that validate_config raises ValueError for invalid rate limit configuration."""
        env_vars = {
            "CLIENT_ID": "test_client_id",
            "CLIENT_SECRET": "test_client_secret",
            "RABBITMQ_HOST": "test_host",
            "RABBITMQ_USERNAME": "test_user",
            "RABBITMQ_PASSWORD": "test_pass",
            "API_PORT": "8000",
            "WEBHOOK_PORT": "8001",
            env_var: value,
        }
        with patch.dict(os.environ, env_vars):
            import importlib
            from utils import config
            importlib.reload(config)

            with pytest.raises(ValueError) as excinfo:
                validate_config()
            assert expected_error_msg in str(excinfo.value))
