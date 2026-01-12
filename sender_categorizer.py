"""
Sender Categorizer 모듈
발신자를 카테고리별로 자동 분류하여 레이블 적용
"""
import logging
import json
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

from google import genai

import config
from gmail_client import GmailClient, Email

logger = logging.getLogger(__name__)


# 발신자 카테고리 정의
SENDER_CATEGORIES = {
    "업무": {
        "description": "직장 관련, 업무 협업, B2B 소통",
        "color": "#4285f4",  # 파랑
        "keywords": ["invoice", "contract", "meeting", "slack", "notion", "jira"]
    },
    "금융": {
        "description": "은행, 카드, 결제, 투자, 보험",
        "color": "#34a853",  # 초록
        "keywords": ["bank", "card", "payment", "결제", "영수증", "신용카드"]
    },
    "쇼핑": {
        "description": "주문, 배송, 반품, 이커머스",
        "color": "#fbbc04",  # 노랑
        "keywords": ["order", "shipping", "delivery", "배송", "주문", "coupang", "naver"]
    },
    "서비스": {
        "description": "가입한 서비스 알림, SaaS, 클라우드",
        "color": "#ea4335",  # 빨강
        "keywords": ["notification", "alert", "account", "verify", "google", "github"]
    },
    "마케팅": {
        "description": "프로모션, 할인, 광고, 뉴스레터",
        "color": "#9e9e9e",  # 회색
        "keywords": ["sale", "discount", "promotion", "newsletter", "unsubscribe"]
    },
    "소셜": {
        "description": "SNS, 개인 연락, 커뮤니티",
        "color": "#673ab7",  # 보라
        "keywords": ["instagram", "facebook", "twitter", "linkedin", "comment", "follow"]
    }
}


@dataclass
class SenderProfile:
    """발신자 프로필"""
    email: str
    name: Optional[str]
    category: Optional[str]
    confidence: float
    email_count: int
    last_email_date: Optional[str]


class SenderCategorizer:
    """발신자 자동 분류기"""
    
    def __init__(self, gmail_client: GmailClient, api_key: Optional[str] = None):
        self.gmail = gmail_client
        self.api_key = api_key or config.GEMINI_API_KEY
        self.client = genai.Client(api_key=self.api_key)
        self.cache_file = Path(__file__).parent / "logs" / "sender_categories.json"
        self._category_cache: Dict[str, str] = {}
        self._load_cache()
        
        logger.info("Sender Categorizer 초기화 완료")
    
    def _load_cache(self):
        """캐시 로드"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    self._category_cache = data.get("categories", {})
            except (json.JSONDecodeError, FileNotFoundError, IOError) as e:
                logger.debug(f"발신자 캐시 로드 실패: {e}")
    
    def _save_cache(self):
        """캐시 저장"""
        self.cache_file.parent.mkdir(exist_ok=True)
        with open(self.cache_file, 'w') as f:
            json.dump({
                "categories": self._category_cache,
                "updated_at": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    
    def get_cached_category(self, sender_email: str) -> Optional[str]:
        """캐시에서 카테고리 조회"""
        return self._category_cache.get(sender_email.lower())
    
    def analyze_sender_category(
        self, 
        sender_email: str,
        sender_name: str,
        recent_subjects: List[str]
    ) -> tuple[str, float]:
        """AI로 발신자 카테고리 분석"""
        
        # 캐시 확인
        cached = self.get_cached_category(sender_email)
        if cached:
            return cached, 1.0
        
        categories_desc = "\n".join([
            f"- {name}: {info['description']}"
            for name, info in SENDER_CATEGORIES.items()
        ])
        
        subjects_text = "\n".join([f"- {s[:config.SUBJECT_TRUNCATE_LENGTH]}" for s in recent_subjects[:config.MAX_SUBJECTS_FOR_ANALYSIS]])
        
        prompt = f"""발신자를 아래 카테고리 중 하나로 분류해주세요.

## 카테고리:
{categories_desc}

## 발신자 정보:
- 이메일: {sender_email}
- 이름: {sender_name}
- 최근 이메일 제목:
{subjects_text}

## 응답 (JSON만):
{{
    "category": "카테고리명",
    "confidence": 0.0~1.0,
    "reason": "분류 이유"
}}"""

        try:
            response = self.client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt
            )
            
            text = response.text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            result = json.loads(text)
            category = result.get("category", "기타")
            confidence = float(result.get("confidence", config.DEFAULT_CONFIDENCE))
            
            # 유효한 카테고리인지 확인
            if category not in SENDER_CATEGORIES:
                category = "서비스"  # 기본값
            
            # 캐시에 저장
            if confidence >= config.CATEGORY_CACHE_THRESHOLD:
                self._category_cache[sender_email.lower()] = category
                self._save_cache()
            
            return category, confidence
            
        except Exception as e:
            logger.error(f"발신자 분류 오류: {e}")
            return "서비스", config.DEFAULT_CONFIDENCE
    
    def categorize_recent_senders(self, limit: int = config.DEFAULT_SENDER_LIMIT) -> List[SenderProfile]:
        """최근 발신자들을 분류"""
        after_date = (datetime.now() - timedelta(days=config.RECENT_DAYS)).strftime("%Y/%m/%d")

        try:
            emails = self.gmail.get_emails(
                max_results=config.MAX_EMAILS_FETCH,
                query=f"after:{after_date}",
                include_spam_trash=False
            )
            
            # 발신자별 이메일 그룹화
            sender_emails: Dict[str, List[Email]] = defaultdict(list)
            for email in emails:
                sender = email.sender_email or ""
                if sender:
                    sender_emails[sender.lower()].append(email)
            
            # 상위 발신자만 분류
            sorted_senders = sorted(
                sender_emails.items(), 
                key=lambda x: len(x[1]), 
                reverse=True
            )[:limit]
            
            profiles = []
            for sender, emails_list in sorted_senders:
                # 최근 제목 추출
                subjects = [e.subject for e in emails_list if e.subject][:config.MAX_SUBJECTS_FOR_ANALYSIS]
                name = emails_list[0].sender if emails_list else ""
                
                # 카테고리 분류
                category, confidence = self.analyze_sender_category(
                    sender, name, subjects
                )
                
                profiles.append(SenderProfile(
                    email=sender,
                    name=name,
                    category=category,
                    confidence=confidence,
                    email_count=len(emails_list),
                    last_email_date=emails_list[0].date if emails_list else None
                ))
                
                logger.info(f"발신자 분류: {sender[:config.SUBJECT_PREVIEW_LENGTH]}... → {category} ({confidence:.0%})")
            
            return profiles
            
        except Exception as e:
            logger.error(f"발신자 분류 오류: {e}")
            return []
    
    def apply_sender_labels(self, profiles: List[SenderProfile]) -> int:
        """분류된 발신자에 레이블 적용"""
        applied = 0
        
        for profile in profiles:
            if profile.confidence < config.CATEGORY_CACHE_THRESHOLD:
                continue
            
            category = profile.category
            if not category or category not in SENDER_CATEGORIES:
                continue
            
            label_name = f"{config.LABEL_PREFIX}발신자/{category}"
            label_id = self.gmail.get_or_create_label(label_name)
            
            if not label_id:
                continue
            
            # 해당 발신자의 이메일에 레이블 적용
            try:
                # 최근 이메일만 레이블 적용
                after_date = (datetime.now() - timedelta(days=config.RECENT_DAYS)).strftime("%Y/%m/%d")
                emails = self.gmail.get_emails(
                    max_results=config.MAX_EMAILS_PER_SENDER,
                    query=f"from:{profile.email} after:{after_date}",
                    include_spam_trash=False
                )
                
                for email in emails:
                    self.gmail.apply_label(email.id, label_id)
                    applied += 1
                    
            except Exception as e:
                logger.error(f"레이블 적용 오류 ({profile.email}): {e}")
        
        return applied


if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table
    console = Console()
    
    console.print("\n[bold]📊 Sender Categorizer 테스트[/bold]\n")
    
    client = GmailClient()
    categorizer = SenderCategorizer(client)
    
    console.print("발신자 분류 중... (최대 10명)")
    profiles = categorizer.categorize_recent_senders(limit=10)
    
    table = Table(title="발신자 분류 결과")
    table.add_column("발신자", style="cyan")
    table.add_column("카테고리", style="magenta")
    table.add_column("신뢰도", justify="right")
    table.add_column("이메일 수", justify="right")
    
    for p in profiles:
        table.add_row(
            p.email[:config.EMAIL_DISPLAY_LENGTH] + "..." if len(p.email) > config.EMAIL_DISPLAY_LENGTH else p.email,
            p.category,
            f"{p.confidence:.0%}",
            str(p.email_count)
        )
    
    console.print(table)
