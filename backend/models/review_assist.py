"""
复核辅助数据模型
"""
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class ReviewAssistResult(BaseModel):
    """复核辅助结果模型"""
    case_id: str
    route_type: str                    # manual_review_required / proceed_to_liability / insufficient_evidence
    route_type_cn: str                 # 重点复核 / 快速确认 / 补证复核
    review_focus: List[str]            # 复核重点列表
    review_priority_score: int         # 0-100
    review_priority_level: str         # 高 / 中 / 低
    conflict_summary: Optional[str] = None
    evidence_status: str               # 充分 / 有冲突 / 不足
    evidence_required_items: List[str] = []
    risk_notes: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None