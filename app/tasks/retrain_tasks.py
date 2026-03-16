"""Celery 定时模型重训练任务。"""
import asyncio
import subprocess
import sys
from pathlib import Path

from app.tasks.celery_app import celery_app
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(name="app.tasks.retrain_tasks.retrain_model_task")
def retrain_model_task(version: str | None = None) -> dict:
    """触发离线重训练脚本并将新模型注册到数据库。"""
    import time
    new_version = version or f"v{int(time.time())}"
    logger.info("开始模型重训练", version=new_version)

    result = subprocess.run(
        [
            sys.executable,
            "ml_training/train.py",
            "--epochs", "50",
            "--version", new_version,
            "--output-dir", settings.model_path,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.error("重训练失败", stderr=result.stderr[-500:])
        return {"success": False, "error": result.stderr[-200:]}

    logger.info("重训练成功", version=new_version, stdout=result.stdout[-300:])

    # 注册新模型到数据库
    asyncio.run(_register_model(new_version))
    return {"success": True, "version": new_version}


async def _register_model(version: str) -> None:
    import torch
    from pathlib import Path
    from app.core.database import AsyncSessionLocal
    from app.models.db.ml_model import MLModel
    from sqlalchemy import update

    model_path = Path(settings.model_path) / f"lstm_{version}.pt"
    if not model_path.exists():
        logger.warning("模型文件不存在，跳过注册", path=str(model_path))
        return

    checkpoint = torch.load(str(model_path), map_location="cpu", weights_only=True)
    metrics = checkpoint.get("metrics", {})

    async with AsyncSessionLocal() as db:
        # 取消旧模型的 active 状态
        await db.execute(update(MLModel).values(is_active=False))

        new_model = MLModel(
            version=version,
            file_path=str(model_path),
            val_loss=metrics.get("val_loss"),
            auc_roc=metrics.get("auc_roc"),
            f1_score=metrics.get("f1_score"),
            hyperparams=checkpoint.get("hyperparams"),
            is_active=True,
            notes="自动重训练",
        )
        db.add(new_model)
        await db.commit()
        logger.info("新模型已注册并激活", version=version)

    # 热加载新模型
    from app.ml.predictor import predictor
    predictor.load_model(version)
