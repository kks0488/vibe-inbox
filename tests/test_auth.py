"""
auth.py 테스트
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestGetTokenExpiryInfo:
    """get_token_expiry_info 함수 테스트"""

    def test_returns_none_for_no_creds(self):
        """자격 증명이 없으면 None 반환"""
        from auth import get_token_expiry_info
        result = get_token_expiry_info(None)
        assert result is None

    def test_returns_none_for_no_expiry(self):
        """만료 시간이 없으면 None 반환"""
        from auth import get_token_expiry_info

        mock_creds = Mock()
        mock_creds.expiry = None

        result = get_token_expiry_info(mock_creds)
        assert result is None

    def test_returns_expired_status(self):
        """만료된 토큰 상태 반환"""
        from auth import get_token_expiry_info

        mock_creds = Mock()
        mock_creds.expiry = datetime.now(timezone.utc) - timedelta(hours=1)

        result = get_token_expiry_info(mock_creds)
        assert result is not None
        hours_remaining, status = result
        assert hours_remaining <= 0
        assert status == "expired"

    def test_returns_critical_status(self):
        """임계 상태 반환 (만료 1시간 미만)"""
        from auth import get_token_expiry_info
        import config

        mock_creds = Mock()
        # 30분 후 만료
        mock_creds.expiry = datetime.now(timezone.utc) + timedelta(minutes=30)

        result = get_token_expiry_info(mock_creds)
        assert result is not None
        hours_remaining, status = result
        assert status == "critical"
        assert hours_remaining < config.TOKEN_AUTO_REFRESH_HOURS

    def test_returns_warning_status(self):
        """경고 상태 반환 (만료 24시간 미만)"""
        from auth import get_token_expiry_info
        import config

        mock_creds = Mock()
        # 12시간 후 만료
        mock_creds.expiry = datetime.now(timezone.utc) + timedelta(hours=12)

        result = get_token_expiry_info(mock_creds)
        assert result is not None
        hours_remaining, status = result
        assert status == "warning"
        assert hours_remaining < config.TOKEN_EXPIRY_WARNING_HOURS

    def test_returns_ok_status(self):
        """정상 상태 반환 (만료 24시간 이상)"""
        from auth import get_token_expiry_info
        import config

        mock_creds = Mock()
        # 48시간 후 만료
        mock_creds.expiry = datetime.now(timezone.utc) + timedelta(hours=48)

        result = get_token_expiry_info(mock_creds)
        assert result is not None
        hours_remaining, status = result
        assert status == "ok"
        assert hours_remaining > config.TOKEN_EXPIRY_WARNING_HOURS


class TestTokenExpiryConfig:
    """토큰 만료 설정 테스트"""

    def test_token_expiry_warning_hours_configured(self):
        """TOKEN_EXPIRY_WARNING_HOURS가 설정됨"""
        import config
        assert hasattr(config, 'TOKEN_EXPIRY_WARNING_HOURS')
        assert config.TOKEN_EXPIRY_WARNING_HOURS > 0

    def test_token_auto_refresh_hours_configured(self):
        """TOKEN_AUTO_REFRESH_HOURS가 설정됨"""
        import config
        assert hasattr(config, 'TOKEN_AUTO_REFRESH_HOURS')
        assert config.TOKEN_AUTO_REFRESH_HOURS > 0

    def test_auto_refresh_less_than_warning(self):
        """자동 갱신 시간이 경고 시간보다 작음"""
        import config
        assert config.TOKEN_AUTO_REFRESH_HOURS < config.TOKEN_EXPIRY_WARNING_HOURS
