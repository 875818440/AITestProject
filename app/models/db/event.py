import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BehaviorEvent(Base):
    """用户行为事件（按月 Range 分区）。"""

    __tablename__ = "behavior_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # 事件分类
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False  # LOGIN | LOGOUT | ACTION | PAGE_VIEW | API_CALL
    )
    action_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 网络信息
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 设备指纹
    device_fingerprint_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_new_device: Mapped[bool | None] = mapped_column(nullable=True)

    # 地理信息
    geo_country: Mapped[str | None] = mapped_column(String(3), nullable=True)
    geo_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    geo_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    geo_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    geo_isp: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_vpn: Mapped[bool | None] = mapped_column(nullable=True)
    distance_from_home_km: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 行为详情（灵活字段）
    action_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 实时风险评分快照
    risk_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_behavior_events_user_created", "user_id", "created_at"),
        Index("ix_behavior_events_event_type", "event_type"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    def __repr__(self) -> str:
        return f"<BehaviorEvent id={self.id} user_id={self.user_id} type={self.event_type}>"
