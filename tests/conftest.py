"""
pytest 설정 및 공통 fixture
"""
import pytest
from unittest.mock import Mock, MagicMock
from dataclasses import dataclass
from datetime import datetime
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class MockEmail:
    """테스트용 Mock Email 객체"""
    id: str
    subject: str
    sender: str
    sender_email: str
    body: str
    date: str = ""
    labels: list = None

    def __post_init__(self):
        if self.labels is None:
            self.labels = []


@pytest.fixture
def mock_email():
    """기본 Mock 이메일 fixture"""
    return MockEmail(
        id="test123",
        subject="테스트 이메일 제목",
        sender="테스트 발신자",
        sender_email="test@example.com",
        body="테스트 이메일 본문 내용입니다.",
        date=datetime.now().isoformat()
    )


@pytest.fixture
def mock_spam_email():
    """스팸 Mock 이메일 fixture"""
    return MockEmail(
        id="spam123",
        subject="[광고] 무료 복권 당첨! 지금 클릭하세요!",
        sender="Unknown Sender",
        sender_email="spam@unknown-domain.xyz",
        body="축하합니다! 100만원 당첨! 지금 바로 클릭하세요!",
        date=datetime.now().isoformat()
    )


@pytest.fixture
def mock_important_email():
    """중요 Mock 이메일 fixture"""
    return MockEmail(
        id="important123",
        subject="[보안] 비밀번호 변경 인증코드: 123456",
        sender="Google Security",
        sender_email="noreply@google.com",
        body="귀하의 계정에서 비밀번호 변경 요청이 있었습니다. 인증코드: 123456",
        date=datetime.now().isoformat()
    )


@pytest.fixture
def mock_gmail_client():
    """Mock Gmail 클라이언트 fixture"""
    client = Mock()
    client.service = Mock()
    client.get_emails = Mock(return_value=[])
    client.apply_label = Mock(return_value=True)
    client.archive_email = Mock(return_value=True)
    client.mark_as_spam = Mock(return_value=True)
    client.get_or_create_label = Mock(return_value="label123")
    client.get_profile = Mock(return_value={"emailAddress": "test@gmail.com"})
    return client


@pytest.fixture
def mock_genai_client():
    """Mock Gemini AI 클라이언트 fixture"""
    client = Mock()
    mock_response = Mock()
    mock_response.text = '''{"category": "NORMAL", "confidence": 0.9, "reason": "일반 이메일", "priority": 3, "suggested_action": "keep"}'''
    client.models.generate_content = Mock(return_value=mock_response)
    return client
