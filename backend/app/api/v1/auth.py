"""认证相关 API：登录、注册、获取当前用户信息。"""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.core.errors import AppError, UnauthorizedError
from app.models.user import User
from app.models.organization import Organization
from app.api.deps import get_current_user
from app.services.user_llm_settings import user_llm_settings_service

router = APIRouter()


# ── 请求/响应模型 ──

class RegisterRequest(BaseModel):
    username: str
    display_name: str
    email: EmailStr
    password: str
    roles: list[str] = ["reporter"]
    desk: str | None = None
    org_name: str | None = None
    invite_code: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: UUID
    username: str
    display_name: str
    email: str
    roles: list[str]
    desk: str | None
    org_id: str | None = None
    org_name: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class UserLLMSettingsRequest(BaseModel):
    api_key: str
    daily_budget_usd: float | None = None
    model_preference: str | None = None
    provider: str = "openai"


class UserLLMSettingsResponse(BaseModel):
    user_id: str
    provider: str
    has_api_key: bool
    api_key_masked: str | None
    daily_budget_usd: float | None
    model_preference: str | None
    updated_at: str | None


# ── 接口 ──

@router.post("/register", response_model=UserResponse, summary="注册新用户")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.username == req.username))
    if existing.scalar_one_or_none():
        raise AppError("USER_EXISTS", "用户名已存在")

    org_id = None
    org_display_name = None

    # 创建新团队
    if req.org_name:
        org_exist = await db.execute(select(Organization).where(Organization.name == req.org_name))
        if org_exist.scalar_one_or_none():
            raise AppError("ORG_EXISTS", "团队名称已存在")

    # 通过邀请码加入团队
    if req.invite_code:
        org_result = await db.execute(
            select(Organization).where(Organization.invite_code == req.invite_code.strip().upper())
        )
        org = org_result.scalar_one_or_none()
        if not org:
            raise AppError("INVALID_INVITE", "邀请码无效")
        org_id = org.id
        org_display_name = org.display_name

    user = User(
        username=req.username,
        display_name=req.display_name,
        email=req.email,
        hashed_password=hash_password(req.password),
        roles=req.roles if not req.org_name else ["chief_editor", "admin"],
        desk=req.desk,
        org_id=org_id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    # 如果创建新团队
    if req.org_name and not req.invite_code:
        org = Organization(
            name=req.org_name,
            display_name=req.org_name,
            owner_id=user.id,
        )
        db.add(org)
        await db.flush()
        await db.refresh(org)
        user.org_id = org.id
        org_id = org.id
        org_display_name = org.display_name
        await db.flush()

    resp = UserResponse.model_validate(user)
    resp.org_name = org_display_name
    return resp


@router.post("/login", response_model=TokenResponse, summary="用户登录")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise UnauthorizedError("用户名或密码错误")
    if not user.is_active:
        raise UnauthorizedError("用户已被禁用")
    token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/me/llm-settings", response_model=UserLLMSettingsResponse, summary="获取当前用户 API Key 配置")
async def get_my_llm_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await user_llm_settings_service.get_user_setting(db, user_id=current_user.id)
    return UserLLMSettingsResponse(**data)


@router.put("/me/llm-settings", response_model=UserLLMSettingsResponse, summary="更新当前用户 API Key 配置")
async def update_my_llm_settings(
    req: UserLLMSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not req.api_key.strip():
        raise AppError("INVALID_API_KEY", "API Key 不能为空")

    data = await user_llm_settings_service.upsert_user_setting(
        db,
        user_id=current_user.id,
        api_key=req.api_key.strip(),
        daily_budget_usd=req.daily_budget_usd,
        model_preference=req.model_preference,
        provider=req.provider,
    )
    return UserLLMSettingsResponse(**data)


@router.delete("/me/llm-settings", summary="清空当前用户 API Key 配置")
async def clear_my_llm_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await user_llm_settings_service.clear_user_setting(db, user_id=current_user.id)
    return {"success": True}
