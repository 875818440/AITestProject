import uuid
from datetime import datetime

from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    risk_score_id: uuid.UUID | None
    channels: list[str] | None
    status: str
    title: str
    message: str
    created_at: datetime
    sent_at: datetime | None
    acknowledged_at: datetime | None

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    total: int
    items: list[AlertResponse]


class AlertAcknowledge(BaseModel):
    note: str | None = None
