"""
Gmail Organizer 설정 파일
"""
import os
import sys
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# 로그 디렉토리
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 로깅 설정
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    name: str = "gmail-organizer",
    log_file: str = None,
    level: str = None,
    use_rich: bool = False
) -> logging.Logger:
    """
    통합 로깅 설정

    Args:
        name: 로거 이름
        log_file: 로그 파일 이름 (없으면 {name}.log)
        level: 로그 레벨 (없으면 환경변수 또는 INFO)
        use_rich: Rich 핸들러 사용 여부

    Returns:
        설정된 Logger 인스턴스
    """
    level = level or LOG_LEVEL
    log_file = log_file or f"{name}.log"

    # 로그 레벨 설정
    log_level = getattr(logging, level.upper(), logging.INFO)

    # 핸들러 설정
    handlers = []

    # 파일 핸들러
    file_handler = logging.FileHandler(
        LOG_DIR / log_file,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    handlers.append(file_handler)

    # 콘솔 핸들러 (Rich 또는 기본)
    if use_rich:
        try:
            from rich.logging import RichHandler
            handlers.append(RichHandler(rich_tracebacks=True))
        except ImportError:
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
            handlers.append(stream_handler)
    else:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        handlers.append(stream_handler)

    # 기본 로깅 설정
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
        force=True
    )

    return logging.getLogger(name)

# .env 파일 로드
load_dotenv()

# 프로젝트 루트 디렉토리
BASE_DIR = Path(__file__).parent

# OpenAI Compatible API 설정 (로컬 프록시)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:8317/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")

# 모델 폴백 지원
OPENAI_MODELS = [
    OPENAI_MODEL,       # 기본 모델
    "gpt-5.1",          # 폴백 1
    "gpt-5",            # 폴백 2
]

# Gmail OAuth 설정
GMAIL_CREDENTIALS_PATH = os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
GMAIL_TOKEN_PATH = BASE_DIR / "token.json"
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]

# 레이블 접두사 및 안전 설정
LABEL_PREFIX = "AI/"          # 모든 자동 레이블 앞에 붙는 접두사 (스케줄러/CLI 공통 사용)
OLD_LABEL_PREFIX = "AI분류/"   # 과거 접두사 (이 레이블도 건너뛰도록 허용)

# 안전/보호 옵션
SPAM_CONFIDENCE_THRESHOLD = 0.9   # 스팸 이동 최소 확신도
SKIP_ALREADY_CLASSIFIED = os.getenv("SKIP_ALREADY_CLASSIFIED", "true").lower() == "true"

# 신뢰 발신자/도메인: 외부 파일에서 로드 (safe_senders.json)
# 자동 보관/스팸 금지, 레이블만 적용
def _load_safe_senders():
    """외부 파일에서 신뢰 발신자/도메인 로드"""
    safe_senders_file = BASE_DIR / "safe_senders.json"
    default_senders = set()
    default_domains = set()

    if safe_senders_file.exists():
        try:
            with open(safe_senders_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return (
                    set(data.get("senders", [])),
                    set(data.get("domains", []))
                )
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"safe_senders.json 로드 실패: {e}")

    return default_senders, default_domains

SAFE_SENDERS, SAFE_DOMAINS = _load_safe_senders()

# 이메일 분류 카테고리 (간소화 버전 - 4개)
# 기본값을 'keep'으로 두어 레이블만 적용하는 안전 모드를 기본으로 합니다.
EMAIL_CATEGORIES = {
    "IMPORTANT": {
        "name": "중요",
        "description": "중요한 업무 이메일, 긴급한 요청, 개인적으로 중요한 메일, 보안 알림, 결제/금융 관련",
        "color": "#ff0000",
        "action": "keep"
    },
    "NORMAL": {
        "name": "일반",
        "description": "일반적인 커뮤니케이션, 알림, 일상적인 이메일, 서비스 알림",
        "color": "#4285f4",
        "action": "keep"
    },
    "INFO": {
        "name": "정보",
        "description": "뉴스레터, 구독 서비스, 프로모션, 광고, 마케팅, 소셜 미디어 알림, SNS 관련",
        "color": "#34a853",
        "action": "archive"  # 다시 자동 보관 활성화 (스팸 이동 없음)
    },
    "SPAM": {
        "name": "스팸",
        "description": "스팸, 피싱, 사기성 메일, 불필요한 광고, 구독 취소 권장",
        "color": "#ea4335",
        "action": "spam"  # 확신도 기준을 통과한 경우에만 스팸함으로 이동
    }
}

# 처리 옵션
DEFAULT_BATCH_SIZE = 50  # 한 번에 처리할 이메일 수
MAX_EMAIL_CONTENT_LENGTH = 2000  # AI에 전달할 이메일 내용 최대 길이

# API 재시도 설정
MAX_API_RETRIES = 3  # API 호출 최대 재시도 횟수
API_RETRY_DELAY_BASE = 2  # Exponential backoff 기본 대기 시간 (초)

# 분류 기본값
DEFAULT_CONFIDENCE = 0.5  # 기본 신뢰도
FALLBACK_CONFIDENCE = 0.3  # 파싱 실패 시 기본 신뢰도
DEFAULT_PRIORITY = 3  # 기본 우선순위 (1-5)
CATEGORY_CACHE_THRESHOLD = 0.7  # 캐싱할 최소 신뢰도

# AI 배치 분류 설정
AI_BATCH_SIZE = 5  # AI 배치 분류 크기
PROMPT_BODY_LENGTH = 1800  # 분류 프롬프트에 사용할 본문 길이
BATCH_BODY_PREVIEW = 300  # 배치 프롬프트에 사용할 본문 미리보기 길이
MAX_SUBJECTS_FOR_ANALYSIS = 5  # 발신자 분석에 사용할 최근 제목 수

# 텍스트 표시 길이
SUBJECT_DISPLAY_LENGTH = 60  # 제목 표시 길이
SUBJECT_PREVIEW_LENGTH = 30  # 제목 미리보기 (에러 메시지용)
EMAIL_DISPLAY_LENGTH = 35  # 이메일 주소 표시 길이
SUBJECT_TRUNCATE_LENGTH = 80  # 제목 자르기 길이

# 이메일 조회 설정
RECENT_DAYS = 7  # 최근 이메일 조회 기간 (일)
MAX_EMAILS_FETCH = 200  # 최대 이메일 가져오기 수
MAX_EMAILS_PER_SENDER = 20  # 발신자당 최대 이메일 수
DEFAULT_SENDER_LIMIT = 30  # 기본 발신자 분류 제한
MAX_RESULTS_DISPLAY = 20  # 결과 표시 최대 개수

# Gmail Batch API 설정
GMAIL_BATCH_SIZE = 10  # Gmail API 배치 요청 최대 크기 (Rate limit 방지)
GMAIL_BATCH_DELAY = 0.5  # 배치 간 딜레이 (초)
GMAIL_RETRY_MAX = 3  # 재시도 횟수
GMAIL_RETRY_DELAY = 2  # 재시도 딜레이 (초)

# 분류 결과 캐싱 설정
CLASSIFICATION_CACHE_ENABLED = True  # 분류 캐시 활성화
CLASSIFICATION_CACHE_TTL_HOURS = 24  # 캐시 유효 시간 (시간)
CLASSIFICATION_CACHE_MAX_SIZE = 1000  # 최대 캐시 항목 수

# 토큰 만료 사전 감지 설정
TOKEN_EXPIRY_WARNING_HOURS = 24  # 토큰 만료 경고 시간 (시간)
TOKEN_AUTO_REFRESH_HOURS = 1  # 자동 갱신 시작 시간 (만료 전 n시간)

# 주간 리포트 설정
WEEKLY_REPORT_ENABLED = True  # 주간 스팸 리포트 활성화
WEEKLY_REPORT_INTERVAL_DAYS = 7  # 리포트 발송 간격 (일)

# Slack 알림 설정
SLACK_ENABLED = os.getenv("SLACK_ENABLED", "true").lower() == "true"
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_ID = os.getenv("SLACK_GMAIL_CHANNEL_ID", "")  # 알림 받을 채널
SLACK_NOTIFY_IMPORTANT = False  # 중요 이메일 알림 (비활성화)
SLACK_NOTIFY_SPAM_SUMMARY = False  # 스팸 처리 요약 알림 (비활성화)
# 오류 알림만 활성화됨
SLACK_IMPORTANT_KEYWORDS = ["긴급", "urgent", "결제", "payment", "보안", "security", "비밀번호", "password"]

# 안전 발신자 자동 학습 설정
AUTO_LEARN_SAFE_SENDERS = os.getenv("AUTO_LEARN_SAFE_SENDERS", "true").lower() == "true"
SAFE_SENDERS_FILE = BASE_DIR / "safe_senders.json"
