"""
Slack 알림 모듈
중요 이메일 알림 및 처리 요약 전송
"""
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False

import config

logger = logging.getLogger(__name__)


@dataclass
class EmailNotification:
    """이메일 알림 데이터"""
    subject: str
    sender: str
    sender_email: str
    category: str
    confidence: float
    snippet: str = ""


class SlackNotifier:
    """Slack 알림 전송 클래스"""

    def __init__(self):
        self.enabled = config.SLACK_ENABLED and SLACK_AVAILABLE and config.SLACK_BOT_TOKEN
        self.client = None
        self.channel_id = config.SLACK_CHANNEL_ID

        if self.enabled:
            try:
                self.client = WebClient(token=config.SLACK_BOT_TOKEN)
                logger.info("Slack 알림 활성화됨")
            except Exception as e:
                logger.warning(f"Slack 클라이언트 초기화 실패: {e}")
                self.enabled = False
        else:
            if not SLACK_AVAILABLE:
                logger.debug("slack-sdk 미설치, Slack 알림 비활성화")
            elif not config.SLACK_BOT_TOKEN:
                logger.debug("SLACK_BOT_TOKEN 미설정, Slack 알림 비활성화")

    def _send_message(self, text: str, blocks: Optional[List[Dict]] = None) -> bool:
        """Slack 메시지 전송"""
        if not self.enabled or not self.channel_id:
            return False

        try:
            self.client.chat_postMessage(
                channel=self.channel_id,
                text=text,
                blocks=blocks
            )
            return True
        except SlackApiError as e:
            logger.error(f"Slack 메시지 전송 실패: {e.response['error']}")
            return False
        except Exception as e:
            logger.error(f"Slack 메시지 전송 오류: {e}")
            return False

    def notify_important_email(self, email: EmailNotification) -> bool:
        """중요 이메일 알림"""
        if not config.SLACK_NOTIFY_IMPORTANT:
            return False

        # 키워드 체크
        has_keyword = any(
            kw.lower() in email.subject.lower() or kw.lower() in email.snippet.lower()
            for kw in config.SLACK_IMPORTANT_KEYWORDS
        )

        # 중요 이메일이고 키워드가 있거나 확신도가 높은 경우만 알림
        if email.category != "IMPORTANT" or (not has_keyword and email.confidence < 0.9):
            return False

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📬 중요 이메일 도착",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*발신자:*\n{email.sender}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*확신도:*\n{email.confidence:.0%}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*제목:*\n{email.subject[:100]}"
                }
            }
        ]

        if email.snippet:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*미리보기:*\n>{email.snippet[:200]}..."
                }
            })

        blocks.append({"type": "divider"})

        return self._send_message(
            text=f"중요 이메일: {email.subject}",
            blocks=blocks
        )

    def notify_processing_summary(
        self,
        total: int,
        categories: Dict[str, int],
        archived: int,
        spam: int
    ) -> bool:
        """처리 요약 알림"""
        if not config.SLACK_NOTIFY_SPAM_SUMMARY:
            return False

        # 처리된 게 없으면 알림 안 함
        if total == 0:
            return False

        category_text = " | ".join([
            f"{cat}: {count}" for cat, count in categories.items()
        ])

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📊 Gmail 정리 완료",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*처리:* {total}개"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*보관:* {archived}개 | *스팸:* {spam}개"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"분류: {category_text}"
                    }
                ]
            }
        ]

        return self._send_message(
            text=f"Gmail 정리: {total}개 처리 (보관 {archived}, 스팸 {spam})",
            blocks=blocks
        )

    def notify_error(self, error_message: str) -> bool:
        """에러 알림"""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚠️ Gmail Organizer 오류",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"```{error_message[:500]}```"
                }
            }
        ]

        return self._send_message(
            text=f"Gmail Organizer 오류: {error_message[:100]}",
            blocks=blocks
        )


# 싱글톤 인스턴스
_notifier: Optional[SlackNotifier] = None


def get_notifier() -> SlackNotifier:
    """SlackNotifier 싱글톤 반환"""
    global _notifier
    if _notifier is None:
        _notifier = SlackNotifier()
    return _notifier
