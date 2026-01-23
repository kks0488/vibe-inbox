"""
안전 발신자 자동 학습 모듈
사용자가 응답한 이메일의 발신자를 자동으로 안전 목록에 추가
"""
import json
import logging
from typing import Set, Optional, List
from datetime import datetime
from pathlib import Path

import config

logger = logging.getLogger(__name__)


class SafeSenderLearner:
    """안전 발신자 자동 학습 클래스"""

    def __init__(self, gmail_client=None):
        self.gmail_client = gmail_client
        self.enabled = config.AUTO_LEARN_SAFE_SENDERS
        self.safe_senders_file = config.SAFE_SENDERS_FILE
        self._known_senders: Set[str] = set()
        self._known_domains: Set[str] = set()
        self._load_current_safe_senders()

    def _load_current_safe_senders(self):
        """현재 안전 발신자 목록 로드"""
        if self.safe_senders_file.exists():
            try:
                with open(self.safe_senders_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._known_senders = set(s.lower() for s in data.get("senders", []))
                    self._known_domains = set(d.lower() for d in data.get("domains", []))
            except Exception as e:
                logger.warning(f"안전 발신자 목록 로드 실패: {e}")

    def _save_safe_senders(self, senders: Set[str], domains: Set[str]):
        """안전 발신자 목록 저장"""
        try:
            data = {
                "description": "신뢰할 수 있는 발신자/도메인 목록. 이 목록에 있는 발신자는 자동 보관/스팸 처리되지 않습니다.",
                "updated_at": datetime.now().strftime("%Y-%m-%d"),
                "senders": sorted(list(senders)),
                "domains": sorted(list(domains))
            }
            with open(self.safe_senders_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"안전 발신자 목록 저장됨 (발신자: {len(senders)}, 도메인: {len(domains)})")
        except Exception as e:
            logger.error(f"안전 발신자 목록 저장 실패: {e}")

    def _extract_domain(self, email: str) -> Optional[str]:
        """이메일에서 도메인 추출"""
        if "@" in email:
            return email.split("@")[1].lower()
        return None

    def _is_already_safe(self, email: str) -> bool:
        """이미 안전 목록에 있는지 확인"""
        email_lower = email.lower()
        if email_lower in self._known_senders:
            return True
        domain = self._extract_domain(email)
        if domain and domain in self._known_domains:
            return True
        return False

    def learn_from_sent_emails(self, days: int = 30) -> int:
        """
        보낸 편지함에서 응답한 이메일의 수신자를 학습

        Args:
            days: 최근 며칠간의 보낸 메일을 확인할지

        Returns:
            새로 추가된 발신자 수
        """
        if not self.enabled or not self.gmail_client:
            return 0

        try:
            # 보낸 편지함에서 최근 이메일 가져오기
            from datetime import timedelta
            from gmail_client import GmailClient

            results = self.gmail_client.service.users().messages().list(
                userId='me',
                maxResults=100,
                q=f"in:sent newer_than:{days}d"
            ).execute()

            messages = results.get('messages', [])
            if not messages:
                return 0

            new_senders: Set[str] = set()

            for msg in messages:
                try:
                    message = self.gmail_client.service.users().messages().get(
                        userId='me',
                        id=msg['id'],
                        format='metadata',
                        metadataHeaders=['To', 'Cc']
                    ).execute()

                    headers = message.get('payload', {}).get('headers', [])
                    for header in headers:
                        if header['name'].lower() in ['to', 'cc']:
                            # 이메일 주소 추출
                            recipients = header['value']
                            for part in recipients.split(','):
                                part = part.strip()
                                if '<' in part and '>' in part:
                                    email = part.split('<')[1].split('>')[0].lower()
                                else:
                                    email = part.lower()

                                if '@' in email and not self._is_already_safe(email):
                                    new_senders.add(email)
                except Exception as e:
                    logger.debug(f"메일 처리 중 오류: {e}")
                    continue

            # 새 발신자 추가
            if new_senders:
                updated_senders = self._known_senders | new_senders
                self._save_safe_senders(updated_senders, self._known_domains)
                self._known_senders = updated_senders
                logger.info(f"자동 학습: {len(new_senders)}명의 새 발신자 추가됨")
                return len(new_senders)

            return 0

        except Exception as e:
            logger.error(f"보낸 편지함 학습 실패: {e}")
            return 0

    def learn_from_replied_threads(self) -> int:
        """
        답장한 스레드의 원본 발신자를 학습

        Returns:
            새로 추가된 발신자 수
        """
        if not self.enabled or not self.gmail_client:
            return 0

        try:
            # 최근 답장한 메일 확인 (Re: 로 시작하는 보낸 메일)
            results = self.gmail_client.service.users().messages().list(
                userId='me',
                maxResults=50,
                q="in:sent subject:Re: newer_than:7d"
            ).execute()

            messages = results.get('messages', [])
            if not messages:
                return 0

            new_senders: Set[str] = set()

            for msg in messages:
                try:
                    # 스레드 ID로 원본 메일 찾기
                    thread_id = msg.get('threadId')
                    if not thread_id:
                        continue

                    thread = self.gmail_client.service.users().threads().get(
                        userId='me',
                        id=thread_id,
                        format='metadata',
                        metadataHeaders=['From']
                    ).execute()

                    thread_messages = thread.get('messages', [])
                    for thread_msg in thread_messages:
                        # 내가 보낸 메일이 아닌 경우 (받은 메일)
                        labels = thread_msg.get('labelIds', [])
                        if 'SENT' not in labels:
                            headers = thread_msg.get('payload', {}).get('headers', [])
                            for header in headers:
                                if header['name'].lower() == 'from':
                                    from_value = header['value']
                                    if '<' in from_value and '>' in from_value:
                                        email = from_value.split('<')[1].split('>')[0].lower()
                                    else:
                                        email = from_value.lower()

                                    if '@' in email and not self._is_already_safe(email):
                                        new_senders.add(email)
                except Exception as e:
                    logger.debug(f"스레드 처리 중 오류: {e}")
                    continue

            # 새 발신자 추가
            if new_senders:
                updated_senders = self._known_senders | new_senders
                self._save_safe_senders(updated_senders, self._known_domains)
                self._known_senders = updated_senders
                logger.info(f"답장 학습: {len(new_senders)}명의 새 발신자 추가됨")
                return len(new_senders)

            return 0

        except Exception as e:
            logger.error(f"답장 스레드 학습 실패: {e}")
            return 0

    def add_sender_manually(self, email: str) -> bool:
        """수동으로 안전 발신자 추가"""
        email_lower = email.lower()
        if self._is_already_safe(email_lower):
            return False

        self._known_senders.add(email_lower)
        self._save_safe_senders(self._known_senders, self._known_domains)
        return True

    def add_domain_manually(self, domain: str) -> bool:
        """수동으로 안전 도메인 추가"""
        domain_lower = domain.lower()
        if domain_lower in self._known_domains:
            return False

        self._known_domains.add(domain_lower)
        self._save_safe_senders(self._known_senders, self._known_domains)
        return True

    def get_stats(self) -> dict:
        """현재 안전 발신자 통계"""
        return {
            "senders": len(self._known_senders),
            "domains": len(self._known_domains),
            "enabled": self.enabled
        }
