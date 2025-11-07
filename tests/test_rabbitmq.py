import pytest
from unittest.mock import MagicMock, patch
from utils.rabbitmq import RabbitMQConnection
from utils import config
import pika

@pytest.fixture(autouse=True)
def mock_rabbitmq_config():
    with patch.object(config, 'RABBITMQ_HOST', 'mock_host'), \
         patch.object(config, 'RABBITMQ_PORT', 5672), \
         patch.object(config, 'RABBITMQ_USERNAME', 'mock_user'), \
         patch.object(config, 'RABBITMQ_PASSWORD', 'mock_password'), \
         patch.object(config, 'RABBITMQ_VIRTUAL_HOST', '/'):
        yield

@pytest.fixture
def rabbitmq_connection():
    """Fixture for RabbitMQConnection instance with mocked pika."""
    with patch('pika.BlockingConnection') as mock_blocking_connection:
        mock_connection_instance = MagicMock()
        mock_channel_instance = MagicMock()
        mock_blocking_connection.return_value = mock_connection_instance
        mock_connection_instance.channel.return_value = mock_channel_instance

        conn = RabbitMQConnection()
        conn.connect()
        yield conn
        conn.close()

def test_connection_success(rabbitmq_connection):
    """Test successful connection and channel creation."""
    assert rabbitmq_connection.connection.is_open
    assert rabbitmq_connection.channel is not None
    rabbitmq_connection.connection.channel.assert_called_once()

def test_connection_failure():
    """Test connection failure handling."""
    with patch('pika.BlockingConnection', side_effect=pika.exceptions.AMQPConnectionError) as mock_blocking_connection:
        conn = RabbitMQConnection()
        with pytest.raises(pika.exceptions.AMQPConnectionError):
            conn.connect()
        mock_blocking_connection.assert_called_once()

def test_close_connection(rabbitmq_connection):
    """Test closing the connection."""
    rabbitmq_connection.close()
    rabbitmq_connection.connection.close.assert_called_once()

def test_ensure_queue_exists(rabbitmq_connection):
    """Test passive queue verification."""
    queue_name = "test_queue"
    rabbitmq_connection.ensure_queue_exists(queue_name)
    rabbitmq_connection.channel.queue_declare.assert_called_with(queue=queue_name, passive=True)

def test_ensure_queue_exists_failure(rabbitmq_connection):
    """Test that missing queue raises error."""
    queue_name = "missing_queue"
    rabbitmq_connection.channel.queue_declare.side_effect = pika.exceptions.ChannelClosedByBroker(404, "NOT_FOUND")
    
    with pytest.raises(pika.exceptions.ChannelClosedByBroker):
        rabbitmq_connection.ensure_queue_exists(queue_name)

def test_publish_message(rabbitmq_connection):
    """Test publishing a message."""
    exchange = "test_exchange"
    routing_key = "test_key"
    body = "test_message"
    rabbitmq_connection.publish(exchange, routing_key, body)
    rabbitmq_connection.channel.basic_publish.assert_called_with(
        exchange=exchange,
        routing_key=routing_key,
        body=body,
        properties=pika.BasicProperties(delivery_mode=2)
    )

def test_consume_message(rabbitmq_connection):
    """Test consuming messages."""
    queue_name = "consume_queue"
    mock_callback = MagicMock()
    
    # Mock ensure_queue_exists to prevent actual queue check
    with patch.object(rabbitmq_connection, 'ensure_queue_exists'):
        rabbitmq_connection.consume(queue_name, mock_callback)
    
    rabbitmq_connection.channel.basic_consume.assert_called_with(
        queue=queue_name, on_message_callback=mock_callback, auto_ack=False
    )
    rabbitmq_connection.channel.start_consuming.assert_called_once()

def test_ack_message(rabbitmq_connection):
    """Test acknowledging a message."""
    delivery_tag = 1
    rabbitmq_connection.ack_message(delivery_tag)
    rabbitmq_connection.channel.basic_ack.assert_called_with(delivery_tag)

def test_nack_message(rabbitmq_connection):
    """Test negative acknowledging a message."""
    delivery_tag = 1
    rabbitmq_connection.nack_message(delivery_tag)
    rabbitmq_connection.channel.basic_nack.assert_called_with(delivery_tag, requeue=True)