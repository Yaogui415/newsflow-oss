"""组织/团队管理 API：创建团队、邀请成员、成员列表、团队设置。"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import AppError
from app.models.user import User
from app.models.organization import Organization
from app.api.deps import get_current_user

router = APIRouter()


# ── 请求/响应模型 ──

class CreateOrgRequest(BaseModel):
    name: str
    display_name: str
    description: str | None = None


class JoinOrgRequest(BaseModel):
    invite_code: str


class UpdateOrgRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None


class OrgMemberResponse(BaseModel):
    id: str
    username: str
    display_name: str
    email: str
    roles: list[str] | str
    desk: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class OrgResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: str | None
    owner_id: str
    invite_code: str
    max_members: int
    member_count: int = 0
    created_at: datetime | None

    model_config = {"from_attributes": True}


# ── 接口 ──

@router.post("", response_model=OrgResponse, summary="创建新团队")
async def create_org(
    req: CreateOrgRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = await db.execute(select(Organization).where(Organization.name == req.name))
    if existing.scalar_one_or_none():
        raise AppError("ORG_EXISTS", "团队名称已存在")

    org = Organization(
        name=req.name,
        display_name=req.display_name,
        description=req.description,
        owner_id=current_user.id,
    )
    db.add(org)
    await db.flush()
    await db.refresh(org)

    # 把创建者加入该组织
    current_user.org_id = org.id
    await db.flush()

    return OrgResponse(
        id=org.id, name=org.name, display_name=org.display_name,
        description=org.description, owner_id=org.owner_id,
        invite_code=org.invite_code, max_members=org.max_members,
        member_count=1, created_at=org.created_at,
    )


@router.post("/join", summary="通过邀请码加入团队")
async def join_org(
    req: JoinOrgRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Organization).where(Organization.invite_code == req.invite_code.strip().upper())
    )
    org = result.scalar_one_or_none()
    if not org:
        raise AppError("INVALID_INVITE", "邀请码无效")

    # 检查成员数
    count_result = await db.execute(
        select(func.count()).select_from(User).where(User.org_id == org.id)
    )
    count = count_result.scalar() or 0
    if count >= org.max_members:
        raise AppError("ORG_FULL", "团队成员已满")

    current_user.org_id = org.id
    await db.flush()
    return {"success": True, "org_name": org.display_name, "message": f"已加入团队「{org.display_name}」"}


@router.get("/my", response_model=OrgResponse | None, summary="获取当前用户所属团队")
async def get_my_org(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.org_id:
        return None
    result = await db.execute(select(Organization).where(Organization.id == current_user.org_id))
    org = result.scalar_one_or_none()
    if not org:
        return None

    count_result = await db.execute(
        select(func.count()).select_from(User).where(User.org_id == org.id)
    )
    count = count_result.scalar() or 0

    return OrgResponse(
        id=org.id, name=org.name, display_name=org.display_name,
        description=org.description, owner_id=org.owner_id,
        invite_code=org.invite_code, max_members=org.max_members,
        member_count=count, created_at=org.created_at,
    )


@router.get("/my/members", response_model=list[OrgMemberResponse], summary="获取团队成员列表")
async def list_org_members(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.org_id:
        raise AppError("NO_ORG", "你尚未加入任何团队")
    result = await db.execute(
        select(User).where(User.org_id == current_user.org_id).order_by(User.created_at)
    )
    return list(result.scalars().all())


@router.put("/my", response_model=OrgResponse, summary="更新团队信息（仅团队创建者）")
async def update_org(
    req: UpdateOrgRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.org_id:
        raise AppError("NO_ORG", "你尚未加入任何团队")
    result = await db.execute(select(Organization).where(Organization.id == current_user.org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise AppError("ORG_NOT_FOUND", "团队不存在")
    if org.owner_id != current_user.id:
        raise AppError("NOT_OWNER", "仅团队创建者可修改团队信息")

    if req.display_name is not None:
        org.display_name = req.display_name
    if req.description is not None:
        org.description = req.description
    await db.flush()
    await db.refresh(org)

    count_result = await db.execute(
        select(func.count()).select_from(User).where(User.org_id == org.id)
    )
    count = count_result.scalar() or 0

    return OrgResponse(
        id=org.id, name=org.name, display_name=org.display_name,
        description=org.description, owner_id=org.owner_id,
        invite_code=org.invite_code, max_members=org.max_members,
        member_count=count, created_at=org.created_at,
    )


@router.post("/my/regenerate-invite", summary="重新生成邀请码（仅团队创建者）")
async def regenerate_invite(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.org_id:
        raise AppError("NO_ORG", "你尚未加入任何团队")
    result = await db.execute(select(Organization).where(Organization.id == current_user.org_id))
    org = result.scalar_one_or_none()
    if not org or org.owner_id != current_user.id:
        raise AppError("NOT_OWNER", "仅团队创建者可重新生成邀请码")

    org.invite_code = uuid.uuid4().hex[:8].upper()
    await db.flush()
    return {"invite_code": org.invite_code}


@router.delete("/my/members/{user_id}", summary="移除团队成员（仅团队创建者）")
async def remove_member(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.org_id:
        raise AppError("NO_ORG", "你尚未加入任何团队")
    result = await db.execute(select(Organization).where(Organization.id == current_user.org_id))
    org = result.scalar_one_or_none()
    if not org or org.owner_id != current_user.id:
        raise AppError("NOT_OWNER", "仅团队创建者可移除成员")
    if user_id == current_user.id:
        raise AppError("CANNOT_REMOVE_SELF", "不能移除自己")

    target = await db.execute(select(User).where(User.id == user_id, User.org_id == org.id))
    user = target.scalar_one_or_none()
    if not user:
        raise AppError("USER_NOT_FOUND", "该成员不存在于此团队")
    user.org_id = None
    await db.flush()
    return {"success": True}


@router.post("/my/leave", summary="退出当前团队")
async def leave_org(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.org_id:
        raise AppError("NO_ORG", "你尚未加入任何团队")
    # 团队创建者不能退出
    result = await db.execute(select(Organization).where(Organization.id == current_user.org_id))
    org = result.scalar_one_or_none()
    if org and org.owner_id == current_user.id:
        raise AppError("OWNER_CANNOT_LEAVE", "团队创建者不能退出，请先转让所有权或解散团队")
    current_user.org_id = None
    await db.flush()
    return {"success": True}
