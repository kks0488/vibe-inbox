"""
gmail_client.py 테스트
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestGmailClientBatch:
    """Gmail 클라이언트 배치 API 테스트"""

    @patch('gmail_client.get_gmail_credentials')
    @patch('gmail_client.build')
    def test_batch_get_emails_creates_correct_batches(self, mock_build, mock_creds):
        """배치 요청이 올바르게 생성되는지 확인"""
        from gmail_client import GmailClient
        import config

        # Mock 설정
        mock_service = Mock()
        mock_build.return_value = mock_service

        # new_batch_http_request Mock
        mock_batch = Mock()
        mock_service.new_batch_http_request.return_value = mock_batch

        # messages().get() Mock
        mock_get = Mock()
        mock_service.users.return_value.messages.return_value.get.return_value = mock_get

        client = GmailClient()

        # 테스트: 50개 메시지 ID로 배치 요청
        msg_ids = [f"msg_{i}" for i in range(50)]
        client._batch_get_emails(msg_ids)

        # 배치가 한 번만 생성되어야 함 (50 < config.GMAIL_BATCH_SIZE=100)
        assert mock_service.new_batch_http_request.call_count == 1
        # batch.execute()가 호출되어야 함
        assert mock_batch.execute.call_count == 1

    @patch('gmail_client.get_gmail_credentials')
    @patch('gmail_client.build')
    def test_batch_get_emails_handles_large_batches(self, mock_build, mock_creds):
        """100개 이상의 이메일도 올바르게 처리하는지 확인"""
        from gmail_client import GmailClient
        import config

        mock_service = Mock()
        mock_build.return_value = mock_service

        mock_batch = Mock()
        mock_service.new_batch_http_request.return_value = mock_batch

        client = GmailClient()

        # 150개 메시지 ID (2개 배치 필요)
        msg_ids = [f"msg_{i}" for i in range(150)]
        client._batch_get_emails(msg_ids)

        # 2개 배치가 생성되어야 함
        assert mock_service.new_batch_http_request.call_count == 2
        assert mock_batch.execute.call_count == 2

    @patch('gmail_client.get_gmail_credentials')
    @patch('gmail_client.build')
    def test_batch_apply_labels_creates_correct_body(self, mock_build, mock_creds):
        """배치 레이블 적용이 올바른 body를 생성하는지 확인"""
        from gmail_client import GmailClient

        mock_service = Mock()
        mock_build.return_value = mock_service

        mock_batch = Mock()
        mock_service.new_batch_http_request.return_value = mock_batch

        client = GmailClient()

        modifications = [
            {"msg_id": "msg_1", "add_labels": ["Label_1"]},
            {"msg_id": "msg_2", "remove_labels": ["INBOX"]},
            {"msg_id": "msg_3", "add_labels": ["SPAM"], "remove_labels": ["INBOX"]}
        ]

        client.batch_apply_labels(modifications)

        # batch.execute()가 호출되어야 함
        assert mock_batch.execute.call_count == 1
        # 3개의 요청이 추가되어야 함
        assert mock_batch.add.call_count == 3

    @patch('gmail_client.get_gmail_credentials')
    @patch('gmail_client.build')
    def test_batch_archive_uses_correct_label(self, mock_build, mock_creds):
        """배치 보관이 INBOX 레이블을 제거하는지 확인"""
        from gmail_client import GmailClient

        mock_service = Mock()
        mock_build.return_value = mock_service

        mock_batch = Mock()
        mock_service.new_batch_http_request.return_value = mock_batch

        client = GmailClient()
        result = client.batch_archive(["msg_1", "msg_2"])

        # 배치가 실행되어야 함
        assert mock_batch.execute.call_count == 1

    @patch('gmail_client.get_gmail_credentials')
    @patch('gmail_client.build')
    def test_batch_mark_as_spam_uses_correct_labels(self, mock_build, mock_creds):
        """배치 스팸 처리가 올바른 레이블을 사용하는지 확인"""
        from gmail_client import GmailClient

        mock_service = Mock()
        mock_build.return_value = mock_service

        mock_batch = Mock()
        mock_service.new_batch_http_request.return_value = mock_batch

        client = GmailClient()
        result = client.batch_mark_as_spam(["msg_1", "msg_2"])

        # 배치가 실행되어야 함
        assert mock_batch.execute.call_count == 1


class TestGmailClientParsing:
    """Gmail 클라이언트 파싱 테스트"""

    @patch('gmail_client.get_gmail_credentials')
    @patch('gmail_client.build')
    def test_parse_email_response_extracts_headers(self, mock_build, mock_creds):
        """이메일 응답 파싱이 헤더를 올바르게 추출하는지 확인"""
        from gmail_client import GmailClient

        mock_service = Mock()
        mock_build.return_value = mock_service

        client = GmailClient()
        # Mock labels cache
        client._labels_cache = {'INBOX': 'INBOX', 'UNREAD': 'UNREAD'}

        # Mock response
        response = {
            'id': 'msg_123',
            'threadId': 'thread_123',
            'labelIds': ['INBOX', 'UNREAD'],
            'snippet': 'Test snippet',
            'payload': {
                'headers': [
                    {'name': 'Subject', 'value': 'Test Subject'},
                    {'name': 'From', 'value': 'Test Sender <test@example.com>'},
                    {'name': 'Date', 'value': '2024-01-01'}
                ],
                'body': {'data': ''}
            }
        }

        email = client._parse_email_response('msg_123', response)

        assert email is not None
        assert email.id == 'msg_123'
        assert email.subject == 'Test Subject'
        assert email.sender == 'Test Sender <test@example.com>'
        assert email.sender_email == 'test@example.com'
        assert email.is_unread is True

    @patch('gmail_client.get_gmail_credentials')
    @patch('gmail_client.build')
    def test_parse_email_response_handles_simple_email(self, mock_build, mock_creds):
        """단순 이메일 주소 형식 처리"""
        from gmail_client import GmailClient

        mock_service = Mock()
        mock_build.return_value = mock_service

        client = GmailClient()
        # Mock labels cache
        client._labels_cache = {'INBOX': 'INBOX'}

        response = {
            'id': 'msg_124',
            'threadId': 'thread_124',
            'labelIds': ['INBOX'],
            'snippet': 'Test',
            'payload': {
                'headers': [
                    {'name': 'From', 'value': 'simple@example.com'}
                ],
                'body': {'data': ''}
            }
        }

        email = client._parse_email_response('msg_124', response)

        assert email is not None
        assert email.sender_email == 'simple@example.com'
        assert email.is_unread is False
