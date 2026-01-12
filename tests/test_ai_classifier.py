"""
ai_classifier.py 테스트
"""
import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from dataclasses import dataclass
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class MockEmailForTest:
    """테스트용 Mock 이메일"""
    id: str
    subject: str
    sender: str
    sender_email: str
    body: str


class TestClassificationCache:
    """분류 캐시 테스트"""

    def test_cache_set_and_get(self):
        """캐시 저장 및 조회"""
        from ai_classifier import ClassificationCache, ClassificationResult

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ClassificationCache(cache_dir=Path(tmpdir))

            email = MockEmailForTest(
                id="test_email_123",
                subject="테스트 이메일",
                sender="Test Sender",
                sender_email="test@example.com",
                body="테스트 본문"
            )

            result = ClassificationResult(
                email_id="test_email_123",
                category="NORMAL",
                confidence=0.9,
                reason="테스트 이유",
                suggested_action="keep",
                priority=3
            )

            # 캐시에 저장
            cache.set(email, result)

            # 캐시에서 조회
            cached = cache.get(email)
            assert cached is not None
            assert cached.email_id == "test_email_123"
            assert cached.category == "NORMAL"
            assert cached.confidence == 0.9

    def test_cache_miss(self):
        """캐시 미스"""
        from ai_classifier import ClassificationCache

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ClassificationCache(cache_dir=Path(tmpdir))

            email = MockEmailForTest(
                id="nonexistent_email",
                subject="없는 이메일",
                sender="Test",
                sender_email="test@example.com",
                body="본문"
            )

            cached = cache.get(email)
            assert cached is None

    def test_cache_stats(self):
        """캐시 통계"""
        from ai_classifier import ClassificationCache

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ClassificationCache(cache_dir=Path(tmpdir))
            stats = cache.stats()

            assert "total_entries" in stats
            assert "max_size" in stats

    def test_cache_clear(self):
        """캐시 전체 삭제"""
        from ai_classifier import ClassificationCache, ClassificationResult

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ClassificationCache(cache_dir=Path(tmpdir))

            email = MockEmailForTest(
                id="test_email",
                subject="테스트",
                sender="Test",
                sender_email="test@example.com",
                body="본문"
            )

            result = ClassificationResult(
                email_id="test_email",
                category="NORMAL",
                confidence=0.9,
                reason="이유",
                suggested_action="keep",
                priority=3
            )

            cache.set(email, result)
            assert cache.get(email) is not None

            cache.clear()
            assert cache.get(email) is None


class TestEmailClassifierWithCache:
    """캐시를 사용하는 이메일 분류기 테스트"""

    @patch('ai_classifier.genai')
    def test_classifier_init_with_cache(self, mock_genai):
        """캐시가 활성화된 분류기 초기화"""
        from ai_classifier import EmailClassifier
        import config

        # Mock API key
        with patch.object(config, 'GEMINI_API_KEY', 'test_api_key'):
            classifier = EmailClassifier(use_cache=True)
            assert classifier.cache is not None

    @patch('ai_classifier.genai')
    def test_classifier_init_without_cache(self, mock_genai):
        """캐시가 비활성화된 분류기 초기화"""
        from ai_classifier import EmailClassifier
        import config

        with patch.object(config, 'GEMINI_API_KEY', 'test_api_key'):
            classifier = EmailClassifier(use_cache=False)
            assert classifier.cache is None

    @patch('ai_classifier.genai')
    def test_cache_stats_method(self, mock_genai):
        """캐시 통계 메서드"""
        from ai_classifier import EmailClassifier
        import config

        with patch.object(config, 'GEMINI_API_KEY', 'test_api_key'):
            classifier = EmailClassifier(use_cache=True)
            stats = classifier.get_cache_stats()

            assert "cache_hits" in stats
            assert "cache_misses" in stats
            assert "hit_rate" in stats
            assert stats["cache_hits"] == 0
            assert stats["cache_misses"] == 0
