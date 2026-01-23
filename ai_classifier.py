"""
Google Gemini AI를 사용한 이메일 분류 모듈
"""
import json
import time
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from google import genai
from rich.console import Console
from rich.table import Table
from tqdm import tqdm

import config
from gmail_client import Email
from exceptions import ClassificationError, RateLimitError

console = Console()
logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """분류 결과 데이터 클래스"""
    email_id: str
    category: str
    confidence: float
    reason: str
    suggested_action: str
    priority: int  # 1-5, 1이 가장 높음


class ClassificationCache:
    """분류 결과 캐시 관리"""

    def __init__(self, cache_dir: Path = None):
        self.cache_dir = cache_dir or config.LOG_DIR
        self.cache_file = self.cache_dir / "classification_cache.json"
        self._cache: Dict[str, Dict] = {}
        self._dirty = False  # Track if cache needs saving
        self._load_cache()

    def _load_cache(self):
        """캐시 파일 로드"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._cache = data.get("cache", {})
                    # 만료된 항목 제거
                    self._cleanup_expired()
            except (json.JSONDecodeError, IOError) as e:
                logger.debug(f"캐시 파일 로드 실패: {e}")
                self._cache = {}

    def _save_cache(self):
        """캐시 파일 저장"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "cache": self._cache,
                    "updated_at": datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.warning(f"캐시 파일 저장 실패: {e}")

    def _cleanup_expired(self):
        """만료된 캐시 항목 제거"""
        ttl_hours = config.CLASSIFICATION_CACHE_TTL_HOURS
        cutoff = datetime.now() - timedelta(hours=ttl_hours)
        cutoff_str = cutoff.isoformat()

        expired_keys = [
            key for key, value in self._cache.items()
            if value.get("cached_at", "") < cutoff_str
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"만료된 캐시 {len(expired_keys)}개 제거")

    def _generate_key(self, email: Email) -> str:
        """이메일에 대한 캐시 키 생성"""
        # email_id를 기본 키로 사용
        return email.id

    def get(self, email: Email) -> Optional[ClassificationResult]:
        """캐시에서 분류 결과 조회"""
        if not config.CLASSIFICATION_CACHE_ENABLED:
            return None

        key = self._generate_key(email)
        cached = self._cache.get(key)

        if not cached:
            return None

        # TTL 확인
        cached_at = cached.get("cached_at", "")
        ttl_hours = config.CLASSIFICATION_CACHE_TTL_HOURS
        cutoff = datetime.now() - timedelta(hours=ttl_hours)

        if cached_at < cutoff.isoformat():
            del self._cache[key]
            return None

        logger.debug(f"캐시 히트: {email.subject[:config.SUBJECT_PREVIEW_LENGTH]}...")

        return ClassificationResult(
            email_id=cached["email_id"],
            category=cached["category"],
            confidence=cached["confidence"],
            reason=cached["reason"],
            suggested_action=cached["suggested_action"],
            priority=cached["priority"]
        )

    def set(self, email: Email, result: ClassificationResult):
        """분류 결과를 캐시에 저장 (메모리에만 저장, 디스크는 flush() 호출 시)"""
        if not config.CLASSIFICATION_CACHE_ENABLED:
            return

        key = self._generate_key(email)

        # 캐시 크기 제한
        if len(self._cache) >= config.CLASSIFICATION_CACHE_MAX_SIZE:
            # 가장 오래된 항목 제거
            oldest_key = min(
                self._cache.keys(),
                key=lambda k: self._cache[k].get("cached_at", "")
            )
            del self._cache[oldest_key]

        self._cache[key] = {
            "email_id": result.email_id,
            "category": result.category,
            "confidence": result.confidence,
            "reason": result.reason,
            "suggested_action": result.suggested_action,
            "priority": result.priority,
            "cached_at": datetime.now().isoformat()
        }

        self._dirty = True  # Mark as dirty, don't save immediately

    def flush(self):
        """캐시를 디스크에 저장 (dirty flag가 설정된 경우만)"""
        if self._dirty:
            self._save_cache()
            self._dirty = False

    def clear(self):
        """캐시 전체 삭제"""
        self._cache = {}
        self._save_cache()
        logger.info("분류 캐시 전체 삭제됨")

    def stats(self) -> Dict[str, int]:
        """캐시 통계"""
        return {
            "total_entries": len(self._cache),
            "max_size": config.CLASSIFICATION_CACHE_MAX_SIZE
        }


class EmailClassifier:
    """Gemini AI 기반 이메일 분류기"""

    def __init__(self, api_key: Optional[str] = None, use_cache: bool = True):
        self.api_key = api_key or config.GEMINI_API_KEY

        if not self.api_key:
            raise ValueError(
                "Gemini API 키가 필요합니다. "
                ".env 파일에 GEMINI_API_KEY를 설정하거나 직접 전달하세요."
            )

        self.client = genai.Client(api_key=self.api_key)
        self.current_model = config.GEMINI_MODEL
        self.cache = ClassificationCache() if use_cache else None
        self._cache_hits = 0
        self._cache_misses = 0

        console.print(f"[green]✓[/green] Gemini AI 클라이언트 로드됨: {self.current_model}")
        if self.cache:
            stats = self.cache.stats()
            console.print(f"[cyan]📦[/cyan] 분류 캐시 활성화 ({stats['total_entries']}/{stats['max_size']})")

    def _call_api_with_retry(self, prompt: str) -> Optional[str]:
        """
        API 호출 + 재시도 + 모델 폴백 로직

        Args:
            prompt: 프롬프트 텍스트

        Returns:
            str: API 응답 텍스트 또는 None
        """
        last_error = None

        for model in config.GEMINI_MODELS:
            for attempt in range(config.MAX_API_RETRIES):
                try:
                    response = self.client.models.generate_content(
                        model=model,
                        contents=prompt
                    )
                    # 성공 시 현재 모델 업데이트
                    if model != self.current_model:
                        logger.info(f"모델 변경: {self.current_model} → {model}")
                        self.current_model = model
                    return response.text.strip()

                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()

                    # Rate limit 에러 확인
                    if "429" in str(e) or "quota" in error_str or "rate" in error_str:
                        wait_time = config.API_RETRY_DELAY_BASE * (2 ** attempt)
                        logger.warning(f"Rate limit - {wait_time}초 대기 후 재시도 ({attempt + 1}/{config.MAX_API_RETRIES})")
                        time.sleep(wait_time)
                        if attempt == config.MAX_API_RETRIES - 1:
                            raise RateLimitError(f"API rate limit exceeded after {config.MAX_API_RETRIES} retries") from e
                        continue

                    # 모델 없음 에러 - 다음 모델로 폴백
                    if "not found" in error_str or "404" in str(e):
                        logger.warning(f"모델 {model} 사용 불가 - 폴백 시도")
                        break  # 다음 모델로

                    # 서버 에러 - 재시도
                    if "500" in str(e) or "503" in str(e):
                        wait_time = config.API_RETRY_DELAY_BASE * (2 ** attempt)
                        logger.warning(f"서버 에러 - {wait_time}초 대기 후 재시도")
                        time.sleep(wait_time)
                        continue

                    # 기타 에러 - 재시도
                    logger.warning(f"API 호출 오류 ({attempt + 1}/{config.MAX_API_RETRIES}): {e}")
                    if attempt < config.MAX_API_RETRIES - 1:
                        time.sleep(config.API_RETRY_DELAY_BASE)

        logger.error(f"모든 모델/재시도 실패: {last_error}")
        return None
    
    def _build_classification_prompt(self, email: Email) -> str:
        """분류를 위한 프롬프트를 생성합니다."""

        prompt = f"""당신은 이메일 분류 전문가입니다. **본문 내용을 실제로 읽고** 분류해주세요.

## 핵심 원칙: 발신자가 아닌 "내용"으로 판단!
- 신뢰 도메인(Google, LinkedIn, 쿠팡 등)이라도 **광고/마케팅이면 INFO**
- 알 수 없는 도메인이라도 **중요한 내용이면 IMPORTANT**

## 분류 카테고리 (4개):

### IMPORTANT (받은편지함 유지, 즉시 확인 필요)
**나에게 직접 해당되는 개인화된 알림:**
- 결제 완료/실패, 정산 내역, 청구서
- 비밀번호 재설정, 인증코드, 보안 알림
- 내 계정 상태 변경, 서비스 장애 통보
- 배송 출발/완료, 주문 확인
- 내가 올린 글에 대한 댓글/답변
- 도메인/인증서 만료 임박
- API 한도 초과, 사용량 경고

### NORMAL (받은편지함 유지)
**일반적인 알림 (개인화되었지만 급하지 않음):**
- GitHub PR/Issue 알림
- Slack 메시지 알림
- 월간 리포트, 통계 요약
- 서비스 공지사항

### INFO (보관 처리 → 받은편지함에서 제거)
**대량 발송 마케팅/뉴스레터:**
- "~% 할인", "지금 바로", "놓치지 마세요" 등 프로모션
- 뉴스레터, 업계 소식, 트렌드 리포트
- 제품 업데이트 소식 (내가 요청하지 않은)
- LinkedIn 팔로우 추천, 게임 알림
- "수신거부" 링크가 있는 마케팅 이메일

### SPAM (스팸함으로 이동)
**악성/사기성 메일만:**
- 피싱, 사기, 복권 당첨
- 요청하지 않은 콜드 영업 메일
- 출처 불명 광고

## 판단 가이드:
| 본문 특징 | 분류 |
|----------|------|
| "주문번호 #12345 배송 출발" | IMPORTANT |
| "🎉 신규 회원 30% 할인!" | INFO |
| "김*수님의 1월 정산 내역" | IMPORTANT |
| "2026 트렌드 리포트 확인하세요" | INFO |
| "u/xxx replied to your post" | IMPORTANT |
| "Bill Gates님을 팔로우해보세요" | INFO |
| "Steam 찜 목록 할인 중" | INFO |
| "결제가 완료되었습니다" | IMPORTANT |

## 이메일 정보:
- 제목: {email.subject}
- 발신자: {email.sender}
- 발신자 이메일: {email.sender_email}
- 본문: {email.body[:config.PROMPT_BODY_LENGTH] if email.body else "(본문 없음)"}

## 응답 (JSON만):
{{
    "category": "IMPORTANT/NORMAL/INFO/SPAM",
    "confidence": 0.0~1.0,
    "reason": "분류 이유 (한국어, 본문 내용 기반으로 설명)",
    "priority": 1~5,
    "suggested_action": "keep/archive/spam"
}}"""

        return prompt
    
    def classify_email(self, email: Email) -> Optional[ClassificationResult]:
        """단일 이메일을 분류합니다."""
        # 캐시 확인
        if self.cache:
            cached_result = self.cache.get(email)
            if cached_result:
                self._cache_hits += 1
                return cached_result
            self._cache_misses += 1

        try:
            prompt = self._build_classification_prompt(email)

            # 재시도 + 폴백 로직 사용
            response_text = self._call_api_with_retry(prompt)

            if not response_text:
                logger.error(f"API 응답 없음: {email.subject[:config.SUBJECT_PREVIEW_LENGTH]}...")
                return None

            # JSON 블록 추출
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            result = json.loads(response_text)

            # 카테고리 유효성 검사
            valid_categories = ['IMPORTANT', 'NORMAL', 'INFO', 'SPAM']
            category = result.get('category', 'NORMAL').upper()
            if category not in valid_categories:
                category = 'NORMAL'

            classification = ClassificationResult(
                email_id=email.id,
                category=category,
                confidence=float(result.get('confidence', config.DEFAULT_CONFIDENCE)),
                reason=result.get('reason', '분류 이유 없음'),
                suggested_action=result.get('suggested_action', 'keep'),
                priority=int(result.get('priority', config.DEFAULT_PRIORITY))
            )

            # 캐시에 저장
            if self.cache:
                self.cache.set(email, classification)

            return classification

        except json.JSONDecodeError as e:
            console.print(f"[yellow]⚠ JSON 파싱 오류 ({email.subject[:config.SUBJECT_PREVIEW_LENGTH]}...): {e}[/yellow]")
            raise ClassificationError(f"Failed to parse AI response: {e}") from e
        except Exception as e:
            console.print(f"[red]✗ 분류 오류 ({email.subject[:config.SUBJECT_PREVIEW_LENGTH]}...): {e}[/red]")
            raise ClassificationError(f"Classification failed: {e}") from e
    
    def classify_emails(
        self,
        emails: List[Email],
        show_progress: bool = True
    ) -> List[Tuple[Email, ClassificationResult]]:
        """여러 이메일을 분류합니다."""
        results = []

        iterator = tqdm(emails, desc="이메일 분류 중") if show_progress else emails

        for email in iterator:
            result = self.classify_email(email)
            if result:
                results.append((email, result))

        # Flush cache at the end to batch all saves
        if self.cache:
            self.cache.flush()

        return results
    
    def _build_batch_prompt(self, emails: List[Email]) -> str:
        """배치 분류를 위한 프롬프트를 생성합니다."""

        emails_info = []
        for i, email in enumerate(emails):
            body_preview = email.body[:config.BATCH_BODY_PREVIEW] if email.body else ""
            emails_info.append(f"""
### 이메일 #{i+1} (ID: {email.id})
- 제목: {email.subject}
- 발신자: {email.sender_email}
- 본문: {body_preview}
""")

        prompt = f"""이메일 분류 전문가. **본문 내용**을 실제로 읽고 분류하세요.

## 핵심: 발신자가 아닌 "내용"으로 판단!

## 카테고리:
- IMPORTANT: 결제/정산, 보안 인증, 비밀번호, 배송 알림, 내 글에 대한 댓글/답변, 만료 임박 (나에게 직접 해당)
- NORMAL: GitHub/Slack 알림, 월간 리포트, 서비스 공지
- INFO: 할인/프로모션, 뉴스레터, 마케팅, 팔로우 추천, 게임 알림 (대량 발송, 보관처리)
- SPAM: 피싱, 사기, 콜드 영업, 출처 불명 광고만 (악성 메일만!)

## 판단 기준:
- "결제 완료", "정산 내역", "주문 확인" → IMPORTANT
- "인증코드", "비밀번호 재설정" → IMPORTANT
- "replied to your post" → IMPORTANT
- "~% 할인", "프로모션", "놓치지 마세요" → INFO
- "팔로우해보세요", "찜 목록 할인" → INFO
- 피싱/사기/복권 당첨 → SPAM

## 이메일:
{"".join(emails_info)}

## 응답 (JSON 배열만):
[{{"email_id":"ID","category":"카테고리","confidence":0.9,"reason":"이유","priority":3,"suggested_action":"액션"}}]"""

        return prompt
    
    def classify_batch(
        self,
        emails: List[Email],
        batch_size: int = config.AI_BATCH_SIZE
    ) -> List[Tuple[Email, ClassificationResult]]:
        """배치로 이메일을 분류합니다."""
        all_results = []
        email_dict = {e.id: e for e in emails}

        for i in tqdm(range(0, len(emails), batch_size), desc="배치 분류"):
            batch = emails[i:i + batch_size]

            try:
                prompt = self._build_batch_prompt(batch)

                # 재시도 + 폴백 로직 사용
                response_text = self._call_api_with_retry(prompt)

                if not response_text:
                    raise Exception("API 응답 없음")

                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()

                results = json.loads(response_text)

                for result in results:
                    email_id = result.get('email_id')
                    if email_id in email_dict:
                        # 카테고리 유효성 검사
                        valid_categories = ['IMPORTANT', 'NORMAL', 'INFO', 'SPAM']
                        category = result.get('category', 'NORMAL').upper()
                        if category not in valid_categories:
                            category = 'NORMAL'

                        classification = ClassificationResult(
                            email_id=email_id,
                            category=category,
                            confidence=float(result.get('confidence', config.DEFAULT_CONFIDENCE)),
                            reason=result.get('reason', ''),
                            suggested_action=result.get('suggested_action', 'keep'),
                            priority=int(result.get('priority', config.DEFAULT_PRIORITY))
                        )
                        all_results.append((email_dict[email_id], classification))

            except Exception as e:
                console.print(f"[yellow]⚠ 배치 처리 오류: {e}[/yellow]")
                # 개별 분류로 폴백
                for email in batch:
                    result = self.classify_email(email)
                    if result:
                        all_results.append((email, result))

        # Flush cache at the end to batch all saves
        if self.cache:
            self.cache.flush()

        return all_results
    
    def summarize_classifications(
        self, 
        results: List[Tuple[Email, ClassificationResult]]
    ) -> Dict[str, List[Tuple[Email, ClassificationResult]]]:
        """분류 결과를 카테고리별로 요약합니다."""
        summary = {cat: [] for cat in config.EMAIL_CATEGORIES.keys()}
        
        for email, result in results:
            if result.category in summary:
                summary[result.category].append((email, result))
            else:
                summary['NORMAL'].append((email, result))
        
        return summary
    
    def print_summary(
        self, 
        results: List[Tuple[Email, ClassificationResult]]
    ):
        """분류 결과 요약을 출력합니다."""
        summary = self.summarize_classifications(results)
        
        console.print("\n[bold]📊 이메일 분류 결과 요약[/bold]\n")
        
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("카테고리", style="dim")
        table.add_column("개수", justify="right")
        table.add_column("권장 액션")
        
        for category, items in summary.items():
            if items:
                cat_info = config.EMAIL_CATEGORIES.get(category, {})
                table.add_row(
                    cat_info.get('name', category),
                    str(len(items)),
                    cat_info.get('action', 'keep')
                )
        
        console.print(table)
        console.print()
    
    def print_detailed_results(
        self,
        results: List[Tuple[Email, ClassificationResult]],
        max_display: int = config.MAX_RESULTS_DISPLAY
    ):
        """상세 분류 결과를 출력합니다."""
        console.print("\n[bold]📋 상세 분류 결과[/bold]\n")

        sorted_results = sorted(results, key=lambda x: (x[1].priority, -x[1].confidence))

        for i, (email, result) in enumerate(sorted_results[:max_display]):
            cat_info = config.EMAIL_CATEGORIES.get(result.category, {})

            console.print(f"[bold]{i+1}.[/bold] {email.subject[:config.SUBJECT_DISPLAY_LENGTH]}...")
            console.print(f"   발신자: {email.sender_email}")
            console.print(f"   분류: {cat_info.get('name', result.category)} "
                         f"(확신도: {result.confidence:.0%})")
            console.print(f"   이유: {result.reason}")
            console.print(f"   권장: {result.suggested_action}")
            console.print()
        
        if len(results) > max_display:
            console.print(f"[dim]... 외 {len(results) - max_display}개[/dim]")

    def get_cache_stats(self) -> Dict[str, int]:
        """캐시 통계 반환"""
        stats = {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": 0.0
        }

        total = self._cache_hits + self._cache_misses
        if total > 0:
            stats["hit_rate"] = self._cache_hits / total

        if self.cache:
            cache_stats = self.cache.stats()
            stats.update(cache_stats)

        return stats

    def print_cache_stats(self):
        """캐시 통계 출력"""
        stats = self.get_cache_stats()
        console.print("\n[bold]📦 분류 캐시 통계[/bold]")
        console.print(f"   캐시 히트: {stats['cache_hits']}")
        console.print(f"   캐시 미스: {stats['cache_misses']}")
        console.print(f"   히트율: {stats['hit_rate']:.1%}")
        if self.cache:
            console.print(f"   캐시 항목: {stats['total_entries']}/{stats['max_size']}")


if __name__ == "__main__":
    try:
        classifier = EmailClassifier()
        console.print("[green]✓ 분류기 초기화 성공[/green]")
    except Exception as e:
        console.print(f"[red]✗ 분류기 초기화 실패: {e}[/red]")
