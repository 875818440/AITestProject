import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, IPvAnyAddress


class DeviceInfo(BaseModel):
    user_agent: str | None = None
    screen_resolution: str | None = None
    timezone: str | None = None
    language: str | None = None
    canvas_hash: str | None = None
    webgl_hash: str | None = None
    platform: str | None = None


class EventCreate(BaseModel):
    """客户端上报行为事件。"""

    user_id: uuid.UUID
    session_id: uuid.UUID | None = None
    event_type: Annotated[str, Field(pattern=r"^(LOGIN|LOGOUT|ACTION|PAGE_VIEW|API_CALL)$")]
    action_type: str | None = None
    ip_address: str | None = None
    device_info: DeviceInfo | None = None
    action_data: dict | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    timestamp: datetime | None = None  # 客户端时间戳（可选）


class EventResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    event_type: str
    risk_score: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    total: int
    items: list[EventResponse]
