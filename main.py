#!/usr/bin/env python3
"""
Gmail Organizer - AI 기반 이메일 정리 도구
OpenAI 호환 AI 모델로 이메일을 자동으로 분류하고 정리합니다.
"""
import argparse
import sys
from typing import List, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

import config
from auth import get_gmail_credentials, check_auth_status, revoke_credentials
from gmail_client import GmailClient, Email
from ai_classifier import EmailClassifier, ClassificationResult
from utils import is_safe_sender

console = Console()


def print_banner():
    """프로그램 배너를 출력합니다."""
    banner = """
   ██████╗ ███╗   ███╗ █████╗ ██╗██╗     
  ██╔════╝ ████╗ ████║██╔══██╗██║██║     
  ██║  ███╗██╔████╔██║███████║██║██║     
  ██║   ██║██║╚██╔╝██║██╔══██║██║██║     
  ╚██████╔╝██║ ╚═╝ ██║██║  ██║██║███████╗
   ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝╚══════╝
     ██████╗ ██████╗  ██████╗  █████╗ ███╗   ██╗██╗███████╗███████╗██████╗ 
    ██╔═══██╗██╔══██╗██╔════╝ ██╔══██╗████╗  ██║██║╚══███╔╝██╔════╝██╔══██╗
    ██║   ██║██████╔╝██║  ███╗███████║██╔██╗ ██║██║  ███╔╝ █████╗  ██████╔╝
    ██║   ██║██╔══██╗██║   ██║██╔══██║██║╚██╗██║██║ ███╔╝  ██╔══╝  ██╔══██╗
    ╚██████╔╝██║  ██║╚██████╔╝██║  ██║██║ ╚████║██║███████╗███████╗██║  ██║
     ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝╚══════╝╚══════╝╚═╝  ╚═╝
    """
    console.print(f"[cyan]{banner}[/cyan]")
    console.print("[bold]AI 기반 Gmail 정리 도구[/bold] - Powered by OpenAI-compatible AI\n")


def cmd_status():
    """현재 상태를 확인합니다."""
    console.print("\n[bold]📊 현재 상태[/bold]\n")
    
    # 인증 상태
    console.print("[bold]인증 상태:[/bold]")
    check_auth_status()
    console.print()
    
    # API 키 상태
    if config.OPENAI_API_KEY:
        console.print(f"[green]✓[/green] AI API 키 설정됨 ({config.OPENAI_MODEL})")
    else:
        console.print(f"[red]✗[/red] AI API 키 미설정 (OPENAI_API_KEY)")
    
    # Gmail 연결 테스트
    try:
        client = GmailClient()
        profile = client.get_profile()
        stats = client.get_inbox_stats()
        
        console.print(f"\n[bold]Gmail 계정:[/bold] {profile.get('emailAddress', 'N/A')}")
        console.print(f"\n[bold]받은편지함 통계:[/bold]")
        console.print(f"  📬 전체: {stats['total']}개")
        console.print(f"  📩 읽지않음: {stats['unread']}개")
        console.print(f"  🚫 스팸: {stats['spam']}개")
    except Exception as e:
        console.print(f"\n[yellow]⚠ Gmail 연결 실패: {e}[/yellow]")


def cmd_analyze(count: int = 50, query: str = ""):
    """이메일을 분석하고 분류 결과를 보여줍니다."""
    console.print(f"\n[bold]🔍 이메일 분석[/bold] (최대 {count}개)\n")
    
    try:
        # Gmail 클라이언트 초기화
        client = GmailClient()
        
        # 이메일 가져오기
        emails = client.get_emails(max_results=count, query=query or "in:inbox")
        
        if not emails:
            console.print("[yellow]분석할 이메일이 없습니다.[/yellow]")
            return
        
        # AI 분류기 초기화
        classifier = EmailClassifier()
        
        # 분류 실행
        console.print(f"\n[cyan]🤖[/cyan] AI가 {len(emails)}개의 이메일을 분석하는 중...\n")
        results = classifier.classify_batch(emails, batch_size=5)
        
        # 결과 출력
        classifier.print_summary(results)
        classifier.print_detailed_results(results)
        
        return results
        
    except Exception as e:
        console.print(f"[red]✗ 분석 실패: {e}[/red]")
        import traceback
        traceback.print_exc()
        return []


def cmd_organize(count: int = 50, query: str = "", auto_apply: bool = False):
    """이메일을 분석하고 정리합니다."""
    console.print(f"\n[bold]🧹 이메일 정리[/bold] (최대 {count}개)\n")
    
    try:
        # Gmail 클라이언트 초기화
        client = GmailClient()
        
        # 이메일 가져오기
        emails = client.get_emails(max_results=count, query=query or "in:inbox")
        
        if not emails:
            console.print("[yellow]정리할 이메일이 없습니다.[/yellow]")
            return
        
        # AI 분류기 초기화
        classifier = EmailClassifier()
        
        # 분류 실행
        console.print(f"\n[cyan]🤖[/cyan] AI가 {len(emails)}개의 이메일을 분석하는 중...\n")
        results = classifier.classify_batch(emails, batch_size=5)
        
        # 결과 요약
        classifier.print_summary(results)
        
        # 카테고리별 정리
        summary = classifier.summarize_classifications(results)
        
        # 정리 작업 계획 표시
        actions_table = Table(title="📋 정리 작업 계획")
        actions_table.add_column("카테고리")
        actions_table.add_column("개수")
        actions_table.add_column("작업")
        
        plan_counts = {
            "labeled": 0,
            "archive": 0,
            "spam": 0,
        }
        
        for category, items in summary.items():
            if items:
                cat_info = config.EMAIL_CATEGORIES.get(category, {})
                action = cat_info.get('action', 'keep')

                total = len(items)
                will_archive = 0
                will_spam = 0

                for email, result in items:
                    if is_safe_sender(email):
                        continue
                    if action == "archive":
                        will_archive += 1
                    elif action == "spam" and result.confidence >= config.SPAM_CONFIDENCE_THRESHOLD:
                        will_spam += 1

                plan_counts["labeled"] += total
                plan_counts["archive"] += will_archive
                plan_counts["spam"] += will_spam

                if action == "archive":
                    action_text = f"보관처리: {will_archive}개, 레이블만: {total - will_archive}개"
                elif action == "spam":
                    action_text = (
                        f"스팸 이동(확신도≥{config.SPAM_CONFIDENCE_THRESHOLD:.0%}): {will_spam}개, "
                        f"레이블만: {total - will_spam}개"
                    )
                elif action == "suggest_unsubscribe":
                    action_text = "레이블 추가 (구독취소 권장)"
                else:
                    action_text = "레이블만 추가"
                
                actions_table.add_row(
                    cat_info.get('name', category),
                    str(len(items)),
                    action_text
                )
        
        console.print(actions_table)
        console.print()
        
        # 확인 후 적용
        if not auto_apply:
            if not Confirm.ask("[bold yellow]위 작업을 적용하시겠습니까?[/bold yellow]"):
                console.print("[yellow]작업이 취소되었습니다.[/yellow]")
                return
        
        # 레이블 생성 및 적용
        console.print("\n[cyan]🏷️[/cyan] 레이블 적용 중...\n")

        applied_counts = {
            "labeled": 0,
            "archive": 0,
            "spam": 0,
        }
        
        for category, items in summary.items():
            if not items:
                continue
                
            cat_info = config.EMAIL_CATEGORIES.get(category, {})
            label_name = f"{config.LABEL_PREFIX}{cat_info.get('name', category)}"
            
            # 레이블 생성/가져오기
            label_id = client.get_or_create_label(label_name)
            
            if not label_id:
                console.print(f"[yellow]레이블 생성 실패: {label_name}[/yellow]")
                continue
            
            action = cat_info.get('action', 'keep')
            
            for email, result in items:
                # 레이블 적용
                if client.apply_label(email.id, label_id):
                    applied_counts["labeled"] += 1
                
                # 안전 발신자는 항상 레이블만 적용
                if is_safe_sender(email):
                    continue
                
                # 추가 작업 적용
                if action == 'archive':
                    if client.archive_email(email.id):
                        applied_counts["archive"] += 1
                elif action == 'spam' and result.confidence >= config.SPAM_CONFIDENCE_THRESHOLD:
                    # 스팸은 충분히 높은 확신도일 때만
                    if client.mark_as_spam(email.id):
                        applied_counts["spam"] += 1
        
        console.print("\n[green]✓ 정리 완료![/green]")
        console.print(f"  📁 레이블 적용: {applied_counts['labeled']}개 (예상 {plan_counts['labeled']}개)")
        console.print(f"  📦 보관처리: {applied_counts['archive']}개 (예상 {plan_counts['archive']}개)")
        console.print(f"  🚫 스팸 이동: {applied_counts['spam']}개 (예상 {plan_counts['spam']}개)")
        
    except Exception as e:
        console.print(f"[red]✗ 정리 실패: {e}[/red]")
        import traceback
        traceback.print_exc()


def cmd_auth():
    """인증을 수행합니다."""
    console.print("\n[bold]🔐 Gmail 인증[/bold]\n")
    
    try:
        get_gmail_credentials()
        console.print("\n[green]✓ 인증 완료![/green]")
    except Exception as e:
        console.print(f"\n[red]✗ 인증 실패: {e}[/red]")


def cmd_logout():
    """인증 정보를 삭제합니다."""
    console.print("\n[bold]🚪 로그아웃[/bold]\n")
    
    if Confirm.ask("인증 정보를 삭제하시겠습니까?"):
        revoke_credentials()
        console.print("[green]✓ 로그아웃 완료[/green]")


def interactive_menu():
    """대화형 메뉴를 실행합니다."""
    print_banner()
    
    while True:
        console.print("\n[bold]메뉴를 선택하세요:[/bold]")
        console.print("  1. 📊 현재 상태 확인")
        console.print("  2. 🔍 이메일 분석 (분류만)")
        console.print("  3. 🧹 이메일 정리 (분류 + 정리)")
        console.print("  4. 🔐 Gmail 인증")
        console.print("  5. 🚪 로그아웃")
        console.print("  0. 종료")
        console.print()
        
        choice = Prompt.ask("선택", default="1")
        
        if choice == "0":
            console.print("\n[cyan]👋 안녕히 가세요![/cyan]\n")
            break
        elif choice == "1":
            cmd_status()
        elif choice == "2":
            count = int(Prompt.ask("분석할 이메일 수", default="30"))
            cmd_analyze(count=count)
        elif choice == "3":
            count = int(Prompt.ask("정리할 이메일 수", default="30"))
            cmd_organize(count=count)
        elif choice == "4":
            cmd_auth()
        elif choice == "5":
            cmd_logout()
        else:
            console.print("[yellow]잘못된 선택입니다.[/yellow]")


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="Gmail Organizer - AI 기반 이메일 정리 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예제:
  python main.py                    # 대화형 메뉴 실행
  python main.py status             # 상태 확인
  python main.py analyze -n 50      # 50개 이메일 분석
  python main.py organize -n 30     # 30개 이메일 정리
  python main.py auth               # Gmail 인증
  python main.py logout             # 로그아웃
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="명령어")
    
    # status 명령어
    subparsers.add_parser("status", help="현재 상태 확인")
    
    # analyze 명령어
    analyze_parser = subparsers.add_parser("analyze", help="이메일 분석")
    analyze_parser.add_argument("-n", "--count", type=int, default=50, help="분석할 이메일 수")
    analyze_parser.add_argument("-q", "--query", type=str, default="", help="Gmail 검색 쿼리")
    
    # organize 명령어
    organize_parser = subparsers.add_parser("organize", help="이메일 정리")
    organize_parser.add_argument("-n", "--count", type=int, default=50, help="정리할 이메일 수")
    organize_parser.add_argument("-q", "--query", type=str, default="", help="Gmail 검색 쿼리")
    organize_parser.add_argument("-y", "--yes", action="store_true", help="확인 없이 자동 적용")
    
    # auth 명령어
    subparsers.add_parser("auth", help="Gmail 인증")
    
    # logout 명령어
    subparsers.add_parser("logout", help="로그아웃")
    
    args = parser.parse_args()
    
    # 명령어 실행
    if args.command == "status":
        print_banner()
        cmd_status()
    elif args.command == "analyze":
        print_banner()
        cmd_analyze(count=args.count, query=args.query)
    elif args.command == "organize":
        print_banner()
        cmd_organize(count=args.count, query=args.query, auto_apply=args.yes)
    elif args.command == "auth":
        print_banner()
        cmd_auth()
    elif args.command == "logout":
        print_banner()
        cmd_logout()
    else:
        # 명령어 없으면 대화형 메뉴
        interactive_menu()


if __name__ == "__main__":
    main()
