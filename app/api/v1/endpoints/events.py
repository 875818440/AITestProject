"""行为事件上报端点。"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, status
from sqlalchemy import select, func

from app.api.deps import CurrentUserID, DBSession
from app.models.db.event import BehaviorEvent
from app.models.schemas.event import EventCreate, EventListResponse, EventResponse
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventCreate,
    background_tasks: BackgroundTasks,
    db: DBSession,
    current_user_id: CurrentUserID,
):
    """上报用户行为事件，异步触发风险评分。"""
    event = BehaviorEvent(
        user_id=payload.user_id,
        session_id=payload.session_id,
        event_type=payload.event_type,
        action_type=payload.action_type,
        ip_address=str(payload.ip_address) if payload.ip_address else None,
        user_agent=payload.device_info.user_agent if payload.device_info else None,
        action_data=payload.action_data,
        duration_ms=payload.duration_ms,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)

    # 异步触发风险评分（不阻塞响应）
    background_tasks.add_task(_trigger_risk_scoring, str(event.id), str(payload.user_id))

    logger.info("行为事件已记录", event_id=str(event.id), event_type=payload.event_type)
    return event


@router.get("/{user_id}", response_model=EventListResponse)
async def list_user_events(
    user_id: uuid.UUID,
    db: DBSession,
    current_user_id: CurrentUserID,
    limit: int = 50,
    offset: int = 0,
):
    count_result = await db.execute(
        select(func.count()).where(BehaviorEvent.user_id == user_id)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(BehaviorEvent)
        .where(BehaviorEvent.user_id == user_id)
        .order_by(BehaviorEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    events = result.scalars().all()
    return EventListResponse(total=total, items=list(events))


async def _trigger_risk_scoring(event_id: str, user_id: str) -> None:
    """后台任务：将评分任务推送到 Celery 队列。"""
    try:
        from app.tasks.score_tasks import compute_risk_score_task
        compute_risk_score_task.delay(user_id, event_id)
    except Exception as exc:
        logger.error("触发风险评分失败", event_id=event_id, error=str(exc))
