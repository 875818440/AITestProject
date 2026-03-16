"""Redis 异步连接池。"""
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis

from app.core.config import settings

_redis_pool: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    global _redis_pool
    _redis_pool = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=50,
    )
    return _redis_pool


async def close_redis() -> None:
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None


def get_redis() -> aioredis.Redis:
    if _redis_pool is None:
        raise RuntimeError("Redis 未初始化，请先调用 init_redis()")
    return _redis_pool


@asynccontextmanager
async def redis_client() -> AsyncGenerator[aioredis.Redis, None]:
    client = get_redis()
    try:
        yield client
    finally:
        pass  # 连接归还至连接池，无需手动关闭
