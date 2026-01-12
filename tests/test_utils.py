"""
utils.py 테스트
"""
import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import is_safe_sender, extract_json_from_response, safe_json_loads, truncate_text


class TestIsSafeSender:
    """is_safe_sender 함수 테스트"""

    def test_safe_sender_in_list(self):
        """SAFE_SENDERS에 있는 발신자"""
        # safe_senders.json에 있는 발신자
        assert is_safe_sender("noreply@github.com") is True

    def test_safe_domain(self):
        """SAFE_DOMAINS에 있는 도메인"""
        assert is_safe_sender("someone@google.com") is True
        assert is_safe_sender("anyone@naver.com") is True

    def test_unsafe_sender(self):
        """신뢰 목록에 없는 발신자"""
        assert is_safe_sender("spam@unknown-domain.xyz") is False

    def test_empty_email(self):
        """빈 이메일"""
        assert is_safe_sender("") is False
        assert is_safe_sender(None) is False

    def test_case_insensitive(self):
        """대소문자 구분 없이 작동"""
        assert is_safe_sender("NOREPLY@GITHUB.COM") is True
        assert is_safe_sender("Someone@Google.Com") is True


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
