"""
config.py 테스트
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config


class TestConfig:
    """설정 파일 테스트"""

    def test_base_dir_exists(self):
        """BASE_DIR이 유효한 경로"""
        assert config.BASE_DIR.exists()

    def test_openai_models_not_empty(self):
        """OPENAI_MODELS 목록이 비어있지 않음"""
        assert len(config.OPENAI_MODELS) > 0

    def test_openai_model_is_first_in_list(self):
        """현재 OPENAI_MODEL이 목록의 첫 번째"""
        assert config.OPENAI_MODEL == config.OPENAI_MODELS[0]

    def test_email_categories_valid(self):
        """EMAIL_CATEGORIES 구조 확인"""
        required_categories = ['IMPORTANT', 'NORMAL', 'INFO', 'SPAM']
        for cat in required_categories:
            assert cat in config.EMAIL_CATEGORIES
            assert 'name' in config.EMAIL_CATEGORIES[cat]
            assert 'action' in config.EMAIL_CATEGORIES[cat]

    def test_safe_senders_loaded(self):
        """SAFE_SENDERS가 로드됨"""
        assert isinstance(config.SAFE_SENDERS, set)

    def test_safe_domains_loaded(self):
        """SAFE_DOMAINS가 로드됨"""
        assert isinstance(config.SAFE_DOMAINS, set)

    def test_label_prefix_not_empty(self):
        """LABEL_PREFIX가 설정됨"""
        assert config.LABEL_PREFIX
        assert len(config.LABEL_PREFIX) > 0

    def test_spam_threshold_valid(self):
        """SPAM_CONFIDENCE_THRESHOLD가 0-1 사이"""
        assert 0 <= config.SPAM_CONFIDENCE_THRESHOLD <= 1

    def test_setup_logging_returns_logger(self):
        """setup_logging이 Logger 인스턴스를 반환"""
        import logging
        logger = config.setup_logging(name="test_logger")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logger"

    def test_log_dir_exists(self):
        """LOG_DIR이 존재"""
        assert config.LOG_DIR.exists()

    def test_api_retry_constants(self):
        """API 재시도 상수가 유효"""
        assert config.MAX_API_RETRIES > 0
        assert config.API_RETRY_DELAY_BASE > 0

    def test_display_length_constants(self):
        """표시 길이 상수가 유효"""
        assert config.SUBJECT_DISPLAY_LENGTH > 0
        assert config.EMAIL_DISPLAY_LENGTH > 0
        assert config.PROMPT_BODY_LENGTH > 0
