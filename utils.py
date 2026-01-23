"""
Gmail Organizer 유틸리티 모듈
공통 함수들을 모아놓은 모듈입니다.
"""
import json
import logging
from typing import Optional, Dict, Any, Union, Tuple

import config

logger = logging.getLogger(__name__)

# Safe sender cache (reloads when safe_senders.json changes)
_SAFE_CACHE_MTIME: Optional[float] = None
_SAFE_CACHE_PATH: Optional[str] = None
_SAFE_CACHE_SENDERS: set[str] = set()
_SAFE_CACHE_DOMAINS: set[str] = set()


def _get_safe_sender_sets() -> Tuple[set[str], set[str]]:
    """
    Returns lowercased safe sender/domain sets.

    Source of truth is `config.SAFE_SENDERS_FILE` (auto-learn updates this file).
    Falls back to `config.SAFE_SENDERS` / `config.SAFE_DOMAINS` when the file
    doesn't exist or can't be read.
    """
    global _SAFE_CACHE_MTIME, _SAFE_CACHE_PATH, _SAFE_CACHE_SENDERS, _SAFE_CACHE_DOMAINS

    safe_file = getattr(config, "SAFE_SENDERS_FILE", None)
    if safe_file is None:
        return ({s.lower() for s in config.SAFE_SENDERS}, {d.lower() for d in config.SAFE_DOMAINS})

    try:
        mtime = safe_file.stat().st_mtime
    except FileNotFoundError:
        return ({s.lower() for s in config.SAFE_SENDERS}, {d.lower() for d in config.SAFE_DOMAINS})
    except Exception as e:
        logger.debug(f"safe_senders 파일 stat 실패: {e}")
        return ({s.lower() for s in config.SAFE_SENDERS}, {d.lower() for d in config.SAFE_DOMAINS})

    safe_path = str(safe_file)
    if _SAFE_CACHE_PATH == safe_path and _SAFE_CACHE_MTIME == mtime:
        return (_SAFE_CACHE_SENDERS, _SAFE_CACHE_DOMAINS)

    try:
        with open(safe_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        senders = {s.lower() for s in data.get("senders", []) if isinstance(s, str)}
        domains = {d.lower() for d in data.get("domains", []) if isinstance(d, str)}

        _SAFE_CACHE_MTIME = mtime
        _SAFE_CACHE_PATH = safe_path
        _SAFE_CACHE_SENDERS = senders
        _SAFE_CACHE_DOMAINS = domains
        return (senders, domains)
    except Exception as e:
        logger.debug(f"safe_senders.json 로드 실패: {e}")
        return ({s.lower() for s in config.SAFE_SENDERS}, {d.lower() for d in config.SAFE_DOMAINS})


def is_safe_sender(email_or_str: Union[str, Any]) -> bool:
    """
    신뢰할 수 있는 발신자인지 확인합니다.

    Args:
        email_or_str: Email 객체 또는 발신자 이메일 주소 문자열

    Returns:
        bool: 신뢰 발신자면 True
    """
    # Email 객체인 경우 sender_email 속성 추출
    if hasattr(email_or_str, 'sender_email'):
        sender_email = email_or_str.sender_email
    else:
        sender_email = email_or_str

    sender_email = (sender_email or "").lower().strip()

    # 빈 이메일 체크
    if not sender_email:
        return False

    safe_senders, safe_domains = _get_safe_sender_sets()

    # SAFE_SENDERS에 있는지 확인
    if sender_email in safe_senders:
        return True

    # 도메인 확인
    if "@" in sender_email:
        domain = sender_email.split("@", 1)[1]
        if domain in safe_domains:
            return True

    return False


def extract_json_from_response(response_text: str) -> Dict[str, Any]:
    """
    AI 응답에서 JSON을 추출합니다.

    Args:
        response_text: AI 응답 텍스트

    Returns:
        dict: 파싱된 JSON 객체

    Raises:
        json.JSONDecodeError: JSON 파싱 실패 시
    """
    text = response_text.strip()

    # ```json ... ``` 블록 추출
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    return json.loads(text)


def safe_json_loads(text: str, default: Optional[Dict] = None) -> Dict[str, Any]:
    """
    안전하게 JSON을 파싱합니다. 실패 시 기본값 반환.

    Args:
        text: JSON 문자열
        default: 파싱 실패 시 반환할 기본값

    Returns:
        dict: 파싱된 JSON 또는 기본값
    """
    if default is None:
        default = {}

    try:
        return extract_json_from_response(text)
    except (json.JSONDecodeError, IndexError, AttributeError) as e:
        logger.debug(f"JSON 파싱 실패: {e}")
        return default


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    텍스트를 최대 길이로 자릅니다.

    Args:
        text: 원본 텍스트
        max_length: 최대 길이
        suffix: 잘린 경우 추가할 접미사

    Returns:
        str: 잘린 텍스트
    """
    if not text:
        return ""

    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix
