"""
분류 통계 및 기록 모듈
이메일 분류 결과를 추적하고 통계를 관리
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ClassificationRecord:
    """분류 기록"""
    timestamp: str
    email_id: str
    subject: str
    sender_email: str
    category: str
    confidence: float
    reason: str
    action_taken: str  # keep, archive, spam


class ClassificationStats:
    """분류 통계 관리"""
    
    def __init__(self, log_dir: Path = None):
        self.log_dir = log_dir or Path(__file__).parent / "logs"
        self.log_dir.mkdir(exist_ok=True)
        self.records_file = self.log_dir / "classification_history.json"
        self.stats_file = self.log_dir / "classification_stats.json"
        
    def record(self, record: ClassificationRecord):
        """분류 기록 저장"""
        try:
            # 기존 기록 로드
            records = self._load_records()
            
            # 새 기록 추가 (최근 500개만 유지)
            records.append(asdict(record))
            if len(records) > 500:
                records = records[-500:]
            
            # 저장
            with open(self.records_file, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
                
            # 통계 업데이트
            self._update_stats(record)
            
        except Exception as e:
            logger.error(f"분류 기록 저장 오류: {e}")
    
    def _load_records(self) -> List[Dict]:
        """기록 로드"""
        if self.records_file.exists():
            try:
                with open(self.records_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def _update_stats(self, record: ClassificationRecord):
        """통계 업데이트"""
        try:
            stats = self.get_stats()
            today = datetime.now().strftime("%Y-%m-%d")
            
            # 오늘 날짜 통계
            if today not in stats["daily"]:
                stats["daily"][today] = {
                    "total": 0,
                    "IMPORTANT": 0,
                    "NORMAL": 0,
                    "INFO": 0,
                    "SPAM": 0,
                    "archived": 0,
                    "spammed": 0
                }
            
            daily = stats["daily"][today]
            daily["total"] += 1
            daily[record.category] = daily.get(record.category, 0) + 1
            
            if record.action_taken == "archive":
                daily["archived"] += 1
            elif record.action_taken == "spam":
                daily["spammed"] += 1
            
            # 전체 통계
            stats["total_processed"] = stats.get("total_processed", 0) + 1
            stats["last_updated"] = datetime.now().isoformat()
            
            # 최근 7일만 유지
            cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            stats["daily"] = {
                k: v for k, v in stats["daily"].items()
                if k >= cutoff
            }
            
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"통계 업데이트 오류: {e}")
    
    def get_stats(self) -> Dict:
        """통계 조회"""
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"daily": {}, "total_processed": 0}
    
    def get_recent_records(self, limit: int = 20) -> List[Dict]:
        """최근 분류 기록 조회"""
        records = self._load_records()
        return records[-limit:] if records else []
    
    def get_summary(self) -> str:
        """통계 요약 문자열"""
        stats = self.get_stats()
        today = datetime.now().strftime("%Y-%m-%d")
        daily = stats.get("daily", {}).get(today, {})
        
        return (
            f"오늘 처리: {daily.get('total', 0)}개 | "
            f"중요: {daily.get('IMPORTANT', 0)} | "
            f"일반: {daily.get('NORMAL', 0)} | "
            f"정보: {daily.get('INFO', 0)} | "
            f"스팸: {daily.get('SPAM', 0)}"
        )


# 싱글톤 인스턴스
_stats_instance: Optional[ClassificationStats] = None

def get_stats() -> ClassificationStats:
    """통계 인스턴스 반환"""
    global _stats_instance
    if _stats_instance is None:
        _stats_instance = ClassificationStats()
    return _stats_instance
