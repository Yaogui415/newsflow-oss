"""证据包 API：CRUD。"""

import json as _json

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import NotFoundError
from app.models.evidence_pack import EvidencePack
from app.models.event_case import EventCase
from app.models.story_packet import StoryPacket
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter()


# ── 请求/响应模型 ──

class EvidencePackCreate(BaseModel):
    story_packet_id: str
    sources: list = []
    citation_anchors: list = []
    completeness_score: float | None = None


class EvidencePackUpdate(BaseModel):
    sources: list | None = None
    citation_anchors: list | None = None
    completeness_score: float | None = None


class EvidencePackResponse(BaseModel):
    id: str
    story_packet_id: str
    version: int
    sources: list
    citation_anchors: list
    completeness_score: float | None
    is_snapshot: bool
    snapshot_of_id: str | None
    created_by: str | None
    created_at: datetime | None

    @field_validator("sources", "citation_anchors", mode="before")
    @classmethod
    def _parse_list(cls, v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except Exception:
                return []
        return v if v is not None else []

    model_config = {"from_attributes": True}


class PaginatedEPResponse(BaseModel):
    items: list[EvidencePackResponse]
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

    return list((await db.execute(
        select(StoryPacket.id).where(
            (StoryPacket.owner_id.in_(visible_owner_ids)) |
            (StoryPacket.event_case_id.in_(visible_event_ids))
        )
    )).scalars().all())


async def _assert_pack_visible(db: AsyncSession, pack: EvidencePack, current_user: User):
    visible_story_packet_ids = await _get_visible_story_packet_ids(db, current_user)
    if pack.story_packet_id not in visible_story_packet_ids:
        raise NotFoundError("证据包", str(pack.id))


# ── 端点 ──

@router.get("", response_model=PaginatedEPResponse, summary="证据包列表")
async def list_evidence_packs(
    story_packet_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    visible_story_packet_ids = await _get_visible_story_packet_ids(db, current_user)
    if not visible_story_packet_ids:
        return PaginatedEPResponse(items=[], total=0, page=page, page_size=page_size)

    query = select(EvidencePack)
    count_query = select(func.count(EvidencePack.id))
    query = query.where(EvidencePack.story_packet_id.in_(visible_story_packet_ids))
    count_query = count_query.where(EvidencePack.story_packet_id.in_(visible_story_packet_ids))

    if story_packet_id:
        query = query.where(EvidencePack.story_packet_id == story_packet_id)
        count_query = count_query.where(EvidencePack.story_packet_id == story_packet_id)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(EvidencePack.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return PaginatedEPResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=EvidencePackResponse, summary="创建证据包")
async def create_evidence_pack(
    req: EvidencePackCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    packet = await db.get(StoryPacket, req.story_packet_id)
    if not packet:
        raise NotFoundError("报道任务包", str(req.story_packet_id))
    visible_story_packet_ids = await _get_visible_story_packet_ids(db, current_user)
    if req.story_packet_id not in visible_story_packet_ids:
        raise NotFoundError("报道任务包", str(req.story_packet_id))

    pack = EvidencePack(
        story_packet_id=req.story_packet_id,
        sources=req.sources,
        citation_anchors=req.citation_anchors,
        completeness_score=req.completeness_score,
        created_by=current_user.id,
    )
    db.add(pack)
    await db.flush()
    await db.refresh(pack)
    return pack


@router.get("/{pack_id}", response_model=EvidencePackResponse, summary="证据包详情")
async def get_evidence_pack(
    pack_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pack = await db.get(EvidencePack, pack_id)
    if not pack:
        raise NotFoundError("证据包", pack_id)
    await _assert_pack_visible(db, pack, current_user)
    return pack


@router.patch("/{pack_id}", response_model=EvidencePackResponse, summary="更新证据包")
async def update_evidence_pack(
    pack_id: str,
    req: EvidencePackUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pack = await db.get(EvidencePack, pack_id)
    if not pack:
        raise NotFoundError("证据包", pack_id)
    await _assert_pack_visible(db, pack, current_user)

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(pack, field, value)

    await db.flush()
    await db.refresh(pack)
    return pack


@router.post("/{pack_id}/snapshot", response_model=EvidencePackResponse, summary="创建证据包快照")
async def snapshot_evidence_pack(
    pack_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pack = await db.get(EvidencePack, pack_id)
    if not pack:
        raise NotFoundError("证据包", pack_id)
    await _assert_pack_visible(db, pack, current_user)

    snapshot = EvidencePack(
        story_packet_id=pack.story_packet_id,
        version=pack.version,
        sources=pack.sources,
        citation_anchors=pack.citation_anchors,
        completeness_score=pack.completeness_score,
        is_snapshot=True,
        snapshot_of_id=pack.id,
        created_by=current_user.id,
    )
    db.add(snapshot)
    await db.flush()
    await db.refresh(snapshot)
    return snapshot


@router.delete("/{pack_id}", response_model=dict, summary="删除证据包")
async def delete_evidence_pack(
    pack_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pack = await db.get(EvidencePack, pack_id)
    if not pack:
        raise NotFoundError("证据包", pack_id)
    await _assert_pack_visible(db, pack, current_user)
    await db.delete(pack)
    await db.flush()
    return {"message": "已删除", "id": pack_id}
