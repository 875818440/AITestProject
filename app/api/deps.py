"""FastAPI 依赖注入：数据库会话、Redis、当前用户。"""
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.core.security import decode_access_token

bearer_scheme = HTTPBearer()

DBSession = Annotated[AsyncSession, Depends(get_db)]
Redis = Annotated[object, Depends(get_redis)]


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> uuid.UUID:
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌格式错误")


CurrentUserID = Annotated[uuid.UUID, Depends(get_current_user_id)]
