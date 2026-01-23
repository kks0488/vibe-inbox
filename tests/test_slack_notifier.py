"""Tests for slack_notifier module."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock slack_sdk module before importing slack_notifier
mock_slack_sdk = MagicMock()
mock_slack_sdk.WebClient = MagicMock

# Create SlackApiError with response attribute
class MockSlackApiError(Exception):
    def __init__(self, message="", response=None):
        super().__init__(message)
        self.response = response or {}

mock_slack_sdk.errors.SlackApiError = MockSlackApiError
sys.modules['slack_sdk'] = mock_slack_sdk
sys.modules['slack_sdk.errors'] = mock_slack_sdk.errors


class TestSlackNotifier:
    """Tests for SlackNotifier class."""

    @patch('slack_notifier.SLACK_AVAILABLE', True)
    @patch('slack_notifier.config.SLACK_ENABLED', False)
    @patch('slack_notifier.config.SLACK_BOT_TOKEN', '')
    @patch('slack_notifier.config.SLACK_CHANNEL_ID', '')
    def test_notifier_disabled_when_slack_disabled(self):
        """Notifier should be disabled when SLACK_ENABLED is False."""
        from slack_notifier import SlackNotifier

        notifier = SlackNotifier()
        assert notifier.enabled == False
        assert notifier.client is None

    @patch('slack_notifier.SLACK_AVAILABLE', True)
    @patch('slack_notifier.config.SLACK_ENABLED', True)
    @patch('slack_notifier.config.SLACK_BOT_TOKEN', '')
    @patch('slack_notifier.config.SLACK_CHANNEL_ID', 'C12345')
    def test_notifier_disabled_when_no_token(self):
        """Notifier should be disabled when SLACK_BOT_TOKEN is empty."""
        from slack_notifier import SlackNotifier

        notifier = SlackNotifier()
        # Empty string is falsy, so enabled will be False-like
        assert not notifier.enabled

    @patch('slack_notifier.SLACK_AVAILABLE', False)
    @patch('slack_notifier.config.SLACK_ENABLED', True)
    @patch('slack_notifier.config.SLACK_BOT_TOKEN', 'xoxb-test')
    @patch('slack_notifier.config.SLACK_CHANNEL_ID', 'C12345')
    def test_notifier_disabled_when_slack_sdk_not_available(self):
        """Notifier should be disabled when slack-sdk is not installed."""
        from slack_notifier import SlackNotifier

        notifier = SlackNotifier()
        assert notifier.enabled == False

    @patch('slack_notifier.WebClient')
    @patch('slack_notifier.SLACK_AVAILABLE', True)
    @patch('slack_notifier.config.SLACK_ENABLED', True)
    @patch('slack_notifier.config.SLACK_BOT_TOKEN', 'xoxb-test-token')
    @patch('slack_notifier.config.SLACK_CHANNEL_ID', 'C12345')
    def test_notifier_enabled_with_valid_config(self, mock_web_client):
        """Notifier should be enabled when all config is valid."""
        from slack_notifier import SlackNotifier

        mock_client = MagicMock()
        mock_web_client.return_value = mock_client

        notifier = SlackNotifier()
        # enabled is truthy when all config is valid
        assert notifier.enabled
        assert notifier.client == mock_client
        assert notifier.channel_id == 'C12345'
        mock_web_client.assert_called_once_with(token='xoxb-test-token')

    @patch('slack_notifier.SLACK_AVAILABLE', True)
    @patch('slack_notifier.config.SLACK_ENABLED', False)
    @patch('slack_notifier.config.SLACK_BOT_TOKEN', '')
    @patch('slack_notifier.config.SLACK_CHANNEL_ID', '')
    def test_send_message_returns_false_when_disabled(self):
        """_send_message should return False when notifier is disabled."""
        from slack_notifier import SlackNotifier

        notifier = SlackNotifier()
        result = notifier._send_message("Test message")
        assert result == False

    @patch('slack_notifier.WebClient')
    @patch('slack_notifier.SLACK_AVAILABLE', True)
    @patch('slack_notifier.config.SLACK_ENABLED', True)
    @patch('slack_notifier.config.SLACK_BOT_TOKEN', 'xoxb-test')
    @patch('slack_notifier.config.SLACK_CHANNEL_ID', 'C12345')
    def test_send_message_success(self, mock_web_client):
        """_send_message should successfully send message when enabled."""
        from slack_notifier import SlackNotifier

        mock_client = MagicMock()
        mock_web_client.return_value = mock_client

        notifier = SlackNotifier()
        result = notifier._send_message("Test message")

        assert result == True
        mock_client.chat_postMessage.assert_called_once_with(
            channel='C12345',
            text="Test message",
            blocks=None
        )

    @patch('slack_notifier.WebClient')
    @patch('slack_notifier.SLACK_AVAILABLE', True)
    @patch('slack_notifier.config.SLACK_ENABLED', True)
    @patch('slack_notifier.config.SLACK_BOT_TOKEN', 'xoxb-test')
    @patch('slack_notifier.config.SLACK_CHANNEL_ID', 'C12345')
    def test_send_message_with_blocks(self, mock_web_client):
        """_send_message should send message with blocks when provided."""
        from slack_notifier import SlackNotifier

        mock_client = MagicMock()
        mock_web_client.return_value = mock_client

        notifier = SlackNotifier()
        blocks = [{"type": "section", "text": {"type": "plain_text", "text": "Test"}}]
        result = notifier._send_message("Test message", blocks=blocks)

        assert result == True
        mock_client.chat_postMessage.assert_called_once_with(
            channel='C12345',
            text="Test message",
            blocks=blocks
        )

    @patch('slack_notifier.WebClient')
    @patch('slack_notifier.SLACK_AVAILABLE', True)
    @patch('slack_notifier.config.SLACK_ENABLED', True)
    @patch('slack_notifier.config.SLACK_BOT_TOKEN', 'xoxb-test')
    @patch('slack_notifier.config.SLACK_CHANNEL_ID', 'C12345')
    def test_send_message_handles_slack_api_error(self, mock_web_client):
        """_send_message should return False on SlackApiError."""
        from slack_notifier import SlackNotifier
        from slack_sdk.errors import SlackApiError

        mock_client = MagicMock()
        mock_response = {'error': 'channel_not_found'}
        mock_client.chat_postMessage.side_effect = SlackApiError(
            message="Error", response=mock_response
        )
        mock_web_client.return_value = mock_client

        notifier = SlackNotifier()
        result = notifier._send_message("Test message")

        assert result == False

    @patch('slack_notifier.WebClient')
    @patch('slack_notifier.SLACK_AVAILABLE', True)
    @patch('slack_notifier.config.SLACK_ENABLED', True)
    @patch('slack_notifier.config.SLACK_BOT_TOKEN', 'xoxb-test')
    @patch('slack_notifier.config.SLACK_CHANNEL_ID', 'C12345')
    def test_send_message_handles_general_exception(self, mock_web_client):
        """_send_message should return False on general Exception."""
        from slack_notifier import SlackNotifier

        mock_client = MagicMock()
        mock_client.chat_postMessage.side_effect = Exception("Network error")
        mock_web_client.return_value = mock_client

        notifier = SlackNotifier()
        result = notifier._send_message("Test message")

        assert result == False

    @patch('slack_notifier.WebClient')
    @patch('slack_notifier.SLACK_AVAILABLE', True)
    @patch('slack_notifier.config.SLACK_ENABLED', True)
    @patch('slack_notifier.config.SLACK_BOT_TOKEN', 'xoxb-test')
    @patch('slack_notifier.config.SLACK_CHANNEL_ID', 'C12345')
    @patch('slack_notifier.config.SLACK_NOTIFY_IMPORTANT', True)
    @patch('slack_notifier.config.SLACK_IMPORTANT_KEYWORDS', ['urgent', 'payment'])
    def test_notify_important_email_with_keyword(self, mock_web_client):
        """notify_important_email should send notification for important email with keyword."""
        from slack_notifier import SlackNotifier, EmailNotification

        mock_client = MagicMock()
        mock_web_client.return_value = mock_client

        notifier = SlackNotifier()
        email = EmailNotification(
            subject="Urgent: Payment Required",
            sender="John Doe",
            sender_email="john@example.com",
            category="IMPORTANT",
            confidence=0.85,
            snippet="Please process the payment immediately"
        )

        result = notifier.notify_important_email(email)
        assert result == True
        mock_client.chat_postMessage.assert_called_once()

    @patch('slack_notifier.SLACK_AVAILABLE', True)
    @patch('slack_notifier.config.SLACK_ENABLED', True)
    @patch('slack_notifier.config.SLACK_BOT_TOKEN', 'xoxb-test')
    @patch('slack_notifier.config.SLACK_CHANNEL_ID', 'C12345')
    @patch('slack_notifier.config.SLACK_NOTIFY_IMPORTANT', False)
    def test_notify_important_email_disabled(self):
        """notify_important_email should return False when notifications disabled."""
        from slack_notifier import SlackNotifier, EmailNotification

        notifier = SlackNotifier()
        email = EmailNotification(
            subject="Important",
            sender="John",
            sender_email="john@example.com",
            category="IMPORTANT",
            confidence=0.95
        )

        result = notifier.notify_important_email(email)
        assert result == False

    @patch('slack_notifier.WebClient')
    @patch('slack_notifier.SLACK_AVAILABLE', True)
    @patch('slack_notifier.config.SLACK_ENABLED', True)
    @patch('slack_notifier.config.SLACK_BOT_TOKEN', 'xoxb-test')
    @patch('slack_notifier.config.SLACK_CHANNEL_ID', 'C12345')
    @patch('slack_notifier.config.SLACK_NOTIFY_SPAM_SUMMARY', True)
    def test_notify_processing_summary(self, mock_web_client):
        """notify_processing_summary should send summary notification."""
        from slack_notifier import SlackNotifier

        mock_client = MagicMock()
        mock_web_client.return_value = mock_client

        notifier = SlackNotifier()
        result = notifier.notify_processing_summary(
            total=100,
            categories={'IMPORTANT': 10, 'NORMAL': 50, 'INFO': 30, 'SPAM': 10},
            archived=30,
            spam=10
        )

        assert result == True
        mock_client.chat_postMessage.assert_called_once()

    @patch('slack_notifier.SLACK_AVAILABLE', True)
    @patch('slack_notifier.config.SLACK_ENABLED', True)
    @patch('slack_notifier.config.SLACK_BOT_TOKEN', 'xoxb-test')
    @patch('slack_notifier.config.SLACK_CHANNEL_ID', 'C12345')
    @patch('slack_notifier.config.SLACK_NOTIFY_SPAM_SUMMARY', True)
    def test_notify_processing_summary_no_emails(self):
        """notify_processing_summary should return False when no emails processed."""
        from slack_notifier import SlackNotifier

        notifier = SlackNotifier()
        result = notifier.notify_processing_summary(
            total=0,
            categories={},
            archived=0,
            spam=0
        )

        assert result == False

    @patch('slack_notifier.WebClient')
    @patch('slack_notifier.SLACK_AVAILABLE', True)
    @patch('slack_notifier.config.SLACK_ENABLED', True)
    @patch('slack_notifier.config.SLACK_BOT_TOKEN', 'xoxb-test')
    @patch('slack_notifier.config.SLACK_CHANNEL_ID', 'C12345')
    def test_notify_error(self, mock_web_client):
        """notify_error should send error notification."""
        from slack_notifier import SlackNotifier

        mock_client = MagicMock()
        mock_web_client.return_value = mock_client

        notifier = SlackNotifier()
        result = notifier.notify_error("Database connection failed")

        assert result == True
        mock_client.chat_postMessage.assert_called_once()
        args = mock_client.chat_postMessage.call_args
        assert "Database connection failed" in args.kwargs['text']

    def test_get_notifier_singleton(self):
        """get_notifier should return singleton instance."""
        from slack_notifier import get_notifier

        notifier1 = get_notifier()
        notifier2 = get_notifier()

        assert notifier1 is notifier2
