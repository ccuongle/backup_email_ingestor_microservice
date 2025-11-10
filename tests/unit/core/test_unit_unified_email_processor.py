import unittest
from unittest.mock import MagicMock, patch
import json
from core.unified_email_processor import EmailProcessor

class TestUnifiedEmailProcessor(unittest.TestCase):

    def setUp(self):
        self.mock_token = "test_token"
        self.processor = EmailProcessor(token=self.mock_token)
        # Mock the httpx client used for non-MS4 calls
        self.processor.client = MagicMock()

    def tearDown(self):
        self.processor.close()

    def _create_test_message(self, msg_id="test_id", subject="Test Subject", sender="test@example.com"):
        message = {
            "id": msg_id,
            "subject": subject,
            "from": {"emailAddress": {"address": sender}},
            "receivedDateTime": "2025-11-03T10:00:00Z",
            "hasAttachments": True,
        }
        return message

    @patch('core.unified_email_processor.session_manager')
    def test_process_email_success_returns_payload(self, mock_session_manager):
        # Arrange
        message = self._create_test_message()
        mock_session_manager.is_email_processed.return_value = False
        
        # Act
        result = self.processor.process_email(message)

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result["email_id"], message["id"])
        self.assertEqual(result["subject"], message["subject"])
        self.assertEqual(result["sender"], message["from"]["emailAddress"]["address"])
        # self.assertIn("raw_message", result)
        mock_session_manager.register_processed_email.assert_called_once_with(message["id"])
        self.processor.client.get.assert_called_once() # For attachments

    @patch('core.unified_email_processor.session_manager')
    def test_process_email_spam_returns_none(self, mock_session_manager):
        # Arrange
        message = self._create_test_message(sender="spam@spam.com")
        mock_session_manager.is_email_processed.return_value = False
        with patch.object(self.processor, '_is_spam', return_value=True) as mock_is_spam:
            
            # Act
            result = self.processor.process_email(message)

            # Assert
            self.assertIsNone(result)
            mock_is_spam.assert_called_once()
            self.processor.client.post.assert_called_once() # For moving to junk
            mock_session_manager.register_processed_email.assert_called_once_with(message["id"])

    @patch('core.unified_email_processor.session_manager')
    def test_process_email_already_processed_returns_none(self, mock_session_manager):
        # Arrange
        message = self._create_test_message()
        mock_session_manager.is_email_processed.return_value = True

        # Act
        result = self.processor.process_email(message)

        # Assert
        self.assertIsNone(result)
        mock_session_manager.is_email_processed.assert_called_once_with(message["id"])

    def test_process_email_missing_id_returns_none(self):
        # Arrange
        message = self._create_test_message(msg_id=None)

        # Act
        result = self.processor.process_email(message)

        # Assert
        self.assertIsNone(result)

    def test_prepare_persistence_payload(self):
        # Arrange
        message = self._create_test_message()
        
        # Act
        payload = self.processor._prepare_persistence_payload(message)

        # Assert
        self.assertEqual(payload["email_id"], message["id"])
        self.assertEqual(payload["subject"], message["subject"])
        self.assertEqual(payload["sender"], message["from"]["emailAddress"]["address"])
        # self.assertEqual(payload["raw_message"], json.dumps(message))

if __name__ == '__main__':
    unittest.main()
