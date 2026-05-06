"""送审快照包 API：只读查询。Review Bundle 不可修改（status 由系统管理）。"""

import json as _json
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import NotFoundError
from app.models.channel_package import ChannelPackage
from app.models.event_case import EventCase
from app.models.review_bundle import ReviewBundle
from app.models.story_packet import StoryPacket
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter()


# ── 响应模型 ──

class ReviewBundleResponse(BaseModel):
    id: str
    story_packet_id: str | None
    channel_package_id: str | None
    bundle_type: str
    draft_version_id: str | None
    evidence_pack_id: str | None
    claim_snapshot: dict | list | None = None
    risk_report_snapshot: dict | list | None = None
    redaction_report_snapshot: dict | list | None = None
    bundle_hash: str | None
    status: str
    submitted_by: str | None
    submit_note: str | None
    created_at: datetime | None

    @field_validator("claim_snapshot", "risk_report_snapshot", "redaction_report_snapshot", mode="before")
    @classmethod
    def _parse_snapshot(cls, v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except Exception:
                return None
        return v

    model_config = {"from_attributes": True}


class PaginatedRBResponse(BaseModel):
    items: list[ReviewBundleResponse]
    total: int
    page: int
    page_size: int


async def _get_visibility_scope(db: AsyncSession, current_user: User) -> tuple[list[str], list[str], list[str], list[str]]:
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

    visible_story_packet_ids = list((await db.execute(
        select(StoryPacket.id).where(
            (StoryPacket.owner_id.in_(visible_owner_ids)) |
            (StoryPacket.event_case_id.in_(visible_event_ids))
        )
    )).scalars().all())

    if visible_story_packet_ids:
        visible_channel_package_ids = list((await db.execute(
            select(ChannelPackage.id).where(ChannelPackage.story_packet_id.in_(visible_story_packet_ids))
        )).scalars().all())
    else:
        visible_channel_package_ids = []

    return visible_owner_ids, visible_event_ids, visible_story_packet_ids, visible_channel_package_ids


async def _assert_bundle_visible(db: AsyncSession, bundle: ReviewBundle, current_user: User):
    _, _, visible_story_packet_ids, visible_channel_package_ids = await _get_visibility_scope(db, current_user)
    visible = (
        (bundle.story_packet_id and bundle.story_packet_id in visible_story_packet_ids) or
        (bundle.channel_package_id and bundle.channel_package_id in visible_channel_package_ids)
    )
    if not visible:
        raise NotFoundError("送审快照包", str(bundle.id))


# ── 端点 ──

@router.get("", response_model=PaginatedRBResponse, summary="送审快照包列表")
async def list_review_bundles(
    story_packet_id: str | None = None,
    channel_package_id: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, _, visible_story_packet_ids, visible_channel_package_ids = await _get_visibility_scope(db, current_user)
    if not visible_story_packet_ids and not visible_channel_package_ids:
        return PaginatedRBResponse(items=[], total=0, page=page, page_size=page_size)

    query = select(ReviewBundle)
    count_query = select(func.count(ReviewBundle.id))
    base_visibility = or_(
        ReviewBundle.story_packet_id.in_(visible_story_packet_ids),
        ReviewBundle.channel_package_id.in_(visible_channel_package_ids),
    )
    query = query.where(base_visibility)
    count_query = count_query.where(base_visibility)

    if story_packet_id:
        query = query.where(ReviewBundle.story_packet_id == story_packet_id)
        count_query = count_query.where(ReviewBundle.story_packet_id == story_packet_id)
    if channel_package_id:
        query = query.where(ReviewBundle.channel_package_id == channel_package_id)
        count_query = count_query.where(ReviewBundle.channel_package_id == channel_package_id)
    if status:
        query = query.where(ReviewBundle.status == status)
        count_query = count_query.where(ReviewBundle.status == status)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(ReviewBundle.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return PaginatedRBResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{bundle_id}", response_model=ReviewBundleResponse, summary="送审快照包详情")
async def get_review_bundle(
    bundle_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bundle = await db.get(ReviewBundle, bundle_id)
    if not bundle:
        raise NotFoundError("送审快照包", bundle_id)
    await _assert_bundle_visible(db, bundle, current_user)
    return bundle
