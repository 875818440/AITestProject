import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RiskScoreResponse(BaseModel):
    user_id: uuid.UUID
    score: int = Field(ge=0, le=100)
    level: str   # normal | low | medium | high
    components: dict | None = None
    triggered_rules: list[str] | None = None
    model_version: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RiskScoreHistoryResponse(BaseModel):
    user_id: uuid.UUID
    total: int
    items: list[RiskScoreResponse]


class RiskSummary(BaseModel):
    """用户最新风险状态摘要。"""

    user_id: uuid.UUID
    current_score: int
    current_level: str
    trend: str  # stable | increasing | decreasing
    last_high_risk_at: datetime | None = None
    alert_count_24h: int = 0
