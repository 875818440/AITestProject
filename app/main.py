"""FastAPI 应用入口 — 生命周期、中间件、路由挂载。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.core.database import engine
from app.core.logging import get_logger, setup_logging
from app.core.redis_client import close_redis, init_redis
from app.api.v1.router import api_router

setup_logging(
    log_level="DEBUG" if settings.app_debug else "INFO",
    json_logs=settings.is_production,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- 启动 ----
    logger.info("应用启动", env=settings.app_env)
    await init_redis()
    logger.info("Redis 连接就绪")
    yield
    # ---- 关闭 ----
    await close_redis()
    await engine.dispose()
    logger.info("应用关闭，资源已释放")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="社交媒体账号被盗风险预警系统 API",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Prometheus 指标
    if settings.metrics_enabled:
        Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # 路由挂载
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["Health"])
    async def health_check():
        return {"status": "ok", "env": settings.app_env}

    return app


app = create_app()
