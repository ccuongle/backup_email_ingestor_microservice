import pytest
from unittest.mock import MagicMock, patch
from ms1_email_ingestor.core.unified_email_processor import EmailProcessor
from ms1_email_ingestor.core.session_manager import session_manager
from utils.rabbitmq import RabbitMQConnection

@pytest.fixture
def mock_rabbitmq_connection():
    with patch('utils.rabbitmq.RabbitMQConnection') as mock_rabbitmq_class:
        # Configure the mock instance that RabbitMQConnection() will return
        mock_instance = MagicMock(spec=RabbitMQConnection)
        
        # Mock the _channel attribute and its methods
        mock_instance._channel = MagicMock()
        mock_instance._channel.queue_declare.return_value = None
        mock_instance._channel.exchange_declare.return_value = None
        mock_instance._channel.queue_bind.return_value = None
        mock_instance._channel.basic_publish.return_value = None
        
        # Make the mock class return our configured mock instance
        mock_rabbitmq_class.return_value = mock_instance
        
        yield mock_instance

@pytest.fixture
def email_processor_instance(mock_rabbitmq_connection):
    processor = EmailProcessor(token="test_token")
    yield processor
    processor.close()

@pytest.fixture(autouse=True)
def clear_session_manager():
    with patch('ms1_email_ingestor.core.session_manager.session_manager.redis', autospec=True) as mock_redis:
        mock_redis.processed_emails_set = set()
        mock_redis.pending_emails_set = set()
        mock_redis.is_email_processed.side_effect = lambda email_id: email_id in mock_redis.processed_emails_set
        mock_redis.mark_email_processed.side_effect = lambda email_id: mock_redis.processed_emails_set.add(email_id)
        mock_redis.add_pending_email.side_effect = lambda email_id: mock_redis.pending_emails_set.add(email_id)
        mock_redis.remove_pending.side_effect = lambda email_id: mock_redis.pending_emails_set.discard(email_id)
        yield

def test_process_email_publishes_to_rabbitmq_on_success(email_processor_instance, mock_rabbitmq_connection):
    # Given
    mock_message = {
        "id": "test_id_123",
        "subject": "Test Subject",
        "from": {"emailAddress": {"address": "sender@example.com"}},
        "toRecipients": [{"emailAddress": {"address": "recipient@example.com"}}],
        "receivedDateTime": "2025-01-01T12:00:00Z",
        "hasAttachments": False
    }

    # Mock internal methods to simulate successful processing
    email_processor_instance._is_spam = MagicMock(return_value=False)
    email_processor_instance._save_attachments = MagicMock()

    # When
    metadata = email_processor_instance.process_email(mock_message)

    # Then
    assert metadata is not None
    assert session_manager.is_email_processed("test_id_123")

    # Verify RabbitMQ publish was called with correct arguments
    mock_rabbitmq_connection.publish.assert_called_once()
    
    call_args, call_kwargs = mock_rabbitmq_connection.publish.call_args
    assert call_kwargs['exchange'] == "email_exchange"
    assert call_kwargs['routing_key'] == "queue.for_extraction"
    
    published_message = call_kwargs['message']
    assert published_message['email_id'] == "test_id_123"
    assert published_message['sender'] == "sender@example.com"
    assert published_message['recipient'] == "recipient@example.com"
    assert published_message['subject'] == "Test Subject"
    assert published_message['received_date'] == "2025-01-01T12:00:00Z"
    assert published_message['attachment_name'] is None
    assert published_message['status'] == "processed"

def test_process_email_does_not_publish_on_spam(email_processor_instance, mock_rabbitmq_connection):
    # Given
    mock_message = {
        "id": "test_id_spam",
        "subject": "Spam Subject",
        "from": {"emailAddress": {"address": "spam@example.com"}},
        "receivedDateTime": "2025-01-01T12:00:00Z",
        "hasAttachments": False
    }

    # Mock _is_spam to return True
    email_processor_instance._is_spam = MagicMock(return_value=True)
    email_processor_instance._move_to_junk = MagicMock()

    # When
    metadata = email_processor_instance.process_email(mock_message)

    # Then
    assert metadata is None
    assert session_manager.is_email_processed("test_id_spam")
    mock_rabbitmq_connection.publish.assert_not_called()
    email_processor_instance._move_to_junk.assert_called_once_with("test_id_spam")

def test_process_email_does_not_publish_on_error(email_processor_instance, mock_rabbitmq_connection):
    # Given
    mock_message = {
        "id": "test_id_error",
        "subject": "Error Subject",
        "from": {"emailAddress": {"address": "error@example.com"}},
        "receivedDateTime": "2025-01-01T12:00:00Z",
        "hasAttachments": False
    }

    # Mock _save_attachments to raise an exception
    email_processor_instance._is_spam = MagicMock(return_value=False)
    email_processor_instance._save_attachments = MagicMock(side_effect=Exception("Test Error"))

    # When
    metadata = email_processor_instance.process_email(mock_message)

    # Then
    assert metadata is None
    assert not session_manager.is_email_processed("test_id_error") # Should not register as processed on error
    mock_rabbitmq_connection.publish.assert_not_called()

def test_email_processor_initializes_rabbitmq_connection(mock_rabbitmq_connection):
    # Given
    # mock_rabbitmq_connection is already patched and yielded by the fixture
    
    # When
    processor = EmailProcessor(token="another_test_token")
    
    # Then
    mock_rabbitmq_connection.declare_exchange.assert_called_once_with(
        exchange_name="email_exchange", exchange_type="topic", durable=True
    )
    mock_rabbitmq_connection.declare_queue.assert_called_once_with(
        queue_name="queue.for_extraction", durable=True
    )
    mock_rabbitmq_connection.bind_queue_to_exchange.assert_called_once_with(
        queue_name="queue.for_extraction",
        exchange_name="email_exchange",
        routing_key="queue.for_extraction"
    )
    processor.close()
