"""
Cold Email Blocker 모듈
처음 연락하는 발신자의 이메일을 AI로 분석하여 콜드 이메일(영업/마케팅) 여부 판단
"""
import logging
from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass
import json
from pathlib import Path

from google import genai

import config
from gmail_client import GmailClient, Email

logger = logging.getLogger(__name__)


@dataclass
class ColdEmailResult:
    """콜드 이메일 분석 결과"""
    email_id: str
    is_cold_email: bool
    confidence: float
    reason: str
    sender_email: str


class ColdEmailBlocker:
    """콜드 이메일 차단기"""
    
    def __init__(self, gmail_client: GmailClient, api_key: Optional[str] = None):
        self.gmail = gmail_client
        self.api_key = api_key or config.GEMINI_API_KEY
        self.client = genai.Client(api_key=self.api_key)
        self.known_senders_file = Path(__file__).parent / "logs" / "known_senders.json"
        self._known_senders_cache: Optional[Set[str]] = None
        
        logger.info("Cold Email Blocker 초기화 완료")
    
    def _load_known_senders(self) -> Set[str]:
        """이전에 내가 이메일을 보낸 발신자 목록 로드"""
        if self._known_senders_cache is not None:
            return self._known_senders_cache
        
        if self.known_senders_file.exists():
            try:
                with open(self.known_senders_file, 'r') as f:
                    data = json.load(f)
                    self._known_senders_cache = set(data.get("senders", []))
                    return self._known_senders_cache
            except (json.JSONDecodeError, FileNotFoundError, IOError) as e:
                logger.debug(f"알려진 발신자 파일 로드 실패: {e}")
        
        self._known_senders_cache = set()
        return self._known_senders_cache
    
    def _save_known_senders(self, senders: Set[str]):
        """알려진 발신자 목록 저장"""
        self.known_senders_file.parent.mkdir(exist_ok=True)
        with open(self.known_senders_file, 'w') as f:
            json.dump({
                "senders": list(senders),
                "updated_at": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
        self._known_senders_cache = senders
    
    def refresh_known_senders(self) -> int:
        """내가 보낸 이메일의 수신자를 수집하여 알려진 발신자로 등록"""
        try:
            # 최근 보낸 이메일 조회 (최근 90일)
            after_date = (datetime.now() - timedelta(days=90)).strftime("%Y/%m/%d")
            
            result = self.gmail.service.users().messages().list(
                userId='me',
                maxResults=500,
                q=f"in:sent after:{after_date}"
            ).execute()
            
            messages = result.get('messages', [])
            known_senders = self._load_known_senders()
            
            for msg in messages[:200]:  # 최대 200개
                try:
                    detail = self.gmail.service.users().messages().get(
                        userId='me', id=msg['id'], format='metadata',
                        metadataHeaders=['To', 'Cc']
                    ).execute()
                    
                    headers = detail.get('payload', {}).get('headers', [])
                    for header in headers:
                        if header['name'].lower() in ['to', 'cc']:
                            # 이메일 주소 추출
                            value = header['value']
                            for part in value.split(','):
                                if '<' in part and '>' in part:
                                    email = part.split('<')[1].split('>')[0].lower().strip()
                                else:
                                    email = part.strip().lower()
                                if '@' in email:
                                    known_senders.add(email)
                except Exception as e:
                    logger.debug(f"이메일 헤더 파싱 오류: {e}")
                    continue
            
            self._save_known_senders(known_senders)
            logger.info(f"알려진 발신자 {len(known_senders)}명 갱신 완료")
            return len(known_senders)
            
        except Exception as e:
            logger.error(f"알려진 발신자 갱신 오류: {e}")
            return 0
    
    def is_first_contact(self, sender_email: str) -> bool:
        """처음 연락하는 발신자인지 확인"""
        known = self._load_known_senders()
        return sender_email.lower() not in known
    
    def analyze_cold_email(self, email: Email) -> ColdEmailResult:
        """AI로 콜드 이메일 여부 분석"""
        prompt = f"""당신은 이메일 분석 전문가입니다. 아래 이메일이 "콜드 이메일"인지 판단해주세요.

## 콜드 이메일 정의:
- 요청하지 않은 영업/세일즈 이메일
- B2B 서비스/제품 홍보
- 파트너십/협업 제안 (요청하지 않은)
- 채용 제안 (지원하지 않은)
- 투자 제안
- PR/마케팅 대행 제안

## 콜드 이메일이 아닌 경우:
- 내가 가입한 서비스의 알림
- 주문/배송 관련 알림
- 보안/계정 관련 알림
- 결제/영수증
- 개인적인 연락
- 뉴스레터 (구독한 경우)

## 이메일 정보:
- 발신자: {email.sender}
- 발신자 이메일: {email.sender_email}
- 제목: {email.subject}
- 본문: {email.body[:1500] if email.body else "(본문 없음)"}

## 응답 (JSON만):
{{
    "is_cold_email": true/false,
    "confidence": 0.0~1.0,
    "reason": "판단 이유 (한국어)"
}}"""

        try:
            response = self.client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt
            )
            
            response_text = response.text.strip()
            
            # JSON 추출
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            result = json.loads(response_text)
            
            return ColdEmailResult(
                email_id=email.id,
                is_cold_email=result.get('is_cold_email', False),
                confidence=float(result.get('confidence', 0.5)),
                reason=result.get('reason', '분석 결과 없음'),
                sender_email=email.sender_email
            )
            
        except Exception as e:
            logger.error(f"콜드 이메일 분석 오류: {e}")
            return ColdEmailResult(
                email_id=email.id,
                is_cold_email=False,
                confidence=0.0,
                reason=f"분석 오류: {str(e)}",
                sender_email=email.sender_email
            )
    
    def check_new_emails(self, emails: List[Email]) -> List[ColdEmailResult]:
        """새 이메일들에서 콜드 이메일 감지"""
        results = []
        
        for email in emails:
            sender = email.sender_email or ""
            
            # 처음 연락하는 발신자만 분석
            if not self.is_first_contact(sender):
                continue
            
            # 안전한 발신자/도메인 제외
            if sender.lower() in {s.lower() for s in config.SAFE_SENDERS}:
                continue
            
            domain = sender.split('@')[-1].lower() if '@' in sender else ''
            if domain in {d.lower() for d in config.SAFE_DOMAINS}:
                continue
            
            # AI 분석
            result = self.analyze_cold_email(email)
            results.append(result)
            
            if result.is_cold_email and result.confidence >= 0.7:
                logger.info(f"콜드 이메일 감지: {email.subject[:40]}... ({sender})")
        
        return results
    
    def process_cold_emails(
        self, 
        results: List[ColdEmailResult],
        action: str = "label"  # "label", "archive", "spam"
    ) -> int:
        """감지된 콜드 이메일 처리"""
        processed = 0
        label_name = f"{config.LABEL_PREFIX}콜드메일"
        label_id = self.gmail.get_or_create_label(label_name)
        
        if not label_id:
            logger.error("콜드메일 레이블 생성 실패")
            return 0
        
        for result in results:
            if not result.is_cold_email or result.confidence < 0.7:
                continue
            
            try:
                # 레이블 적용
                self.gmail.apply_label(result.email_id, label_id)
                
                if action == "archive":
                    self.gmail.archive_email(result.email_id)
                elif action == "spam":
                    if result.confidence >= 0.9:  # 높은 확신도만
                        self.gmail.mark_as_spam(result.email_id)
                
                processed += 1
            except Exception as e:
                logger.error(f"콜드 이메일 처리 오류: {e}")
        
        return processed


if __name__ == "__main__":
    from rich.console import Console
    console = Console()
    
    console.print("\n[bold]🚫 Cold Email Blocker 테스트[/bold]\n")
    
    client = GmailClient()
    blocker = ColdEmailBlocker(client)
    
    # 알려진 발신자 갱신
    console.print("1. 알려진 발신자 갱신 중...")
    count = blocker.refresh_known_senders()
    console.print(f"   → {count}명의 발신자 등록됨")
    
    # 최근 이메일 확인
    console.print("\n2. 최근 이메일에서 콜드 이메일 검색...")
    emails = client.get_emails(max_results=20, query="in:inbox is:unread")
    results = blocker.check_new_emails(emails)
    
    cold_count = sum(1 for r in results if r.is_cold_email and r.confidence >= 0.7)
    console.print(f"   → {len(results)}개 분석, {cold_count}개 콜드 이메일 감지")
    
    for r in results:
        if r.is_cold_email and r.confidence >= 0.7:
            console.print(f"   🚫 {r.sender_email}: {r.reason[:50]}...")
