"""Celery 应用初始化。"""
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "risk_warning",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.score_tasks",
        "app.tasks.alert_tasks",
        "app.tasks.retrain_tasks",
        "app.tasks.collect_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # 定时任务（Beat 调度）
    beat_schedule={
        "weekly-model-retrain": {
            "task": "app.tasks.retrain_tasks.retrain_model_task",
            "schedule": 604800.0,  # 每 7 天
        },
        "daily-data-cleanup": {
            "task": "app.tasks.collect_tasks.cleanup_old_events_task",
            "schedule": 86400.0,  # 每天
        },
    },
)
