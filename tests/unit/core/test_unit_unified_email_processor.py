import unittest
from unittest.mock import MagicMock, patch
from core.unified_email_processor import EmailProcessor

class TestUnifiedEmailProcessor(unittest.TestCase):

    def setUp(self):
        """Setup trước mỗi test"""
        self.mock_token = "test_token"
        
        # ✅ Tạo mock RabbitMQ connection
        self.mock_rabbitmq = MagicMock()
        self.mock_rabbitmq.publish = MagicMock()
        
        # ✅ Inject mock vào EmailProcessor
        self.processor = EmailProcessor(
            token=self.mock_token,
            rabbitmq_connection=self.mock_rabbitmq  # Dependency Injection
        )
        
        # Mock the httpx client
        self.processor.client = MagicMock()

    def tearDown(self):
        """Cleanup sau mỗi test"""
        self.processor.close()

    def _create_test_message(self, msg_id="test_id", subject="Test Subject", sender="test@example.com"):
        """Helper tạo test message"""
        message = {
            "id": msg_id,
            "subject": subject,
            "from": {"emailAddress": {"address": sender}},
            "toRecipients": [{"emailAddress": {"address": "recipient@example.com"}}],
            "receivedDateTime": "2025-11-03T10:00:00Z",
            "hasAttachments": True,
        }
        return message

    @patch('core.unified_email_processor.session_manager')
    def test_process_email_success_returns_payload(self, mock_session_manager):
        """Test xử lý email thành công"""
        # Arrange
        message = self._create_test_message()
        mock_session_manager.is_email_processed.return_value = False
        
        # Mock attachment API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": []}
        self.processor.client.get.return_value = mock_response
        
        # Act
        result = self.processor.process_email(message)

        # Assert
        self.assertIsNotNone(result, "Result should not be None")
        self.assertEqual(result["email_id"], message["id"])
        self.assertEqual(result["subject"], message["subject"])
        self.assertEqual(result["sender"], message["from"]["emailAddress"]["address"])
        self.assertEqual(result["status"], "processed")
        
        # ✅ Verify RabbitMQ publish được gọi
        self.mock_rabbitmq.publish.assert_called_once()
        call_args = self.mock_rabbitmq.publish.call_args
        self.assertEqual(call_args[1]["exchange"], "email_exchange")
        self.assertEqual(call_args[1]["routing_key"], "queue.for_extraction")
        
        # Verify session manager
        mock_session_manager.register_processed_email.assert_called_once_with(message["id"])
        
        # Verify attachment fetch
        self.processor.client.get.assert_called_once()

    @patch('core.unified_email_processor.session_manager')
    def test_process_email_spam_returns_none(self, mock_session_manager):
        """Test xử lý email spam"""
        # Arrange
        message = self._create_test_message(sender="spam@spam.com")
        mock_session_manager.is_email_processed.return_value = False
        
        # Mock move to junk response
        mock_response = MagicMock()
        mock_response.status_code = 200
        self.processor.client.post.return_value = mock_response
        
        with patch.object(self.processor, '_is_spam', return_value=True) as mock_is_spam:
            # Act
            result = self.processor.process_email(message)

            # Assert
            self.assertIsNone(result, "Spam email should return None")
            mock_is_spam.assert_called_once()
            self.processor.client.post.assert_called_once()
            mock_session_manager.register_processed_email.assert_called_once_with(message["id"])
            
            # ✅ Verify RabbitMQ KHÔNG được gọi với spam
            self.mock_rabbitmq.publish.assert_not_called()

    @patch('core.unified_email_processor.session_manager')
    def test_process_email_already_processed_returns_none(self, mock_session_manager):
        """Test email đã xử lý trước đó"""
        # Arrange
        message = self._create_test_message()
        mock_session_manager.is_email_processed.return_value = True

        # Act
        result = self.processor.process_email(message)

        # Assert
        self.assertIsNone(result, "Already processed email should return None")
        mock_session_manager.is_email_processed.assert_called_once_with(message["id"])
        
        # ✅ Verify không có thao tác nào khác được gọi
        self.processor.client.get.assert_not_called()
        self.mock_rabbitmq.publish.assert_not_called()

    def test_process_email_missing_id_returns_none(self):
        """Test email thiếu ID"""
        # Arrange
        message = self._create_test_message(msg_id=None)

        # Act
        result = self.processor.process_email(message)

        # Assert
        self.assertIsNone(result, "Email without ID should return None")

    def test_prepare_persistence_payload(self):
        """Test chuẩn bị payload metadata"""
        # Arrange
        message = self._create_test_message()
        
        # Act
        payload = self.processor._prepare_persistence_payload(message)

        # Assert
        self.assertEqual(payload["email_id"], message["id"])
        self.assertEqual(payload["subject"], message["subject"])
        self.assertEqual(payload["sender"], message["from"]["emailAddress"]["address"])
        self.assertEqual(payload["recipient"], "recipient@example.com")
        self.assertEqual(payload["received_date"], message["receivedDateTime"])
        self.assertEqual(payload["status"], "processed")
        self.assertIsNotNone(payload["attachment_name"])

    @patch('core.unified_email_processor.session_manager')
    def test_process_email_rabbitmq_publish_failure(self, mock_session_manager):
        """Test xử lý khi RabbitMQ publish thất bại"""
        # Arrange
        message = self._create_test_message()
        mock_session_manager.is_email_processed.return_value = False
        
        # Mock RabbitMQ publish raise exception
        self.mock_rabbitmq.publish.side_effect = Exception("RabbitMQ connection failed")
        
        # Mock attachment response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": []}
        self.processor.client.get.return_value = mock_response
        
        # Act
        result = self.processor.process_email(message)
        
        # Assert
        # ✅ Khi RabbitMQ fail, process_email return None
        self.assertIsNone(result, "Should return None when RabbitMQ publish fails")
        
        # Verify publish được gọi (nhưng failed)
        self.mock_rabbitmq.publish.assert_called_once()

    @patch('core.unified_email_processor.session_manager')
    def test_batch_process_emails(self, mock_session_manager):
        """Test xử lý batch emails"""
        # Arrange
        messages = [
            self._create_test_message(msg_id="id1"),
            self._create_test_message(msg_id="id2"),
            self._create_test_message(msg_id="id3"),
        ]
        
        # Mock: id2 đã xử lý rồi
        def is_processed_side_effect(msg_id):
            return msg_id == "id2"
        
        mock_session_manager.is_email_processed.side_effect = is_processed_side_effect
        mock_session_manager.register_pending_email = MagicMock()
        mock_session_manager.register_processed_email = MagicMock()
        
        # Mock attachment response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": []}
        self.processor.client.get.return_value = mock_response
        
        # Act
        result = self.processor.batch_process_emails(messages, source="test")
        
        # Assert
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["success"], 2)  # id1, id3
        self.assertEqual(result["skipped"], 1)  # id2

    @patch('core.unified_email_processor.session_manager')
    @patch('core.unified_email_processor.os.makedirs')
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    def test_save_attachments_success(self, mock_open, mock_makedirs, mock_session_manager):
        """Test lưu attachments thành công"""
        # Arrange
        message = self._create_test_message()
        mock_session_manager.is_email_processed.return_value = False
        
        # Mock attachment API response với file attachment
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": "invoice.pdf",
                    "contentBytes": "SGVsbG8gV29ybGQ="  # "Hello World" in base64
                }
            ]
        }
        self.processor.client.get.return_value = mock_response
        
        # Act
        result = self.processor.process_email(message)
        
        # Assert
        self.assertIsNotNone(result)
        mock_open.assert_called()  # File được mở để ghi


if __name__ == '__main__':
    unittest.main()