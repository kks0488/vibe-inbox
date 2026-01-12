"""
Gmail OAuth 2.0 인증 모듈
Google Cloud Console에서 OAuth 2.0 자격 증명을 설정해야 합니다.
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from rich.console import Console
from rich.panel import Panel

import config

console = Console()
logger = logging.getLogger(__name__)


def get_gmail_credentials() -> Credentials:
    """
    Gmail API 인증 자격 증명을 가져옵니다.
    
    Returns:
        Credentials: 유효한 Gmail API 자격 증명
        
    Raises:
        FileNotFoundError: credentials.json 파일이 없는 경우
    """
    creds = None
    token_path = config.GMAIL_TOKEN_PATH
    credentials_path = Path(config.GMAIL_CREDENTIALS_PATH)
    
    # 기존 토큰이 있으면 로드
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), config.GMAIL_SCOPES)
        console.print("[green]✓[/green] 기존 인증 토큰을 로드했습니다.")
    
    # 토큰이 없거나 만료된 경우
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            console.print("[yellow]⟳[/yellow] 토큰을 갱신하는 중...")
            creds.refresh(Request())
        else:
            # 새로운 인증 필요
            if not credentials_path.exists():
                console.print(Panel(
                    "[red]credentials.json 파일이 없습니다![/red]\n\n"
                    "Gmail API를 사용하려면 다음 단계를 따라주세요:\n\n"
                    "1. [link=https://console.cloud.google.com/]Google Cloud Console[/link] 접속\n"
                    "2. 새 프로젝트 생성 또는 기존 프로젝트 선택\n"
                    "3. Gmail API 활성화\n"
                    "4. OAuth 2.0 클라이언트 ID 생성 (데스크톱 앱)\n"
                    "5. credentials.json 다운로드\n"
                    "6. 이 폴더에 credentials.json 파일 배치\n\n"
                    "자세한 안내는 README.md를 참조하세요.",
                    title="⚠️ 인증 설정 필요",
                    border_style="red"
                ))
                raise FileNotFoundError(
                    "credentials.json 파일이 필요합니다. README.md의 설정 가이드를 참조하세요."
                )
            
            console.print("[cyan]🔐[/cyan] 브라우저에서 Google 계정으로 로그인해주세요...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), 
                config.GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
            console.print("[green]✓[/green] 인증 완료!")
        
        # 토큰 저장 (보안: 소유자만 읽기/쓰기 가능)
        with open(token_path, 'w') as token_file:
            token_file.write(creds.to_json())
        os.chmod(token_path, 0o600)  # 소유자만 읽기/쓰기
        console.print(f"[green]✓[/green] 인증 토큰을 저장했습니다: {token_path}")
    
    return creds


def revoke_credentials():
    """저장된 인증 토큰을 삭제합니다."""
    token_path = config.GMAIL_TOKEN_PATH
    if token_path.exists():
        os.remove(token_path)
        console.print("[yellow]✓[/yellow] 인증 토큰이 삭제되었습니다.")
    else:
        console.print("[gray]인증 토큰이 없습니다.[/gray]")


def check_auth_status() -> bool:
    """
    현재 인증 상태를 확인합니다.

    Returns:
        bool: 인증되어 있으면 True
    """
    token_path = config.GMAIL_TOKEN_PATH

    if not token_path.exists():
        console.print("[red]✗[/red] 인증되지 않음")
        return False

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), config.GMAIL_SCOPES)
        if creds.valid:
            # 만료 시간 확인
            expiry_info = get_token_expiry_info(creds)
            if expiry_info:
                hours_remaining, status = expiry_info
                if status == "warning":
                    console.print(f"[yellow]⚠[/yellow] 인증됨 (만료까지 {hours_remaining:.1f}시간)")
                else:
                    console.print(f"[green]✓[/green] 인증됨 (만료까지 {hours_remaining:.1f}시간)")
            else:
                console.print("[green]✓[/green] 인증됨 (유효)")
            return True
        elif creds.expired:
            console.print("[yellow]⚠[/yellow] 토큰 만료됨 (갱신 필요)")
            return False
    except Exception as e:
        console.print(f"[red]✗[/red] 인증 확인 실패: {e}")
        return False

    return False


def get_token_expiry_info(creds: Credentials) -> Optional[Tuple[float, str]]:
    """
    토큰 만료 정보를 반환합니다.

    Args:
        creds: Google OAuth2 자격 증명

    Returns:
        Tuple[float, str]: (남은 시간(시간), 상태) 또는 None
        상태: "ok", "warning", "critical", "expired"
    """
    if not creds or not creds.expiry:
        return None

    now = datetime.now(timezone.utc)
    expiry = creds.expiry

    # expiry가 timezone-naive인 경우 UTC로 가정
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    time_remaining = expiry - now
    hours_remaining = time_remaining.total_seconds() / 3600

    if hours_remaining <= 0:
        return (0, "expired")
    elif hours_remaining <= config.TOKEN_AUTO_REFRESH_HOURS:
        return (hours_remaining, "critical")
    elif hours_remaining <= config.TOKEN_EXPIRY_WARNING_HOURS:
        return (hours_remaining, "warning")
    else:
        return (hours_remaining, "ok")


def check_and_refresh_token() -> Tuple[bool, str]:
    """
    토큰을 확인하고 필요 시 갱신합니다.

    Returns:
        Tuple[bool, str]: (성공 여부, 메시지)
    """
    token_path = config.GMAIL_TOKEN_PATH

    if not token_path.exists():
        return (False, "토큰 파일 없음")

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), config.GMAIL_SCOPES)

        # 만료 정보 확인
        expiry_info = get_token_expiry_info(creds)

        if expiry_info:
            hours_remaining, status = expiry_info
            logger.debug(f"토큰 상태: {status}, 남은 시간: {hours_remaining:.1f}시간")

            # 만료되었거나 임계치 이하이면 갱신 시도
            if status in ("expired", "critical"):
                if creds.refresh_token:
                    logger.info(f"토큰 사전 갱신 시작 (남은 시간: {hours_remaining:.1f}시간)")
                    creds.refresh(Request())

                    # 갱신된 토큰 저장
                    with open(token_path, 'w') as token_file:
                        token_file.write(creds.to_json())
                    os.chmod(token_path, 0o600)

                    logger.info("토큰 사전 갱신 완료")
                    return (True, f"토큰 사전 갱신 완료 (이전 남은 시간: {hours_remaining:.1f}시간)")
                else:
                    return (False, "Refresh 토큰 없음 - 재인증 필요")

            # 경고 상태
            elif status == "warning":
                logger.warning(f"토큰이 곧 만료됩니다 ({hours_remaining:.1f}시간 후)")
                return (True, f"토큰 만료 경고 ({hours_remaining:.1f}시간 후)")

            # 정상 상태
            else:
                return (True, f"토큰 정상 ({hours_remaining:.1f}시간 남음)")

        # 만료 정보가 없는 경우
        if creds.valid:
            return (True, "토큰 유효")
        elif creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, 'w') as token_file:
                token_file.write(creds.to_json())
            os.chmod(token_path, 0o600)
            return (True, "토큰 갱신 완료")
        else:
            return (False, "토큰 무효 - 재인증 필요")

    except Exception as e:
        logger.error(f"토큰 확인/갱신 오류: {e}")
        return (False, f"오류: {e}")


if __name__ == "__main__":
    # 테스트용 실행
    console.print("\n[bold]Gmail 인증 상태 확인[/bold]\n")
    check_auth_status()

