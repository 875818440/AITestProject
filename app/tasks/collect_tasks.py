"""数据采集辅助任务：清理过期事件。"""
from datetime import datetime, timedelta, timezone

from app.tasks.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(name="app.tasks.collect_tasks.cleanup_old_events_task")
def cleanup_old_events_task(retain_days: int = 90) -> dict:
    """清理超过保留天数的行为事件（通常由分区表自动管理，此为补充）。"""
    import asyncio
    return asyncio.run(_async_cleanup(retain_days))


async def _async_cleanup(retain_days: int) -> dict:
    from sqlalchemy import delete
    from app.core.database import AsyncSessionLocal
    from app.models.db.event import BehaviorEvent

    cutoff = datetime.now(timezone.utc) - timedelta(days=retain_days)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(BehaviorEvent).where(BehaviorEvent.created_at < cutoff)
        )
        await db.commit()
        deleted = result.rowcount
        logger.info("过期事件清理完成", deleted_count=deleted, cutoff=cutoff.isoformat())
        return {"deleted": deleted, "cutoff": cutoff.isoformat()}
