import pytest
import json
from unittest.mock import MagicMock, patch
from core.unified_email_processor import EmailProcessor
from core.session_manager import session_manager
from utils.rabbitmq import RabbitMQConnection



@pytest.fixture
def email_processor_instance():
    with patch('core.unified_email_processor.RabbitMQConnection') as MockRabbitMQConnection:
        mock_rabbitmq_instance = MagicMock(spec=RabbitMQConnection)
        MockRabbitMQConnection.return_value = mock_rabbitmq_instance
        
        processor = EmailProcessor(token="test_token")
        
        # Configure the mock instance methods
        # mock_rabbitmq_instance.declare_exchange.return_value = None
        # mock_rabbitmq_instance.declare_queue.return_value = None
        # mock_rabbitmq_instance.bind_queue_to_exchange.return_value = None
        
        yield processor, mock_rabbitmq_instance
        processor.close()

@pytest.fixture(autouse=True)
def clear_session_manager():
    with patch('core.session_manager.session_manager.redis', autospec=True) as mock_redis:
        mock_redis.processed_emails_set = set()
        mock_redis.pending_emails_set = set()
        mock_redis.is_email_processed.side_effect = lambda email_id: email_id in mock_redis.processed_emails_set
        mock_redis.mark_email_processed.side_effect = lambda email_id: mock_redis.processed_emails_set.add(email_id)
        mock_redis.add_pending_email.side_effect = lambda email_id: mock_redis.pending_emails_set.add(email_id)
        mock_redis.remove_pending.side_effect = lambda email_id: mock_redis.pending_emails_set.discard(email_id)
        yield

def test_process_email_publishes_to_rabbitmq_on_success(email_processor_instance, mocker):
    processor, mock_rabbitmq_connection = email_processor_instance
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
    processor._is_spam = MagicMock(return_value=False)
    processor._save_attachments = MagicMock()

    # When
    metadata = processor.process_email(mock_message)

    # Then
    assert metadata is not None
    assert session_manager.is_email_processed("test_id_123")

    # Verify RabbitMQ publish was called with correct arguments
    mock_rabbitmq_connection.publish.assert_called_once()
    
    call_args, call_kwargs = mock_rabbitmq_connection.publish.call_args
    assert call_kwargs['exchange'] == "email_exchange"
    assert call_kwargs['routing_key'] == "queue.for_extraction"
    
    published_message = call_kwargs['body'] # Changed from 'message' to 'body'
    published_message_dict = json.loads(published_message) # Parse JSON string back to dict
    assert published_message_dict['email_id'] == "test_id_123"
    assert published_message_dict['sender'] == "sender@example.com"
    assert published_message_dict['recipient'] == "recipient@example.com"
    assert published_message_dict['subject'] == "Test Subject"
    assert published_message_dict['received_date'] == "2025-01-01T12:00:00Z"
    assert published_message_dict['attachment_name'] is None
    assert published_message_dict['status'] == "processed"

def test_process_email_does_not_publish_on_spam(email_processor_instance, mocker):
    processor, mock_rabbitmq_connection = email_processor_instance
    # Given
    mock_message = {
        "id": "test_id_spam",
        "subject": "Spam Subject",
        "from": {"emailAddress": {"address": "spam@example.com"}},
        "receivedDateTime": "2025-01-01T12:00:00Z",
        "hasAttachments": False
    }

    # Mock _is_spam to return True
    processor._is_spam = MagicMock(return_value=True)
    processor._move_to_junk = MagicMock()

    # When
    metadata = processor.process_email(mock_message)

    # Then
    assert metadata is None
    assert session_manager.is_email_processed("test_id_spam")
    mock_rabbitmq_connection.publish.assert_not_called()
    processor._move_to_junk.assert_called_once_with("test_id_spam")

def test_process_email_does_not_publish_on_error(email_processor_instance, mocker):
    processor, mock_rabbitmq_connection = email_processor_instance
    # Given
    mock_message = {
        "id": "test_id_error",
        "subject": "Error Subject",
        "from": {"emailAddress": {"address": "error@example.com"}},
        "receivedDateTime": "2025-01-01T12:00:00Z",
        "hasAttachments": False
    }

    # Mock _save_attachments to raise an exception
    processor._is_spam = MagicMock(return_value=False)
    processor._save_attachments = MagicMock(side_effect=Exception("Test Error"))

    # When
    metadata = processor.process_email(mock_message)

    # Then
    assert metadata is None
    assert not session_manager.is_email_processed("test_id_error") # Should not register as processed on error
    mock_rabbitmq_connection.publish.assert_not_called()
