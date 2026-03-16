"""告警管理端点。"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, func

from app.api.deps import CurrentUserID, DBSession
from app.models.db.alert import Alert
from app.models.schemas.alert import AlertAcknowledge, AlertListResponse, AlertResponse

router = APIRouter()


@router.get("/", response_model=AlertListResponse)
async def list_alerts(
    db: DBSession,
    current_user_id: CurrentUserID,
    alert_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = 0,
):
    """查询当前用户的告警列表。"""
    query = select(Alert).where(Alert.user_id == current_user_id)
    count_query = select(func.count()).where(Alert.user_id == current_user_id)

    if alert_status:
        query = query.where(Alert.status == alert_status.upper())
        count_query = count_query.where(Alert.status == alert_status.upper())

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(Alert.created_at.desc()).limit(limit).offset(offset)
    )
    return AlertListResponse(total=total, items=list(result.scalars().all()))


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: uuid.UUID,
    db: DBSession,
    current_user_id: CurrentUserID,
):
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.user_id == current_user_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    return alert


@router.patch("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    payload: AlertAcknowledge,
    db: DBSession,
    current_user_id: CurrentUserID,
):
    """用户确认/处理告警。"""
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.user_id == current_user_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    if alert.status == "ACKNOWLEDGED":
        raise HTTPException(status_code=400, detail="告警已处理")

    alert.status = "ACKNOWLEDGED"
    alert.acknowledged_at = datetime.now(timezone.utc)
    if payload.note and alert.metadata_:
        alert.metadata_["acknowledge_note"] = payload.note
    elif payload.note:
        alert.metadata_ = {"acknowledge_note": payload.note}

    await db.flush()
    await db.refresh(alert)
    return alert
