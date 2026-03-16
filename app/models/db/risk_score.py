import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RiskScore(Base):
    """风险评分历史记录。"""

    __tablename__ = "risk_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # 综合评分
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    level: Mapped[str] = mapped_column(
        String(10), nullable=False  # normal | low | medium | high
    )

    # 各子分（多因子融合详情）
    lstm_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rule_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    velocity_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 触发的规则列表
    triggered_rules: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    # 模型元信息
    model_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    components: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<RiskScore user_id={self.user_id} score={self.score} level={self.level}>"
