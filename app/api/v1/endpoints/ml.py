"""ML 模型管理端点：版本列表、触发重训练。"""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from pydantic import BaseModel

from app.api.deps import CurrentUserID, DBSession
from app.models.db.ml_model import MLModel

router = APIRouter()


class MLModelInfo(BaseModel):
    id: str
    version: str
    model_type: str
    is_active: bool
    auc_roc: float | None
    f1_score: float | None
    train_samples: int | None
    trained_at: str

    model_config = {"from_attributes": True}


@router.get("/models", response_model=list[MLModelInfo])
async def list_models(db: DBSession, current_user_id: CurrentUserID):
    """查询所有已注册的 ML 模型版本。"""
    result = await db.execute(
        select(MLModel).order_by(MLModel.trained_at.desc())
    )
    models = result.scalars().all()
    return [
        MLModelInfo(
            id=str(m.id),
            version=m.version,
            model_type=m.model_type,
            is_active=m.is_active,
            auc_roc=m.auc_roc,
            f1_score=m.f1_score,
            train_samples=m.train_samples,
            trained_at=m.trained_at.isoformat(),
        )
        for m in models
    ]


@router.post("/retrain", status_code=status.HTTP_202_ACCEPTED)
async def trigger_retrain(current_user_id: CurrentUserID):
    """异步触发模型重训练任务。"""
    try:
        from app.tasks.retrain_tasks import retrain_model_task
        task = retrain_model_task.delay()
        return {"message": "重训练任务已提交", "task_id": task.id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"任务提交失败: {exc}")
