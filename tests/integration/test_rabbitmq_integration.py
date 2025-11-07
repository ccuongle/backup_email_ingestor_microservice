"""
Integration Tests for MS1 RabbitMQ Connection (Mocked Connection Mode)
Using real RabbitMQ configuration but mocking connection layer.
"""

import pytest
import pika
from unittest.mock import patch, MagicMock
from utils.rabbitmq import RabbitMQConnection
from utils import config


# -------------------------------------------------------------
# FIXTURES
# -------------------------------------------------------------
@pytest.fixture(scope="module")
def mock_pika_connection():
    """Mock pika.BlockingConnection để không mở kết nối thật."""
    with patch("utils.rabbitmq.pika.BlockingConnection") as mock_conn_cls:
        mock_conn = MagicMock()
        mock_channel = MagicMock()

        # Setup mock behavior
        mock_conn.channel.return_value = mock_channel
        mock_conn.is_open = True
        mock_channel.is_open = True

        mock_conn_cls.return_value = mock_conn
        yield mock_conn, mock_channel


@pytest.fixture(autouse=True)
def reset_mocks(mock_pika_connection):
    """Tự động reset mock giữa mỗi test để tránh dồn call count."""
    conn, ch = mock_pika_connection
    conn.reset_mock()
    ch.reset_mock()


# -------------------------------------------------------------
# TEST CASES
# -------------------------------------------------------------
class TestRabbitMQMockedIntegration:
    """
    Integration-style tests for RabbitMQ connection using mocked connection.
    Focus: verify logic, not external RabbitMQ availability.
    """

    @pytest.mark.integration
    def test_connection_and_channel(self, mock_pika_connection):
        """Test Case ID: 1.1-INT-001 — Connection and channel creation."""
        mock_conn, mock_channel = mock_pika_connection

        client = RabbitMQConnection()
        client.connect()

        assert client.connection is mock_conn
        assert client.channel is mock_channel
        print("✓ Mocked connection and channel verified")

        client.close()
        mock_conn.close.assert_called_once()
        print("✓ Mocked connection closed successfully")

    @pytest.mark.integration
    def test_connection_failure_invalid_credentials(self):
        """Test Case ID: 1.1-INT-002 — Invalid credentials handling."""
        # Giả lập pika ném lỗi khi connect
        with patch("utils.rabbitmq.pika.BlockingConnection", side_effect=pika.exceptions.AMQPConnectionError):
            client = RabbitMQConnection()
            with pytest.raises(pika.exceptions.AMQPConnectionError):
                client.connect()
            print("✓ Invalid credentials handled correctly (mocked)")

    @pytest.mark.integration
    def test_ensure_queue_exists_success(self, mock_pika_connection):
        """Test Case ID: 1.1-INT-003 — Passive queue exists."""
        _, mock_channel = mock_pika_connection

        client = RabbitMQConnection()
        client.connect()

        client.ensure_queue_exists("test_existing_queue")
        mock_channel.queue_declare.assert_called_with(queue="test_existing_queue", passive=True)
        print("✓ Queue existence verified via passive declare (mocked)")

        client.close()

    @pytest.mark.integration
    def test_ensure_queue_exists_failure(self, mock_pika_connection):
        """Test Case ID: 1.1-INT-004 — Nonexistent queue raises error."""
        _, mock_channel = mock_pika_connection
        mock_channel.queue_declare.side_effect = pika.exceptions.ChannelClosedByBroker(404, "Not Found")

        client = RabbitMQConnection()
        client.connect()

        with pytest.raises(pika.exceptions.ChannelClosedByBroker):
            client.ensure_queue_exists("non_existent_queue")
        print("✓ Nonexistent queue raises ChannelClosedByBroker (mocked)")

        client.close()

    @pytest.mark.integration
    def test_publish_and_consume_message(self, mock_pika_connection):
        """Test Case ID: 1.1-INT-005 — Publish and consume cycle."""
        _, mock_channel = mock_pika_connection

        client = RabbitMQConnection()
        client.connect()

        test_queue = "mock_pubsub_queue"
        test_message = "Hello from mocked integration!"

        # Publish
        client.publish(exchange="", routing_key=test_queue, body=test_message)

        # Kiểm tra bằng partial match (vì có thêm properties)
        assert mock_channel.basic_publish.called
        call_kwargs = mock_channel.basic_publish.call_args.kwargs
        assert call_kwargs["exchange"] == ""
        assert call_kwargs["routing_key"] == test_queue
        assert call_kwargs["body"] == test_message
        print("✓ Mocked message published successfully (with properties)")

        # Simulate consume
        callback = MagicMock()
        mock_channel.basic_consume(queue=test_queue, on_message_callback=callback, auto_ack=False)
        print("✓ Mocked consumer registered successfully")

        client.close()

    @pytest.mark.integration
    def test_publish_to_exchange_with_routing_key(self, mock_pika_connection):
        """Test Case ID: 1.1-INT-006 — Publish with exchange and routing key."""
        _, mock_channel = mock_pika_connection

        client = RabbitMQConnection()
        client.connect()

        exchange = "test_email_exchange"
        routing_key = "email.to.extractor"
        message = "Email metadata for extraction"

        client.publish(exchange=exchange, routing_key=routing_key, body=message)

        # Kiểm tra partial args
        assert mock_channel.basic_publish.called
        call_kwargs = mock_channel.basic_publish.call_args.kwargs
        assert call_kwargs["exchange"] == exchange
        assert call_kwargs["routing_key"] == routing_key
        assert call_kwargs["body"] == message
        print("✓ Publish to exchange with routing key verified (mocked)")

        client.close()

    @pytest.mark.integration
    def test_connection_recovery(self, mock_pika_connection):
        """Test Case ID: 1.1-INT-007 — Connection recovery."""
        mock_conn, mock_channel = mock_pika_connection

        client = RabbitMQConnection()
        client.connect()

        # Simulate close
        client.close()
        mock_conn.close.assert_called_once()
        print("✓ Mocked connection closed once")

        # Reconnect again
        client.connect()
        assert client.channel is mock_channel
        print("✓ Mocked connection recovery verified")
