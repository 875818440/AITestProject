"""Celery 异步告警发送任务。"""
import asyncio
import uuid
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(
    name="app.tasks.alert_tasks.send_alert_task",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def send_alert_task(
    self,
    user_id: str,
    risk_score_id: str,
    risk_score: int,
    level: str,
    triggered_rules: list[str],
) -> dict:
    try:
        return asyncio.run(
            _async_send_alert(user_id, risk_score_id, risk_score, level, triggered_rules)
        )
    except Exception as exc:
        logger.error("告警任务失败", user_id=user_id, error=str(exc))
        raise self.retry(exc=exc)


async def _async_send_alert(
    user_id: str,
    risk_score_id: str,
    risk_score: int,
    level: str,
    triggered_rules: list[str],
) -> dict:
    from app.core.database import AsyncSessionLocal
    from app.core.redis_client import init_redis, get_redis
    from app.models.db.user import User
    from app.models.db.alert import Alert
    from app.services.alert_service import dispatch_alert
    from sqlalchemy import select

    try:
        get_redis()
    except RuntimeError:
        await init_redis()

    async with AsyncSessionLocal() as db:
        user_result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        user: User | None = user_result.scalar_one_or_none()

        send_results = await dispatch_alert(
            user_id=user_id,
            risk_score=risk_score,
            level=level,
            triggered_rules=triggered_rules,
            user_email=user.email if user else None,
            user_phone=user.phone if user else None,
            fcm_token=user.fcm_token if user else None,
        )

        if send_results:
            channels = list(send_results.keys())
            alert_record = Alert(
                user_id=uuid.UUID(user_id),
                risk_score_id=uuid.UUID(risk_score_id),
                channels=channels,
                status="SENT",
                title=f"账号安全预警 — 风险评分 {risk_score}/100",
                message=f"检测到 {level} 风险，触发规则：{', '.join(triggered_rules)}",
                metadata_={"send_results": send_results},
                sent_at=datetime.now(timezone.utc),
            )
            db.add(alert_record)
            await db.commit()
            logger.info("告警记录已保存", user_id=user_id, channels=channels)

        return {"user_id": user_id, "send_results": send_results}
