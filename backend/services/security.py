# JWT 鉴权依赖 + 成本追踪用 contextvar
from typing import Optional
import contextvars
import jwt
from fastapi import Header, HTTPException
from config.settings import settings

# 成本追踪用 contextvar（后续模块使用）
_tracking_ctx: contextvars.ContextVar = contextvars.ContextVar('tracking', default=None)

__all__ = ["get_current_user", "_tracking_ctx"]


async def get_current_user(authorization: Optional[str] = Header(None)) -> str:
    """从 Authorization: Bearer <token> 解析 JWT，返回 user_id

    同时设置 _tracking_ctx，供后续 LLM 成本追踪回调使用。
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            raise ValueError("Not a Bearer token")
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = str(payload["user_id"])
        _tracking_ctx.set({"user_id": user_id, "session_id": None, "node_type": None})
        return user_id
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
