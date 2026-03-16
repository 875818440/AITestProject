"""风险评分查询端点。"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import select, func

from app.api.deps import CurrentUserID, DBSession
from app.models.db.risk_score import RiskScore
from app.models.db.alert import Alert
from app.models.schemas.risk import RiskScoreHistoryResponse, RiskScoreResponse, RiskSummary
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/{user_id}/score", response_model=RiskScoreResponse)
async def get_latest_risk_score(
    user_id: uuid.UUID,
    db: DBSession,
    current_user_id: CurrentUserID,
):
    """获取用户最新风险评分。"""
    result = await db.execute(
        select(RiskScore)
        .where(RiskScore.user_id == user_id)
        .order_by(RiskScore.created_at.desc())
        .limit(1)
    )
    score = result.scalar_one_or_none()
    if score is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="暂无风险评分记录")
    return score


@router.get("/{user_id}/history", response_model=RiskScoreHistoryResponse)
async def get_risk_score_history(
    user_id: uuid.UUID,
    db: DBSession,
    current_user_id: CurrentUserID,
    hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=100, ge=1, le=500),
):
    """获取用户近 N 小时风险评分历史。"""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    count_result = await db.execute(
        select(func.count()).where(
            RiskScore.user_id == user_id,
            RiskScore.created_at >= since,
        )
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(RiskScore)
        .where(RiskScore.user_id == user_id, RiskScore.created_at >= since)
        .order_by(RiskScore.created_at.desc())
        .limit(limit)
    )
    scores = result.scalars().all()
    return RiskScoreHistoryResponse(user_id=user_id, total=total, items=list(scores))


@router.get("/{user_id}/summary", response_model=RiskSummary)
async def get_risk_summary(
    user_id: uuid.UUID,
    db: DBSession,
    current_user_id: CurrentUserID,
):
    """获取用户风险状态摘要（当前评分 + 趋势 + 24h 告警数）。"""
    # 最新 2 条评分用于计算趋势
    result = await db.execute(
        select(RiskScore)
        .where(RiskScore.user_id == user_id)
        .order_by(RiskScore.created_at.desc())
        .limit(2)
    )
    scores = result.scalars().all()

    current_score = scores[0].score if scores else 0
    current_level = scores[0].level if scores else "normal"

    if len(scores) >= 2:
        diff = scores[0].score - scores[1].score
        trend = "increasing" if diff > 5 else ("decreasing" if diff < -5 else "stable")
    else:
        trend = "stable"

    # 24h 告警数
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    alert_count_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == user_id,
            Alert.created_at >= since_24h,
        )
    )
    alert_count_24h = alert_count_result.scalar_one()

    # 最近一次高风险时间
    high_risk_result = await db.execute(
        select(RiskScore.created_at)
        .where(RiskScore.user_id == user_id, RiskScore.level == "high")
        .order_by(RiskScore.created_at.desc())
        .limit(1)
    )
    last_high_risk_at = high_risk_result.scalar_one_or_none()

    return RiskSummary(
        user_id=user_id,
        current_score=current_score,
        current_level=current_level,
        trend=trend,
        last_high_risk_at=last_high_risk_at,
        alert_count_24h=alert_count_24h,
    )
