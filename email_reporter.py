"""
주간 스팸 리포트 모듈
AI가 스팸으로 분류한 이메일을 주기적으로 사용자에게 이메일로 발송
"""
import base64
import json
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional
from pathlib import Path
import logging

import config
from gmail_client import GmailClient, Email

logger = logging.getLogger(__name__)


class WeeklyReporter:
    """주간 스팸 리포트 생성 및 발송"""
    
    def __init__(self, gmail_client: GmailClient):
        self.gmail = gmail_client
        self.report_label = f"{config.LABEL_PREFIX}스팸"
        self.state_file = Path(__file__).parent / "logs" / "report_state.json"
    
    def _load_state(self) -> Dict:
        """마지막 리포트 상태 로드"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError, IOError) as e:
                logger.debug(f"리포트 상태 파일 로드 실패: {e}")
        return {"last_report": None}
    
    def _save_state(self, state: Dict):
        """리포트 상태 저장"""
        self.state_file.parent.mkdir(exist_ok=True)
        with open(self.state_file, 'w') as f:
            json.dump(state, f)
    
    def should_send_report(self) -> bool:
        """리포트 발송 시간인지 확인 (7일마다)"""
        state = self._load_state()
        last_report = state.get("last_report")
        
        if not last_report:
            return True
        
        try:
            last_dt = datetime.fromisoformat(last_report)
            days_since = (datetime.now() - last_dt).days
            return days_since >= 7
        except (ValueError, TypeError) as e:
            logger.debug(f"리포트 날짜 파싱 실패: {e}")
            return True
    
    def get_spam_emails_this_week(self) -> List[Email]:
        """최근 7일간 AI가 스팸으로 분류한 이메일 조회"""
        # 날짜 범위 계산 (최근 7일)
        after_date = (datetime.now() - timedelta(days=7)).strftime("%Y/%m/%d")
        
        # AI/스팸 레이블이 있는 이메일 + 스팸함의 이메일
        queries = [
            f"label:{self.report_label} after:{after_date}",
            f"in:spam after:{after_date}"
        ]
        
        all_emails = []
        seen_ids = set()
        
        for query in queries:
            try:
                emails = self.gmail.get_emails(
                    max_results=100,
                    query=query,
                    include_spam_trash=True
                )
                for email in emails:
                    if email.id not in seen_ids:
                        seen_ids.add(email.id)
                        all_emails.append(email)
            except Exception as e:
                logger.error(f"스팸 이메일 조회 오류: {e}")
        
        return all_emails
    
    def get_weekly_stats(self) -> Dict:
        """주간 이메일 통계 조회"""
        after_date = (datetime.now() - timedelta(days=7)).strftime("%Y/%m/%d")
        stats = {
            "total": 0,
            "important": 0,
            "normal": 0,
            "info": 0,
            "spam": 0,
            "unread": 0
        }
        
        try:
            # 전체 받은 이메일
            result = self.gmail.service.users().messages().list(
                userId='me', maxResults=1, q=f"after:{after_date}"
            ).execute()
            stats["total"] = result.get('resultSizeEstimate', 0)
            
            # 분류별 통계
            for category in ["중요", "일반", "정보", "스팸"]:
                label = f"{config.LABEL_PREFIX}{category}"
                try:
                    result = self.gmail.service.users().messages().list(
                        userId='me', maxResults=1, 
                        q=f"label:{label} after:{after_date}"
                    ).execute()
                    key = {"중요": "important", "일반": "normal", "정보": "info", "스팸": "spam"}[category]
                    stats[key] = result.get('resultSizeEstimate', 0)
                except Exception as e:
                    logger.debug(f"카테고리 통계 조회 실패: {e}")
            
            # 미읽음
            result = self.gmail.service.users().messages().list(
                userId='me', maxResults=1, q=f"is:unread after:{after_date}"
            ).execute()
            stats["unread"] = result.get('resultSizeEstimate', 0)
            
        except Exception as e:
            logger.error(f"통계 조회 오류: {e}")
        
        return stats
    
    def get_top_senders(self, limit: int = 10) -> List[Dict]:
        """최근 7일간 최다 발신자 조회"""
        after_date = (datetime.now() - timedelta(days=7)).strftime("%Y/%m/%d")
        sender_counts = {}
        
        try:
            emails = self.gmail.get_emails(
                max_results=200,
                query=f"after:{after_date}",
                include_spam_trash=False
            )
            
            for email in emails:
                sender = email.sender_email or email.sender
                if sender:
                    sender_counts[sender] = sender_counts.get(sender, 0) + 1
            
            # 정렬하여 상위 N개 반환
            sorted_senders = sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)
            return [{"sender": s, "count": c} for s, c in sorted_senders[:limit]]
            
        except Exception as e:
            logger.error(f"발신자 통계 조회 오류: {e}")
            return []
    
    def generate_ai_insights(self, stats: Dict, top_senders: List[Dict], spam_count: int) -> List[str]:
        """AI 기반 개선 제안 생성"""
        insights = []
        
        total = stats.get("total", 0)
        if total == 0:
            return ["이번 주 이메일 데이터가 없습니다."]
        
        # 스팸 비율 분석
        spam_ratio = (spam_count / total * 100) if total > 0 else 0
        if spam_ratio > 30:
            insights.append(f"⚠️ 스팸/광고 비율이 {spam_ratio:.0f}%로 높습니다. 뉴스레터 구독 정리를 권장합니다.")
        
        # 미읽음 분석
        unread = stats.get("unread", 0)
        unread_ratio = (unread / total * 100) if total > 0 else 0
        if unread_ratio > 50:
            insights.append(f"📬 미읽음 이메일이 {unread_ratio:.0f}%입니다. 중요 메일 위주로 확인하세요.")
        
        # 최다 발신자 분석
        if top_senders:
            top = top_senders[0]
            if top["count"] >= 10:
                insights.append(f"📧 '{top['sender']}'에서 {top['count']}통 수신. 알림 설정 확인을 권장합니다.")
        
        # 분류 비율 분석
        important = stats.get("important", 0)
        if important > 0 and total > 0:
            imp_ratio = important / total * 100
            if imp_ratio < 20:
                insights.append(f"💡 중요 메일 비율이 {imp_ratio:.0f}%로 낮습니다. 대부분 자동 처리 가능한 메일입니다.")
        
        if not insights:
            insights.append("✅ 이메일 관리가 잘 되고 있습니다!")
        
        return insights
    
    def generate_report_html(
        self, 
        spam_emails: List[Email],
        stats: Dict = None,
        top_senders: List[Dict] = None,
        insights: List[str] = None
    ) -> str:
        """HTML 리포트 생성 (강화된 버전)"""
        now = datetime.now().strftime("%Y년 %m월 %d일")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y년 %m월 %d일")
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               max-width: 650px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                   color: white; padding: 25px; border-radius: 12px 12px 0 0; }}
        .content {{ background: white; padding: 25px; border-radius: 0 0 12px 12px; 
                    box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
        .section {{ margin-bottom: 25px; padding-bottom: 20px; border-bottom: 1px solid #eee; }}
        .section:last-child {{ border-bottom: none; margin-bottom: 0; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 15px 0; }}
        .stat-box {{ background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; }}
        .stat-number {{ font-size: 28px; font-weight: bold; color: #667eea; }}
        .stat-label {{ font-size: 12px; color: #666; margin-top: 5px; }}
        .email-item {{ border-bottom: 1px solid #eee; padding: 12px 0; }}
        .email-item:last-child {{ border-bottom: none; }}
        .subject {{ font-weight: 600; color: #333; margin-bottom: 3px; font-size: 14px; }}
        .sender {{ color: #666; font-size: 13px; }}
        .insight {{ background: #e8f4fd; padding: 12px 15px; border-radius: 8px; margin: 8px 0; 
                    border-left: 4px solid #667eea; font-size: 14px; }}
        .sender-item {{ display: flex; justify-content: space-between; padding: 8px 0; 
                        border-bottom: 1px solid #f0f0f0; }}
        .sender-item:last-child {{ border-bottom: none; }}
        .sender-count {{ background: #667eea; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; }}
        .warning {{ background: #fff3cd; padding: 15px; border-radius: 8px; margin-top: 20px; 
                    border-left: 4px solid #ffc107; }}
        h2 {{ margin: 0; }}
        h3 {{ color: #333; margin-bottom: 15px; font-size: 16px; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>📧 Gmail Organizer 주간 리포트</h2>
        <p style="margin: 10px 0 0; opacity: 0.9;">{week_ago} ~ {now}</p>
    </div>
    <div class="content">
"""
        
        # 통계 섹션
        if stats:
            total = stats.get('total', 0)
            important = stats.get('important', 0)
            spam = stats.get('spam', 0)
            unread = stats.get('unread', 0)
            
            html += f"""
        <div class="section">
            <h3>📊 이번 주 이메일 통계</h3>
            <div class="stats-grid">
                <div class="stat-box">
                    <div class="stat-number">{total}</div>
                    <div class="stat-label">전체</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" style="color: #28a745;">{important}</div>
                    <div class="stat-label">중요</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" style="color: #dc3545;">{len(spam_emails)}</div>
                    <div class="stat-label">스팸</div>
                </div>
            </div>
            <p style="text-align:center; color:#666; font-size:13px;">
                미읽음: {unread}개 | 정보: {stats.get('info', 0)}개 | 일반: {stats.get('normal', 0)}개
            </p>
        </div>
"""
        
        # AI 인사이트 섹션
        if insights:
            html += """
        <div class="section">
            <h3>💡 AI 분석 및 제안</h3>
"""
            for insight in insights:
                html += f'            <div class="insight">{insight}</div>\n'
            html += "        </div>\n"
        
        # 최다 발신자 섹션
        if top_senders and len(top_senders) > 0:
            html += """
        <div class="section">
            <h3>📬 최다 발신자 TOP 5</h3>
"""
            for sender in top_senders[:5]:
                sender_display = sender['sender'][:40] + '...' if len(sender['sender']) > 40 else sender['sender']
                html += f"""
            <div class="sender-item">
                <span style="font-size:13px;">{sender_display}</span>
                <span class="sender-count">{sender['count']}통</span>
            </div>
"""
            html += "        </div>\n"
        
        # 스팸 이메일 목록 섹션
        html += """
        <div class="section">
            <h3>🚫 스팸 분류된 이메일</h3>
"""
        if spam_emails:
            for email in spam_emails[:15]:  # 최대 15개만 표시
                subject = email.subject[:60] if email.subject else "(제목 없음)"
                sender = email.sender_email or email.sender or "(발신자 없음)"
                sender = sender[:35] + '...' if len(sender) > 35 else sender
                
                html += f"""
            <div class="email-item">
                <div class="subject">{subject}</div>
                <div class="sender">📤 {sender}</div>
            </div>
"""
            
            if len(spam_emails) > 15:
                html += f'            <p style="color:#666; text-align:center; font-size:13px;">... 외 {len(spam_emails) - 15}개</p>\n'
        else:
            html += '            <p style="text-align:center; color:#28a745;">✅ 이번 주에는 스팸이 없습니다!</p>\n'
        
        html += "        </div>\n"
        
        # 경고 섹션
        html += """
        <div class="warning">
            ⚠️ <strong>확인 권장</strong><br>
            AI가 실수로 중요한 이메일을 스팸으로 분류했을 수 있습니다.<br>
            Gmail 스팸함을 확인하고 필요시 복구해주세요.
        </div>
    </div>
</body>
</html>
"""
        return html
    
    def send_email(self, to: str, subject: str, body_html: str) -> bool:
        """이메일 발송 (Gmail API 사용)"""
        try:
            message = MIMEMultipart('alternative')
            message['to'] = to
            message['subject'] = subject
            
            html_part = MIMEText(body_html, 'html', 'utf-8')
            message.attach(html_part)
            
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            self.gmail.service.users().messages().send(
                userId='me',
                body={'raw': raw}
            ).execute()
            
            return True
        except Exception as e:
            logger.error(f"이메일 발송 실패: {e}")
            return False
    
    def send_weekly_report(self) -> bool:
        """주간 리포트 발송 (강화된 버전)"""
        try:
            # 프로필에서 이메일 주소 가져오기
            profile = self.gmail.get_profile()
            recipient = profile.get('emailAddress')
            
            if not recipient:
                logger.error("발송 대상 이메일 주소를 찾을 수 없음")
                return False
            
            # 데이터 수집
            logger.info("주간 리포트 데이터 수집 중...")
            
            # 스팸 이메일 목록 조회
            spam_emails = self.get_spam_emails_this_week()
            logger.info(f"스팸 이메일 {len(spam_emails)}개 발견")
            
            # 주간 통계 조회
            stats = self.get_weekly_stats()
            logger.info(f"주간 통계: 전체 {stats.get('total', 0)}개, 중요 {stats.get('important', 0)}개")
            
            # 최다 발신자 조회
            top_senders = self.get_top_senders(limit=10)
            logger.info(f"최다 발신자 {len(top_senders)}명 분석 완료")
            
            # AI 인사이트 생성
            insights = self.generate_ai_insights(stats, top_senders, len(spam_emails))
            logger.info(f"AI 인사이트 {len(insights)}개 생성")
            
            # 리포트 생성 및 발송
            html = self.generate_report_html(
                spam_emails=spam_emails,
                stats=stats,
                top_senders=top_senders,
                insights=insights
            )
            subject = f"[Gmail Organizer] 주간 이메일 리포트 ({datetime.now().strftime('%m/%d')})"
            
            if self.send_email(recipient, subject, html):
                logger.info(f"주간 리포트 발송 완료: {recipient}")
                
                # 상태 저장
                self._save_state({"last_report": datetime.now().isoformat()})
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"리포트 발송 오류: {e}", exc_info=True)
            return False
    
    def send_test_report(self) -> bool:
        """테스트 리포트 발송"""
        logger.info("테스트 리포트 발송 시작...")
        return self.send_weekly_report()


if __name__ == "__main__":
    # 테스트 실행
    from rich.console import Console
    console = Console()
    
    console.print("\n[bold]📊 주간 스팸 리포트 테스트[/bold]\n")
    
    client = GmailClient()
    reporter = WeeklyReporter(client)
    
    # 스팸 이메일 조회
    emails = reporter.get_spam_emails_this_week()
    console.print(f"[cyan]스팸 이메일:[/cyan] {len(emails)}개")
    
    for email in emails[:5]:
        console.print(f"  - {email.subject[:50]}... ({email.sender_email})")
    
    # 리포트 발송 여부 확인
    if reporter.should_send_report():
        console.print("\n[yellow]리포트 발송 필요[/yellow]")
    else:
        console.print("\n[green]리포트 발송 불필요 (7일 이내 발송됨)[/green]")
