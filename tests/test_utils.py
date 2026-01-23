"""
utils.py 테스트
"""
import pytest
import json
import sys
from pathlib import Path
from unittest.mock import Mock
import os
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import is_safe_sender, extract_json_from_response, safe_json_loads, truncate_text
import config


class TestIsSafeSender:
    """is_safe_sender 함수 테스트"""

    def _write_safe_senders_file(self, path: Path, senders=None, domains=None):
        senders = senders or []
        domains = domains or []
        path.write_text(
            json.dumps(
                {
                    "description": "test",
                    "updated_at": "2026-01-01",
                    "senders": senders,
                    "domains": domains,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def test_safe_sender_in_list(self, tmp_path, monkeypatch):
        """SAFE_SENDERS에 있는 발신자"""
        # 파일 기반 safe_senders 로드
        tmp = tmp_path / "safe_senders.json"
        self._write_safe_senders_file(tmp, senders=["noreply@github.com"])
        monkeypatch.setattr(config, "SAFE_SENDERS_FILE", tmp, raising=False)
        assert is_safe_sender("noreply@github.com") is True

    def test_safe_domain(self, tmp_path, monkeypatch):
        """SAFE_DOMAINS에 있는 도메인"""
        tmp = tmp_path / "safe_senders.json"
        self._write_safe_senders_file(tmp, domains=["google.com", "naver.com"])
        monkeypatch.setattr(config, "SAFE_SENDERS_FILE", tmp, raising=False)
        assert is_safe_sender("someone@google.com") is True
        assert is_safe_sender("anyone@naver.com") is True

    def test_unsafe_sender(self, tmp_path, monkeypatch):
        """신뢰 목록에 없는 발신자"""
        tmp = tmp_path / "safe_senders.json"
        self._write_safe_senders_file(tmp, senders=["noreply@github.com"], domains=["google.com"])
        monkeypatch.setattr(config, "SAFE_SENDERS_FILE", tmp, raising=False)
        assert is_safe_sender("spam@unknown-domain.xyz") is False

    def test_empty_email(self, tmp_path, monkeypatch):
        """빈 이메일"""
        tmp = tmp_path / "safe_senders.json"
        self._write_safe_senders_file(tmp)
        monkeypatch.setattr(config, "SAFE_SENDERS_FILE", tmp, raising=False)
        assert is_safe_sender("") is False
        assert is_safe_sender(None) is False

    def test_case_insensitive(self, tmp_path, monkeypatch):
        """대소문자 구분 없이 작동"""
        tmp = tmp_path / "safe_senders.json"
        self._write_safe_senders_file(tmp, senders=["noreply@github.com"], domains=["google.com"])
        monkeypatch.setattr(config, "SAFE_SENDERS_FILE", tmp, raising=False)
        assert is_safe_sender("NOREPLY@GITHUB.COM") is True
        assert is_safe_sender("Someone@Google.Com") is True

    def test_with_email_object_safe_sender(self, tmp_path, monkeypatch):
        """Email 객체로 호출 - SAFE_SENDERS에 있는 발신자"""
        tmp = tmp_path / "safe_senders.json"
        self._write_safe_senders_file(tmp, senders=["noreply@github.com"])
        monkeypatch.setattr(config, "SAFE_SENDERS_FILE", tmp, raising=False)
        email = Mock()
        email.sender_email = "noreply@github.com"
        assert is_safe_sender(email) is True

    def test_with_email_object_safe_domain(self, tmp_path, monkeypatch):
        """Email 객체로 호출 - SAFE_DOMAINS에 있는 도메인"""
        tmp = tmp_path / "safe_senders.json"
        self._write_safe_senders_file(tmp, domains=["google.com"])
        monkeypatch.setattr(config, "SAFE_SENDERS_FILE", tmp, raising=False)
        email = Mock()
        email.sender_email = "user@google.com"
        assert is_safe_sender(email) is True

    def test_with_email_object_unsafe(self, tmp_path, monkeypatch):
        """Email 객체로 호출 - 신뢰 목록에 없는 발신자"""
        tmp = tmp_path / "safe_senders.json"
        self._write_safe_senders_file(tmp, senders=["noreply@github.com"], domains=["google.com"])
        monkeypatch.setattr(config, "SAFE_SENDERS_FILE", tmp, raising=False)
        email = Mock()
        email.sender_email = "spam@unknown-domain.xyz"
        assert is_safe_sender(email) is False

    def test_with_email_object_none_sender(self, tmp_path, monkeypatch):
        """Email 객체로 호출 - sender_email이 None"""
        tmp = tmp_path / "safe_senders.json"
        self._write_safe_senders_file(tmp)
        monkeypatch.setattr(config, "SAFE_SENDERS_FILE", tmp, raising=False)
        email = Mock()
        email.sender_email = None
        assert is_safe_sender(email) is False

    def test_safe_sender_file_reload(self, tmp_path, monkeypatch):
        """safe_senders.json 변경 시 재로드"""
        tmp = tmp_path / "safe_senders.json"
        self._write_safe_senders_file(tmp, senders=["first@example.com"])
        monkeypatch.setattr(config, "SAFE_SENDERS_FILE", tmp, raising=False)

        assert is_safe_sender("first@example.com") is True
        assert is_safe_sender("second@example.com") is False

        # 파일 갱신 + mtime 변경 보장
        time.sleep(0.01)
        self._write_safe_senders_file(tmp, senders=["second@example.com"])
        os.utime(tmp, None)

        assert is_safe_sender("first@example.com") is False
        assert is_safe_sender("second@example.com") is True


class TestExtractJsonFromResponse:
    """extract_json_from_response 함수 테스트"""

    def test_plain_json(self):
        """일반 JSON 문자열"""
        text = '{"key": "value"}'
        result = extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_json_with_code_block(self):
        """```json 블록으로 감싸진 JSON"""
        text = '''Here is the result:
```json
{"category": "SPAM", "confidence": 0.95}
```
Done!'''
        result = extract_json_from_response(text)
        assert result["category"] == "SPAM"
        assert result["confidence"] == 0.95

    def test_json_with_simple_code_block(self):
        """``` 블록으로 감싸진 JSON"""
        text = '''```
{"test": true}
```'''
        result = extract_json_from_response(text)
        assert result["test"] is True

    def test_invalid_json_raises_error(self):
        """잘못된 JSON은 에러 발생"""
        with pytest.raises(json.JSONDecodeError):
            extract_json_from_response("not json")


class TestSafeJsonLoads:
    """safe_json_loads 함수 테스트"""

    def test_valid_json(self):
        """유효한 JSON"""
        result = safe_json_loads('{"key": "value"}')
        assert result == {"key": "value"}

    def test_invalid_json_returns_default(self):
        """잘못된 JSON은 기본값 반환"""
        result = safe_json_loads("invalid")
        assert result == {}

    def test_custom_default(self):
        """커스텀 기본값"""
        result = safe_json_loads("invalid", default={"default": True})
        assert result == {"default": True}


class TestTruncateText:
    """truncate_text 함수 테스트"""

    def test_short_text_unchanged(self):
        """짧은 텍스트는 그대로"""
        assert truncate_text("hello", 10) == "hello"

    def test_long_text_truncated(self):
        """긴 텍스트는 잘림"""
        result = truncate_text("hello world", 8)
        assert result == "hello..."
        assert len(result) == 8

    def test_custom_suffix(self):
        """커스텀 접미사"""
        result = truncate_text("hello world", 8, suffix="~")
        assert result == "hello w~"

    def test_empty_text(self):
        """빈 텍스트"""
        assert truncate_text("", 10) == ""
        assert truncate_text(None, 10) == ""
