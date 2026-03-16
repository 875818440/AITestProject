"""Celery 异步风险评分任务。

流程：
  1. 从 DB 读取事件 + 用户信息
  2. 调用 GeoIP 服务解析 IP
  3. 更新特征序列（Redis）
  4. 调用风险评分引擎
  5. 将评分写入 DB（risk_scores 表）
  6. 若超阈值，触发告警任务
"""
import asyncio
import uuid
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(
    name="app.tasks.score_tasks.compute_risk_score_task",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def compute_risk_score_task(self, user_id: str, event_id: str) -> dict:
    """异步计算风险评分并持久化结果。"""
    try:
        return asyncio.run(_async_compute_risk_score(user_id, event_id))
    except Exception as exc:
        logger.error("风险评分任务失败", user_id=user_id, event_id=event_id, error=str(exc))
        raise self.retry(exc=exc)


async def _async_compute_risk_score(user_id: str, event_id: str) -> dict:
    from app.core.database import AsyncSessionLocal
    from app.core.redis_client import init_redis, get_redis
    from app.models.db.event import BehaviorEvent
    from app.models.db.risk_score import RiskScore
    from app.models.db.user import User
    from app.models.db.alert import Alert
    from app.services.ip_geo_service import geo_service
    from app.services.feature_engineering import (
        vectorize_event,
        push_event_to_sequence,
        compute_device_fingerprint,
    )
    from app.services.risk_engine import compute_risk_score
    from app.services.alert_service import dispatch_alert
    from sqlalchemy import select

    # 确保 Redis 已连接（Celery worker 中需重新初始化）
    try:
        get_redis()
    except RuntimeError:
        await init_redis()

    async with AsyncSessionLocal() as db:
        # 查询事件
        event_result = await db.execute(
            select(BehaviorEvent).where(BehaviorEvent.id == uuid.UUID(event_id))
        )
        event: BehaviorEvent | None = event_result.scalar_one_or_none()
        if not event:
            logger.warning("事件不存在", event_id=event_id)
            return {"error": "event_not_found"}

        # 查询用户
        user_result = await db.execute(
            select(User).where(User.id == uuid.UUID(user_id))
        )
        user: User | None = user_result.scalar_one_or_none()

        # GeoIP 解析
        geo = None
        distance_km = None
        if event.ip_address:
            geo = await geo_service.lookup(str(event.ip_address))
            if user and user.home_country:
                # 若有常驻地经纬度（此处简化，实际可存到用户表）
                distance_km = geo_service.distance_from_home(geo, None, None)

        # 特征向量化 + 推入 Redis 序列
        from app.services.feature_engineering import FEATURE_DIM
        feat_vec = vectorize_event(
            event_type=event.event_type,
            created_at=event.created_at,
            geo=geo,
            is_new_device=bool(event.is_new_device),
            is_vpn=bool(event.is_vpn),
            distance_from_home_km=distance_km,
            duration_ms=event.duration_ms,
            interval_from_last_s=None,
        )
        await push_event_to_sequence(user_id, feat_vec)

        # 风险评分
        components = await compute_risk_score(
            user_id=user_id,
            event_type=event.event_type,
            geo=geo,
            is_new_device=bool(event.is_new_device),
            is_vpn=bool(event.is_vpn),
            distance_from_home_km=distance_km,
            home_country=user.home_country if user else None,
        )

        # 写入 risk_scores 表
        risk_record = RiskScore(
            user_id=uuid.UUID(user_id),
            event_id=uuid.UUID(event_id),
            score=components.final_score,
            level=components.level,
            lstm_score=components.lstm_prob,
            rule_score=components.rule_prob,
            velocity_score=components.velocity_prob,
            triggered_rules=components.triggered_rules,
            model_version=components.attention_weights and "v1" or None,
            components={
                "lstm": components.lstm_prob,
                "rule": components.rule_prob,
                "velocity": components.velocity_prob,
            },
        )
        db.add(risk_record)

        # 更新事件中的风险快照
        event.risk_score = components.final_score
        if geo:
            event.geo_country = geo.country_code
            event.geo_city = geo.city
            event.geo_lat = geo.lat
            event.geo_lng = geo.lng
            event.geo_isp = geo.isp
            event.is_vpn = geo.is_vpn
            event.distance_from_home_km = distance_km

        await db.flush()
        await db.refresh(risk_record)

        # 超阈值则触发告警
        if components.level in ("medium", "high"):
            from app.tasks.alert_tasks import send_alert_task
            send_alert_task.delay(
                user_id=user_id,
                risk_score_id=str(risk_record.id),
                risk_score=components.final_score,
                level=components.level,
                triggered_rules=components.triggered_rules,
            )

        await db.commit()
        logger.info(
            "风险评分完成",
            user_id=user_id,
            score=components.final_score,
            level=components.level,
        )
        return {
            "user_id": user_id,
            "score": components.final_score,
            "level": components.level,
            "risk_score_id": str(risk_record.id),
        }
