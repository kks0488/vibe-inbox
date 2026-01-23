"""
Gmail API 클라이언트 모듈
이메일 가져오기, 레이블 관리, 이메일 정리 기능 제공
"""
import base64
import time
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import BatchHttpRequest
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from tqdm import tqdm
import logging

import config
from auth import get_gmail_credentials

logger = logging.getLogger(__name__)

console = Console()


@dataclass
class Email:
    """이메일 데이터 클래스"""
    id: str
    thread_id: str
    subject: str
    sender: str
    sender_email: str
    date: str
    snippet: str
    body: str
    labels: List[str]
    is_unread: bool
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "subject": self.subject,
            "sender": self.sender,
            "sender_email": self.sender_email,
            "date": self.date,
            "snippet": self.snippet,
            "body": self.body[:config.MAX_EMAIL_CONTENT_LENGTH],
            "labels": self.labels,
            "is_unread": self.is_unread
        }


class GmailClient:
    """Gmail API 클라이언트"""
    
    def __init__(self):
        self.creds = get_gmail_credentials()
        self.service = build('gmail', 'v1', credentials=self.creds)
        self.user_id = 'me'
        self._labels_cache: Dict[str, str] = {}
        
    def _get_label_name(self, label_id: str) -> str:
        """레이블 ID를 이름으로 변환"""
        if not self._labels_cache:
            self._refresh_labels_cache()
        return self._labels_cache.get(label_id, label_id)
    
    def _refresh_labels_cache(self):
        """레이블 캐시 갱신"""
        try:
            results = self.service.users().labels().list(userId=self.user_id).execute()
            labels = results.get('labels', [])
            self._labels_cache = {label['id']: label['name'] for label in labels}
        except HttpError as e:
            console.print(f"[red]레이블 로드 실패: {e}[/red]")
    
    def get_emails(
        self, 
        max_results: int = 50, 
        query: str = "",
        include_spam_trash: bool = False
    ) -> List[Email]:
        """
        이메일 목록을 가져옵니다.
        
        Args:
            max_results: 가져올 최대 이메일 수
            query: Gmail 검색 쿼리 (예: "is:unread", "from:example@gmail.com")
            include_spam_trash: 스팸/휴지통 포함 여부
            
        Returns:
            Email 객체 리스트
        """
        emails = []
        
        try:
            # 이메일 ID 목록 가져오기
            results = self.service.users().messages().list(
                userId=self.user_id,
                maxResults=max_results,
                q=query,
                includeSpamTrash=include_spam_trash
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                console.print("[yellow]가져올 이메일이 없습니다.[/yellow]")
                return emails
            
            console.print(f"[cyan]📧[/cyan] {len(messages)}개의 이메일을 가져오는 중...")

            # Batch API를 사용하여 이메일 상세 정보 병렬 가져오기
            msg_ids = [msg['id'] for msg in messages]
            emails = self._batch_get_emails(msg_ids)

        except HttpError as e:
            console.print(f"[red]이메일 가져오기 실패: {e}[/red]")

        return emails

    def _batch_get_emails(self, msg_ids: List[str]) -> List[Email]:
        """
        Batch API를 사용하여 여러 이메일을 병렬로 가져옵니다.
        Rate limit 방지를 위해 배치 간 딜레이와 재시도 로직 포함.

        Args:
            msg_ids: 가져올 이메일 ID 목록

        Returns:
            Email 객체 리스트
        """
        emails: List[Email] = []
        results: Dict[str, Any] = {}
        failed_ids: List[str] = []

        def callback(request_id: str, response: Any, exception: Exception):
            """배치 요청 콜백"""
            if exception is not None:
                # Rate limit 에러인 경우 재시도 목록에 추가
                if '429' in str(exception) or 'rateLimitExceeded' in str(exception):
                    failed_ids.append(request_id)
                else:
                    logger.warning(f"이메일 가져오기 실패 ({request_id}): {exception}")
            else:
                results[request_id] = response

        # 배치 크기로 나누어 처리
        total_batches = (len(msg_ids) + config.GMAIL_BATCH_SIZE - 1) // config.GMAIL_BATCH_SIZE

        with tqdm(total=len(msg_ids), desc="이메일 로딩") as pbar:
            for batch_idx in range(total_batches):
                start_idx = batch_idx * config.GMAIL_BATCH_SIZE
                end_idx = min(start_idx + config.GMAIL_BATCH_SIZE, len(msg_ids))
                batch_ids = msg_ids[start_idx:end_idx]

                # 배치 요청 생성
                batch = self.service.new_batch_http_request(callback=callback)

                for msg_id in batch_ids:
                    request = self.service.users().messages().get(
                        userId=self.user_id,
                        id=msg_id,
                        format='full'
                    )
                    batch.add(request, request_id=msg_id)

                # 배치 실행 (재시도 로직 포함)
                for retry in range(config.GMAIL_RETRY_MAX):
                    try:
                        batch.execute()
                        break
                    except HttpError as e:
                        if '429' in str(e) or 'rateLimitExceeded' in str(e):
                            delay = config.GMAIL_RETRY_DELAY * (2 ** retry)
                            logger.warning(f"Rate limit 도달, {delay}초 후 재시도...")
                            time.sleep(delay)
                        else:
                            logger.error(f"배치 요청 실패: {e}")
                            break

                pbar.update(len(batch_ids))

                # 배치 간 딜레이 (Rate limit 방지)
                if batch_idx < total_batches - 1:
                    time.sleep(config.GMAIL_BATCH_DELAY)

        # 실패한 이메일 개별 재시도
        if failed_ids:
            logger.info(f"{len(failed_ids)}개 이메일 개별 재시도 중...")
            for msg_id in failed_ids:
                time.sleep(config.GMAIL_RETRY_DELAY)
                for retry in range(config.GMAIL_RETRY_MAX):
                    try:
                        response = self.service.users().messages().get(
                            userId=self.user_id,
                            id=msg_id,
                            format='full'
                        ).execute()
                        results[msg_id] = response
                        break
                    except HttpError as e:
                        if retry < config.GMAIL_RETRY_MAX - 1:
                            time.sleep(config.GMAIL_RETRY_DELAY * (2 ** retry))
                        else:
                            logger.warning(f"이메일 가져오기 최종 실패 ({msg_id})")

        # 결과 처리하여 Email 객체 생성
        for msg_id in msg_ids:
            if msg_id in results:
                email = self._parse_email_response(msg_id, results[msg_id])
                if email:
                    emails.append(email)

        return emails

    def _parse_email_response(self, msg_id: str, message: Dict) -> Optional[Email]:
        """API 응답을 Email 객체로 파싱합니다."""
        try:
            headers = message.get('payload', {}).get('headers', [])

            # 헤더에서 정보 추출
            subject = ""
            sender = ""
            sender_email = ""
            date = ""

            for header in headers:
                name = header['name'].lower()
                value = header['value']

                if name == 'subject':
                    subject = value
                elif name == 'from':
                    sender = value
                    # 이메일 주소 추출
                    if '<' in value and '>' in value:
                        sender_email = value.split('<')[1].split('>')[0]
                    else:
                        sender_email = value
                elif name == 'date':
                    date = value

            # 본문 추출
            body = self._extract_body(message.get('payload', {}))

            # 레이블 정보
            label_ids = message.get('labelIds', [])
            labels = [self._get_label_name(lid) for lid in label_ids]
            is_unread = 'UNREAD' in label_ids

            return Email(
                id=msg_id,
                thread_id=message.get('threadId', ''),
                subject=subject,
                sender=sender,
                sender_email=sender_email,
                date=date,
                snippet=message.get('snippet', ''),
                body=body,
                labels=labels,
                is_unread=is_unread
            )

        except Exception as e:
            logger.warning(f"이메일 파싱 실패 ({msg_id}): {e}")
            return None
    
    def _get_email_detail(self, msg_id: str) -> Optional[Email]:
        """이메일 상세 정보를 가져옵니다."""
        try:
            message = self.service.users().messages().get(
                userId=self.user_id,
                id=msg_id,
                format='full'
            ).execute()
            
            headers = message.get('payload', {}).get('headers', [])
            
            # 헤더에서 정보 추출
            subject = ""
            sender = ""
            sender_email = ""
            date = ""
            
            for header in headers:
                name = header['name'].lower()
                value = header['value']
                
                if name == 'subject':
                    subject = value
                elif name == 'from':
                    sender = value
                    # 이메일 주소 추출
                    if '<' in value and '>' in value:
                        sender_email = value.split('<')[1].split('>')[0]
                    else:
                        sender_email = value
                elif name == 'date':
                    date = value
            
            # 본문 추출
            body = self._extract_body(message.get('payload', {}))
            
            # 레이블 정보
            label_ids = message.get('labelIds', [])
            labels = [self._get_label_name(lid) for lid in label_ids]
            is_unread = 'UNREAD' in label_ids
            
            return Email(
                id=msg_id,
                thread_id=message.get('threadId', ''),
                subject=subject,
                sender=sender,
                sender_email=sender_email,
                date=date,
                snippet=message.get('snippet', ''),
                body=body,
                labels=labels,
                is_unread=is_unread
            )
            
        except HttpError as e:
            console.print(f"[red]이메일 상세 정보 가져오기 실패 ({msg_id}): {e}[/red]")
            return None
    
    def _extract_body(self, payload: Dict) -> str:
        """이메일 본문을 추출합니다. text/plain 우선, 없으면 text/html 사용"""
        import re
        
        plain_body = ""
        html_body = ""
        
        def extract_parts(part):
            nonlocal plain_body, html_body
            
            mime_type = part.get('mimeType', '')
            
            # 직접 body 데이터가 있는 경우
            if part.get('body', {}).get('data'):
                data = part['body']['data']
                try:
                    decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    if mime_type == 'text/plain' and not plain_body:
                        plain_body = decoded
                    elif mime_type == 'text/html' and not html_body:
                        html_body = decoded
                except (base64.binascii.Error, UnicodeDecodeError) as e:
                    logger.debug(f"Failed to decode email body: {e}")
            
            # 하위 parts 재귀 처리
            if 'parts' in part:
                for subpart in part['parts']:
                    extract_parts(subpart)
        
        # 페이로드 처리
        extract_parts(payload)
        
        # text/plain 우선, 없으면 HTML에서 텍스트 추출
        if plain_body:
            body = plain_body
        elif html_body:
            # HTML 태그 제거
            body = re.sub(r'<style[^>]*>.*?</style>', '', html_body, flags=re.DOTALL | re.IGNORECASE)
            body = re.sub(r'<script[^>]*>.*?</script>', '', body, flags=re.DOTALL | re.IGNORECASE)
            body = re.sub(r'<[^>]+>', ' ', body)
            body = re.sub(r'&nbsp;', ' ', body)
            body = re.sub(r'&[a-z]+;', '', body)
            body = re.sub(r'\s+', ' ', body).strip()
        else:
            body = ""
        
        return body[:config.MAX_EMAIL_CONTENT_LENGTH]
    
    def create_label(self, label_name: str, color: Optional[str] = None) -> Optional[str]:
        """
        새 레이블을 생성합니다.
        
        Args:
            label_name: 레이블 이름
            color: 레이블 색상 (선택)
            
        Returns:
            생성된 레이블 ID 또는 None
        """
        label_body = {
            'name': label_name,
            'labelListVisibility': 'labelShow',
            'messageListVisibility': 'show'
        }
        
        try:
            label = self.service.users().labels().create(
                userId=self.user_id,
                body=label_body
            ).execute()
            
            self._refresh_labels_cache()
            console.print(f"[green]✓[/green] 레이블 생성됨: {label_name}")
            return label['id']
            
        except HttpError as e:
            if 'already exists' in str(e).lower():
                # 이미 존재하는 레이블 찾기
                for lid, name in self._labels_cache.items():
                    if name == label_name:
                        return lid
            console.print(f"[red]레이블 생성 실패: {e}[/red]")
            return None
    
    def get_or_create_label(self, label_name: str) -> Optional[str]:
        """레이블을 가져오거나 없으면 생성합니다."""
        self._refresh_labels_cache()
        
        for lid, name in self._labels_cache.items():
            if name == label_name:
                return lid
        
        return self.create_label(label_name)
    
    def apply_label(self, msg_id: str, label_id: str) -> bool:
        """이메일에 레이블을 적용합니다."""
        try:
            self.service.users().messages().modify(
                userId=self.user_id,
                id=msg_id,
                body={'addLabelIds': [label_id]}
            ).execute()
            return True
        except HttpError as e:
            console.print(f"[red]레이블 적용 실패: {e}[/red]")
            return False

    def batch_apply_labels(
        self,
        modifications: List[Dict[str, Any]]
    ) -> Dict[str, bool]:
        """
        여러 이메일에 레이블 작업을 배치로 적용합니다.

        Args:
            modifications: [{"msg_id": str, "add_labels": [str], "remove_labels": [str]}]

        Returns:
            {msg_id: success} 딕셔너리
        """
        results: Dict[str, bool] = {}

        def callback(request_id: str, response: Any, exception: Exception):
            if exception is not None:
                logger.warning(f"배치 레이블 적용 실패 ({request_id}): {exception}")
                results[request_id] = False
            else:
                results[request_id] = True

        # 배치 크기로 나누어 처리
        total_batches = (len(modifications) + config.GMAIL_BATCH_SIZE - 1) // config.GMAIL_BATCH_SIZE

        for batch_idx in range(total_batches):
            start_idx = batch_idx * config.GMAIL_BATCH_SIZE
            end_idx = min(start_idx + config.GMAIL_BATCH_SIZE, len(modifications))
            batch_mods = modifications[start_idx:end_idx]

            batch = self.service.new_batch_http_request(callback=callback)

            for mod in batch_mods:
                msg_id = mod['msg_id']
                body = {}
                if mod.get('add_labels'):
                    body['addLabelIds'] = mod['add_labels']
                if mod.get('remove_labels'):
                    body['removeLabelIds'] = mod['remove_labels']

                request = self.service.users().messages().modify(
                    userId=self.user_id,
                    id=msg_id,
                    body=body
                )
                batch.add(request, request_id=msg_id)

            try:
                batch.execute()
            except HttpError as e:
                logger.error(f"배치 레이블 요청 실패: {e}")

        return results

    def batch_archive(self, msg_ids: List[str]) -> Dict[str, bool]:
        """여러 이메일을 배치로 보관처리합니다."""
        modifications = [
            {"msg_id": msg_id, "remove_labels": ["INBOX"]}
            for msg_id in msg_ids
        ]
        return self.batch_apply_labels(modifications)

    def batch_mark_as_spam(self, msg_ids: List[str]) -> Dict[str, bool]:
        """여러 이메일을 배치로 스팸 처리합니다."""
        modifications = [
            {"msg_id": msg_id, "add_labels": ["SPAM"], "remove_labels": ["INBOX"]}
            for msg_id in msg_ids
        ]
        return self.batch_apply_labels(modifications)

    def remove_label(self, msg_id: str, label_id: str) -> bool:
        """이메일에서 레이블을 제거합니다."""
        try:
            self.service.users().messages().modify(
                userId=self.user_id,
                id=msg_id,
                body={'removeLabelIds': [label_id]}
            ).execute()
            return True
        except HttpError as e:
            console.print(f"[red]레이블 제거 실패: {e}[/red]")
            return False

    def archive_email(self, msg_id: str) -> bool:
        """이메일을 보관처리합니다 (받은편지함에서 제거)."""
        return self.remove_label(msg_id, 'INBOX')

    def mark_as_spam(self, msg_id: str) -> bool:
        """이메일을 스팸으로 표시합니다."""
        try:
            self.service.users().messages().modify(
                userId=self.user_id,
                id=msg_id,
                body={
                    'addLabelIds': ['SPAM'],
                    'removeLabelIds': ['INBOX']
                }
            ).execute()
            return True
        except HttpError as e:
            console.print(f"[red]스팸 표시 실패: {e}[/red]")
            return False
    
    def trash_email(self, msg_id: str) -> bool:
        """이메일을 휴지통으로 이동합니다."""
        try:
            self.service.users().messages().trash(
                userId=self.user_id,
                id=msg_id
            ).execute()
            return True
        except HttpError as e:
            console.print(f"[red]삭제 실패: {e}[/red]")
            return False
    
    def mark_as_read(self, msg_id: str) -> bool:
        """이메일을 읽음으로 표시합니다."""
        return self.remove_label(msg_id, 'UNREAD')
    
    def get_profile(self) -> Dict[str, Any]:
        """계정 프로필 정보를 가져옵니다."""
        try:
            profile = self.service.users().getProfile(userId=self.user_id).execute()
            return profile
        except HttpError as e:
            console.print(f"[red]프로필 가져오기 실패: {e}[/red]")
            return {}
    
    def get_inbox_stats(self) -> Dict[str, int]:
        """받은편지함 통계를 가져옵니다."""
        stats = {
            'total': 0,
            'unread': 0,
            'spam': 0,
            'trash': 0
        }
        
        try:
            # 전체 메일 수
            result = self.service.users().messages().list(
                userId=self.user_id, 
                maxResults=1,
                q="in:inbox"
            ).execute()
            stats['total'] = result.get('resultSizeEstimate', 0)
            
            # 읽지 않은 메일 수
            result = self.service.users().messages().list(
                userId=self.user_id, 
                maxResults=1,
                q="is:unread in:inbox"
            ).execute()
            stats['unread'] = result.get('resultSizeEstimate', 0)
            
            # 스팸 수
            result = self.service.users().messages().list(
                userId=self.user_id, 
                maxResults=1,
                q="in:spam"
            ).execute()
            stats['spam'] = result.get('resultSizeEstimate', 0)
            
        except HttpError as e:
            console.print(f"[red]통계 가져오기 실패: {e}[/red]")
        
        return stats


if __name__ == "__main__":
    # 테스트 실행
    client = GmailClient()
    
    # 프로필 확인
    profile = client.get_profile()
    console.print(f"\n[bold]📧 Gmail 계정:[/bold] {profile.get('emailAddress', 'N/A')}")
    
    # 통계 확인
    stats = client.get_inbox_stats()
    console.print(f"[bold]📊 받은편지함 통계:[/bold]")
    console.print(f"   전체: {stats['total']}개")
    console.print(f"   읽지않음: {stats['unread']}개")
    console.print(f"   스팸: {stats['spam']}개")

