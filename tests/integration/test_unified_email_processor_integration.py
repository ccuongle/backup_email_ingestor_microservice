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

def test_integration_process_email_publishes_to_rabbitmq(email_processor_instance, mock_rabbitmq_connection):
    # Given
    mock_message = {
        "id": "integration_test_id_456",
        "subject": "Integration Test Subject",
        "from": {"emailAddress": {"address": "integration_sender@example.com"}},
        "toRecipients": [{"emailAddress": {"address": "integration_recipient@example.com"}}],
        "receivedDateTime": "2025-01-02T10:00:00Z",
        "hasAttachments": True # Simulate having attachments
    }

    # Mock internal methods that interact with external systems (like file system or actual spam check)
    # but allow the core logic to flow
    email_processor_instance._save_attachments = MagicMock()
    email_processor_instance._is_spam = MagicMock(return_value=False)
    email_processor_instance._move_to_junk = MagicMock()

    # When
    metadata = email_processor_instance.process_email(mock_message)

    # Then
    assert metadata is not None
    assert session_manager.is_email_processed("integration_test_id_456")

    # Verify _save_attachments and _is_spam were called
    email_processor_instance._save_attachments.assert_called_once_with("integration_test_id_456")
    email_processor_instance._is_spam.assert_called_once_with("integration_sender@example.com")
    email_processor_instance._move_to_junk.assert_not_called() # Should not be called if not spam

    # Verify RabbitMQ publish was called with correct arguments
    mock_rabbitmq_connection.publish.assert_called_once()
    
    call_args, call_kwargs = mock_rabbitmq_connection.publish.call_args
    assert call_kwargs['exchange'] == "email_exchange"
    assert call_kwargs['routing_key'] == "queue.for_extraction"
    
    published_message = call_kwargs['message']
    assert published_message['email_id'] == "integration_test_id_456"
    assert published_message['sender'] == "integration_sender@example.com"
    assert published_message['recipient'] == "integration_recipient@example.com"
    assert published_message['subject'] == "Integration Test Subject"
    assert published_message['received_date'] == "2025-01-02T10:00:00Z"
    assert published_message['attachment_name'] == "attachments_exist" # As per _prepare_persistence_payload logic
    assert published_message['status'] == "processed"

