"""Tests for scheduler module."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import threading
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestGmailScheduler:
    """Tests for GmailScheduler class."""

    @patch('scheduler.get_gmail_credentials')
    @patch('scheduler.GmailClient')
    @patch('scheduler.EmailClassifier')
    def test_scheduler_initialization(self, mock_classifier, mock_client, mock_creds):
        """Scheduler should initialize with correct defaults."""
        from scheduler import GmailScheduler

        mock_creds.return_value = Mock()

        scheduler = GmailScheduler(
            interval_minutes=30,
            batch_size=50,
            auto_organize=False
        )

        assert scheduler.interval_minutes == 30
        assert scheduler.batch_size == 50
        assert scheduler.auto_organize == False

    @patch('scheduler.get_gmail_credentials')
    @patch('scheduler.GmailClient')
    @patch('scheduler.EmailClassifier')
    def test_scheduler_stop(self, mock_classifier, mock_client, mock_creds):
        """Scheduler should stop gracefully."""
        from scheduler import GmailScheduler

        mock_creds.return_value = Mock()

        scheduler = GmailScheduler()
        scheduler.running = True
        scheduler.stop()

        assert scheduler.running == False

    @patch('scheduler.get_gmail_credentials')
    @patch('scheduler.GmailClient')
    @patch('scheduler.EmailClassifier')
    def test_scheduler_default_values(self, mock_classifier, mock_client, mock_creds):
        """Scheduler should have sensible default values."""
        from scheduler import GmailScheduler

        mock_creds.return_value = Mock()

        scheduler = GmailScheduler()

        assert scheduler.interval_minutes == 30  # Default from init
        assert scheduler.auto_organize == True
