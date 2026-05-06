"""渠道发布包 API：CRUD + 状态操作。"""

import json as _json

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import NotFoundError
from app.core.state_machine import channel_package_engine
from app.models.channel_package import ChannelPackage
from app.models.event_case import EventCase
from app.models.story_packet import StoryPacket
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter()


# ── 请求/响应模型 ──

class ChannelPackageCreate(BaseModel):
    story_packet_id: str
    source_draft_id: str
    channel_type: str
    content: dict = {}
    drift_threshold: float = 0.30


class ChannelPackageUpdate(BaseModel):
    content: dict | None = None
    drift_score: float | None = None
    drift_threshold: float | None = None
    platform_rules_check: dict | None = None
    published_url: str | None = None


class TransitionRequest(BaseModel):
    target_state: str


class ChannelPackageResponse(BaseModel):
    id: str
    story_packet_id: str
    source_draft_id: str
    channel_type: str
    status: str
    content: dict
    drift_score: float | None
    drift_threshold: float
    platform_rules_check: dict | None = None
    published_at: datetime | None
    published_url: str | None
    owner_id: str | None
    created_at: datetime | None
    updated_at: datetime | None

    @field_validator("content", "platform_rules_check", mode="before")
    @classmethod
    def _parse_dict(cls, v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except Exception:
                return {}
        return v if v is not None else {}

    model_config = {"from_attributes": True}


class PaginatedCPResponse(BaseModel):
    items: list[ChannelPackageResponse]
    total: int
    page: int
    page_size: int


async def _get_visible_story_packet_ids(db: AsyncSession, current_user: User) -> list[str]:
    if current_user.org_id:
        visible_owner_ids = list((await db.execute(
            select(User.id).where(User.org_id == current_user.org_id)
        )).scalars().all())
        if not visible_owner_ids:
            visible_owner_ids = [current_user.id]
    else:
        visible_owner_ids = [current_user.id]

    visible_event_ids = list((await db.execute(
        select(EventCase.id).where(EventCase.owner_id.in_(visible_owner_ids))
    )).scalars().all())

    story_packet_ids = list((await db.execute(
        select(StoryPacket.id).where(
            (StoryPacket.owner_id.in_(visible_owner_ids)) |
            (StoryPacket.event_case_id.in_(visible_event_ids))
        )
    )).scalars().all())
    return story_packet_ids


async def _assert_channel_package_visible(db: AsyncSession, pkg: ChannelPackage, current_user: User):
    visible_story_packet_ids = await _get_visible_story_packet_ids(db, current_user)
    if pkg.story_packet_id not in visible_story_packet_ids:
        raise NotFoundError("渠道包", str(pkg.id))


# ── 端点 ──

@router.get("", response_model=PaginatedCPResponse, summary="渠道包列表")
async def list_channel_packages(
    story_packet_id: str | None = None,
    channel_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    visible_story_packet_ids = await _get_visible_story_packet_ids(db, current_user)
    if not visible_story_packet_ids:
        return PaginatedCPResponse(items=[], total=0, page=page, page_size=page_size)

    query = select(ChannelPackage)
    count_query = select(func.count(ChannelPackage.id))
    query = query.where(ChannelPackage.story_packet_id.in_(visible_story_packet_ids))
    count_query = count_query.where(ChannelPackage.story_packet_id.in_(visible_story_packet_ids))

    if story_packet_id:
        query = query.where(ChannelPackage.story_packet_id == story_packet_id)
        count_query = count_query.where(ChannelPackage.story_packet_id == story_packet_id)
    if channel_type:
        query = query.where(ChannelPackage.channel_type == channel_type)
        count_query = count_query.where(ChannelPackage.channel_type == channel_type)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(ChannelPackage.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return PaginatedCPResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=ChannelPackageResponse, summary="创建渠道包")
async def create_channel_package(
    req: ChannelPackageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pkg = ChannelPackage(
        story_packet_id=req.story_packet_id,
        source_draft_id=req.source_draft_id,
        channel_type=req.channel_type,
        content=req.content,
        drift_threshold=req.drift_threshold,
        owner_id=current_user.id,
    )
    db.add(pkg)
    await db.flush()
    await db.refresh(pkg)
    return pkg


@router.get("/{pkg_id}", response_model=ChannelPackageResponse, summary="渠道包详情")
async def get_channel_package(
    pkg_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pkg = await db.get(ChannelPackage, pkg_id)
    if not pkg:
        raise NotFoundError("渠道包", pkg_id)
    await _assert_channel_package_visible(db, pkg, current_user)
    return pkg


@router.patch("/{pkg_id}", response_model=ChannelPackageResponse, summary="更新渠道包")
async def update_channel_package(
    pkg_id: str,
    req: ChannelPackageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pkg = await db.get(ChannelPackage, pkg_id)
    if not pkg:
        raise NotFoundError("渠道包", pkg_id)
    await _assert_channel_package_visible(db, pkg, current_user)

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(pkg, field, value)

    await db.flush()
    await db.refresh(pkg)
    return pkg


@router.post("/{pkg_id}/transition", response_model=ChannelPackageResponse, summary="渠道包状态迁移")
async def transition_channel_package(
    pkg_id: str,
    req: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pkg = await db.get(ChannelPackage, pkg_id)
    if not pkg:
        raise NotFoundError("渠道包", pkg_id)
    await _assert_channel_package_visible(db, pkg, current_user)

    await channel_package_engine.attempt_transition(
        obj=pkg,
        target_state=req.target_state,
        actor=current_user,
        db=db,
    )

    await db.flush()
    await db.refresh(pkg)
    return pkg
