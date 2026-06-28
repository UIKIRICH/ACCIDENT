from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ReviewAssistResult(BaseModel):
    case_id: str
    route_type: Optional[str] = None      # 英文路由类型，可选
    route_type_cn: str                    # 中文路由类型
    review_priority_score: int
    review_priority_level: str
    review_priority_reason: str
    review_focus: List[str]
    conflict_summary: str
    evidence_status: str
    evidence_required_items: List[str]
    risk_notes: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None