"""API 公共依赖注入。"""

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.core.errors import UnauthorizedError, ForbiddenError
from app.models.user import User


async def get_current_user(
    authorization: str = Header(..., description="Bearer <token>"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 JWT Token 解析当前登录用户。"""
    if not authorization.startswith("Bearer "):
        raise UnauthorizedError("无效的认证头")
    token = authorization[7:]
    payload = decode_access_token(token)
    if payload is None:
        raise UnauthorizedError("Token 无效或已过期")
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError()
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("用户不存在或已禁用")
    return user


def require_roles(*allowed_roles: str):
    """角色权限检查依赖工厂。"""
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if not any(role in current_user.roles for role in allowed_roles):
            raise ForbiddenError(f"需要以下角色之一：{', '.join(allowed_roles)}")
        return current_user
    return checker
