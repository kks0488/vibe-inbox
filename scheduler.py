#!/usr/bin/env python3
"""
Gmail Organizer 스케줄러 - 상시 실행 데몬
AI가 먼저 읽고, 확실한 스팸/광고만 처리. 애매한 건 사용자가 확인하도록 유지.
"""
import time
import signal
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from rich.console import Console

import config
from auth import get_gmail_credentials, check_auth_status, check_and_refresh_token
from gmail_client import GmailClient
from ai_classifier import EmailClassifier
from email_reporter import WeeklyReporter
from cold_email_blocker import ColdEmailBlocker
from classification_stats import get_stats, ClassificationRecord
from slack_notifier import get_notifier, EmailNotification
from safe_sender_learner import SafeSenderLearner
from utils import is_safe_sender

# 통합 로깅 설정
logger = config.setup_logging(name="scheduler", log_file="scheduler.log", use_rich=True)
console = Console()


class GmailScheduler:
    """Gmail 정리 스케줄러"""
    
    def __init__(
        self,
        interval_minutes: int = 30,
        batch_size: int = 50,
        auto_organize: bool = True
    ):
        self.interval_minutes = interval_minutes
        self.batch_size = batch_size
        self.auto_organize = auto_organize
        self.running = False
        self.gmail_client: Optional[GmailClient] = None
        self.classifier: Optional[EmailClassifier] = None
        self.weekly_reporter: Optional[WeeklyReporter] = None
        self.cold_email_blocker: Optional[ColdEmailBlocker] = None
        self.slack_notifier = None
        self.safe_sender_learner: Optional[SafeSenderLearner] = None
        self._last_learn_time: Optional[datetime] = None

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        logger.info(f"종료 시그널 수신 ({signum})")
        self.stop()
    
    def _initialize(self) -> bool:
        try:
            logger.info("Gmail 클라이언트 초기화 중...")
            self.gmail_client = GmailClient()
            
            logger.info("AI 분류기 초기화 중...")
            self.classifier = EmailClassifier()
            
            # 주간 리포터 초기화
            if config.WEEKLY_REPORT_ENABLED:
                logger.info("주간 리포터 초기화 중...")
                self.weekly_reporter = WeeklyReporter(self.gmail_client)
            
            # 콜드 이메일 차단기 초기화
            logger.info("콜드 이메일 차단기 초기화 중...")
            self.cold_email_blocker = ColdEmailBlocker(self.gmail_client)
            # 시작 시 알려진 발신자 갱신 (백그라운드에서 빠르게)
            self.cold_email_blocker.refresh_known_senders()

            # Slack 알림 초기화
            logger.info("Slack 알림 초기화 중...")
            self.slack_notifier = get_notifier()
            if self.slack_notifier.enabled:
                logger.info("Slack 알림 활성화됨")
            else:
                logger.info("Slack 알림 비활성화 (토큰 또는 채널 미설정)")

            # 안전 발신자 자동 학습 초기화
            if config.AUTO_LEARN_SAFE_SENDERS:
                logger.info("안전 발신자 자동 학습 초기화 중...")
                self.safe_sender_learner = SafeSenderLearner(self.gmail_client)
                stats = self.safe_sender_learner.get_stats()
                logger.info(f"안전 발신자: {stats['senders']}명, 도메인: {stats['domains']}개")

            profile = self.gmail_client.get_profile()
            logger.info(f"Gmail 연결됨: {profile.get('emailAddress', 'N/A')}")

            return True
        except Exception as e:
            logger.error(f"초기화 실패: {e}")
            return False
    
    def _filter_unprocessed_emails(self, emails) -> List:
        """
        모든 메일을 다시 분류/재배치하도록 건너뛰지 않습니다.
        이미 AI 레이블이 있어도 재적용/재처리합니다.
        """
        return emails
    
    def _check_token_status(self):
        """토큰 상태를 확인하고 필요 시 갱신"""
        success, message = check_and_refresh_token()
        if success:
            if "경고" in message or "warning" in message.lower():
                logger.warning(f"토큰 상태: {message}")
            else:
                logger.debug(f"토큰 상태: {message}")
        else:
            logger.error(f"토큰 오류: {message}")
            console.print(f"[red]⚠ 토큰 오류: {message}[/red]")

    def _process_emails(self):
        """이메일 처리 실행"""
        # 처리 전 토큰 상태 확인
        self._check_token_status()

        try:
            total_processed = 0
            cold_emails_found = 0
            
            # 받은편지함 처리 (읽지 않은 것 우선)
            logger.info("=== 받은편지함 처리 ===")
            emails = self.gmail_client.get_emails(
                max_results=self.batch_size,
                query="in:inbox",
                include_spam_trash=False
            )
            
            if emails:
                emails = self._filter_unprocessed_emails(emails)
                if emails:
                    processed = self._classify_and_organize(emails)
                    total_processed += processed
                    
                    # 콜드 이메일 체크 (처음 연락하는 발신자만)
                    if self.cold_email_blocker:
                        cold_results = self.cold_email_blocker.check_new_emails(emails)
                        cold_count = self.cold_email_blocker.process_cold_emails(cold_results, action="label")
                        cold_emails_found = cold_count
                        if cold_count > 0:
                            logger.info(f"🚫 콜드 이메일 {cold_count}개 감지 및 레이블 적용")
            
            logger.info(f"총 {total_processed}개 이메일 처리 완료 (콜드: {cold_emails_found}개)")
            
        except Exception as e:
            logger.error(f"이메일 처리 중 오류: {e}", exc_info=True)
    
    def _classify_and_organize(self, emails) -> int:
        """
        AI 분류 후 처리:
        - config.EMAIL_CATEGORIES의 action에 따라 동작 (기본: keep)
        - 신뢰 발신자(SAFE_SENDERS/SAFE_DOMAINS)는 항상 레이블만 적용
        - 스팸 이동은 config.SPAM_CONFIDENCE_THRESHOLD 이상일 때만
        """
        if not emails:
            return 0
        
        logger.info(f"{len(emails)}개 이메일 분류 중...")
        
        # AI 분류
        results = self.classifier.classify_batch(emails, batch_size=5)
        
        if not results:
            logger.warning("분류 결과 없음")
            return 0
        
        # 분류 통계
        summary = self.classifier.summarize_classifications(results)
        stats = {cat: len(items) for cat, items in summary.items() if items}
        logger.info(f"분류 결과: {stats}")
        
        # 처리 카운터
        kept_unread = 0  # 읽지 않음 유지 (사용자 확인 필요)
        archived = 0
        spammed = 0
        
        if not self.auto_organize:
            logger.info("자동 정리 비활성화 - 분석만 완료")
            kept_unread = len(results)
            logger.info(f"  📬 레이블만 적용/유지: {kept_unread}개")
            return len(results)
        
        for category, items in summary.items():
            if not items:
                continue
            
            cat_info = config.EMAIL_CATEGORIES.get(category, {})
            label_name = f"{config.LABEL_PREFIX}{cat_info.get('name', category)}"
            
            label_id = self.gmail_client.get_or_create_label(label_name)
            if not label_id:
                continue
            
            for email, result in items:
                try:
                    # 모든 메일에 레이블 적용
                    self.gmail_client.apply_label(email.id, label_id)
                    
                    # 신뢰 발신자는 항상 레이블만
                    action = 'keep' if is_safe_sender(email) else cat_info.get('action', 'keep')
                    
                    if action == 'archive':
                        self.gmail_client.archive_email(email.id)
                        archived += 1
                    elif action == 'spam' and result.confidence >= config.SPAM_CONFIDENCE_THRESHOLD:
                        self.gmail_client.mark_as_spam(email.id)
                        spammed += 1
                    else:
                        kept_unread += 1
                    
                    # 통계 기록
                    stats_tracker = get_stats()
                    stats_tracker.record(ClassificationRecord(
                        timestamp=datetime.now().isoformat(),
                        email_id=email.id,
                        subject=email.subject[:100] if email.subject else "",
                        sender_email=email.sender_email or "",
                        category=result.category,
                        confidence=result.confidence,
                        reason=result.reason[:200] if result.reason else "",
                        action_taken=action
                    ))
                            
                except Exception as e:
                    logger.error(f"이메일 처리 오류 ({email.id}): {e}")
        
        # 통계 요약 로그
        stats_summary = get_stats().get_summary()
        logger.info(f"처리 완료:")
        logger.info(f"  📬 읽지않음 유지: {kept_unread}개")
        logger.info(f"  📦 보관: {archived}개, 🚫 스팸: {spammed}개")
        logger.info(f"  📊 {stats_summary}")

        # Slack 처리 요약 알림
        if self.slack_notifier and (archived > 0 or spammed > 0):
            self.slack_notifier.notify_processing_summary(
                total=len(results),
                categories=stats,
                archived=archived,
                spam=spammed
            )

        return len(results)
    
    def _check_weekly_report(self):
        """주간 리포트 발송 체크"""
        if not self.weekly_reporter or not config.WEEKLY_REPORT_ENABLED:
            return

        try:
            if self.weekly_reporter.should_send_report():
                logger.info("=== 주간 스팸 리포트 발송 ===")
                if self.weekly_reporter.send_weekly_report():
                    logger.info("주간 리포트 발송 성공")
                else:
                    logger.warning("주간 리포트 발송 실패")
        except Exception as e:
            logger.error(f"주간 리포트 체크 오류: {e}", exc_info=True)

    def _learn_safe_senders(self):
        """안전 발신자 자동 학습 (하루에 한 번)"""
        if not self.safe_sender_learner:
            return

        now = datetime.now()

        # 마지막 학습 후 24시간이 지났는지 확인
        if self._last_learn_time:
            hours_since_last = (now - self._last_learn_time).total_seconds() / 3600
            if hours_since_last < 24:
                return

        try:
            logger.info("=== 안전 발신자 자동 학습 ===")

            # 보낸 편지함에서 학습
            sent_count = self.safe_sender_learner.learn_from_sent_emails(days=7)

            # 답장한 스레드에서 학습
            reply_count = self.safe_sender_learner.learn_from_replied_threads()

            total = sent_count + reply_count
            if total > 0:
                logger.info(f"안전 발신자 학습 완료: {total}명 추가 (보낸메일: {sent_count}, 답장: {reply_count})")
            else:
                logger.info("새로 학습할 안전 발신자 없음")

            self._last_learn_time = now

        except Exception as e:
            logger.error(f"안전 발신자 학습 오류: {e}")
    
    def start(self):
        console.print("\n[bold cyan]🚀 Gmail Organizer 스케줄러 시작[/bold cyan]\n")
        logger.info(f"스케줄러 시작 - 간격: {self.interval_minutes}분")
        
        if not self._initialize():
            logger.error("초기화 실패")
            sys.exit(1)
        
        self.running = True
        
        console.print("[green]✓[/green] 스케줄러 시작됨")
        console.print(f"   실행 간격: {self.interval_minutes}분")
        if config.WEEKLY_REPORT_ENABLED:
            console.print(f"   📧 주간 리포트: 활성화 ({config.WEEKLY_REPORT_INTERVAL_DAYS}일마다)")
        console.print()
        console.print("[bold]처리 방식:[/bold]")
        console.print("  📌 중요/일반 → 레이블만 적용 (읽지않음 유지)")
        console.print("  📰 정보 → 기본은 레이블만 (action='keep')")
        console.print(f"  🚫 스팸 → 기본은 레이블만, 확신도>={config.SPAM_CONFIDENCE_THRESHOLD:.0%}일 때만 스팸 이동")
        console.print("  🛡️ SAFE_SENDERS/SAFE_DOMAINS → 항상 레이블만")
        console.print()
        
        # 첫 실행
        self._process_emails()
        self._check_weekly_report()
        self._learn_safe_senders()

        # 주기적 실행
        while self.running:
            logger.info(f"다음 실행까지 {self.interval_minutes}분 대기...")

            for _ in range(self.interval_minutes * 60):
                if not self.running:
                    break
                time.sleep(1)

            if self.running:
                self._process_emails()
                self._check_weekly_report()
                self._learn_safe_senders()
        
        logger.info("스케줄러 종료됨")
    
    def stop(self):
        logger.info("스케줄러 중지 중...")
        self.running = False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Gmail Organizer 스케줄러")
    parser.add_argument("-i", "--interval", type=int, default=30, help="실행 간격 (분)")
    parser.add_argument("-n", "--batch-size", type=int, default=50, help="배치 크기")
    parser.add_argument("--analyze-only", action="store_true", help="분석만")
    
    args = parser.parse_args()
    
    scheduler = GmailScheduler(
        interval_minutes=args.interval,
        batch_size=args.batch_size,
        auto_organize=not args.analyze_only
    )
    
    scheduler.start()


if __name__ == "__main__":
    main()
