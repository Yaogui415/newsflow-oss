"""事实卡 API：独立 CRUD（补充 story_packets 下的嵌套列表端点）。"""

import json as _json
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import NotFoundError
from app.models.claim_card import ClaimCard
from app.models.event_case import EventCase
from app.models.story_packet import StoryPacket
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter()


# ── 请求/响应模型 ──

class ClaimCardCreate(BaseModel):
    story_packet_id: str
    claim_text: str
    risk_level: str = "L0"
    status: str = "unverified"
    supporting_evidence: list = []
    contradicting_evidence: list = []
    missing_evidence: list = []
    confidence_score: float | None = None
    draft_anchor_ref: str | None = None


class ClaimCardUpdate(BaseModel):
    claim_text: str | None = None
    risk_level: str | None = None
    status: str | None = None
    supporting_evidence: list | None = None
    contradicting_evidence: list | None = None
    missing_evidence: list | None = None
    confidence_score: float | None = None
    manual_accept_reason: str | None = None
    draft_anchor_ref: str | None = None


class ClaimCardResponse(BaseModel):
    id: str
    story_packet_id: str
    claim_text: str
    risk_level: str
    status: str
    supporting_evidence: list
    contradicting_evidence: list
    missing_evidence: list
    confidence_score: float | None
    manual_accept_reason: str | None
    draft_anchor_ref: str | None
    verified_by: str | None
    created_at: datetime | None
    updated_at: datetime | None

    @field_validator("supporting_evidence", "contradicting_evidence", "missing_evidence", mode="before")
    @classmethod
    def _parse_list(cls, v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except Exception:
                return []
        return v if v is not None else []

    model_config = {"from_attributes": True}


class PaginatedCCResponse(BaseModel):
    items: list[ClaimCardResponse]
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


async def _assert_claim_visible(db: AsyncSession, card: ClaimCard, current_user: User):
    visible_story_packet_ids = await _get_visible_story_packet_ids(db, current_user)
    if card.story_packet_id not in visible_story_packet_ids:
        raise NotFoundError("事实卡", str(card.id))


# ── 端点 ──

@router.get("", response_model=PaginatedCCResponse, summary="事实卡列表")
async def list_claim_cards(
    story_packet_id: str | None = None,
    risk_level: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    visible_story_packet_ids = await _get_visible_story_packet_ids(db, current_user)
    if not visible_story_packet_ids:
        return PaginatedCCResponse(items=[], total=0, page=page, page_size=page_size)

    query = select(ClaimCard).where(ClaimCard.status != "archived")
    count_query = select(func.count(ClaimCard.id)).where(ClaimCard.status != "archived")
    query = query.where(ClaimCard.story_packet_id.in_(visible_story_packet_ids))
    count_query = count_query.where(ClaimCard.story_packet_id.in_(visible_story_packet_ids))

    if story_packet_id:
        query = query.where(ClaimCard.story_packet_id == story_packet_id)
        count_query = count_query.where(ClaimCard.story_packet_id == story_packet_id)
    if risk_level:
        levels = [l.strip() for l in risk_level.split(",") if l.strip()]
        if levels:
            query = query.where(ClaimCard.risk_level.in_(levels))
            count_query = count_query.where(ClaimCard.risk_level.in_(levels))
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            query = query.where(ClaimCard.status.in_(statuses))
            count_query = count_query.where(ClaimCard.status.in_(statuses))

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(ClaimCard.updated_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return PaginatedCCResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=ClaimCardResponse, summary="创建事实卡")
async def create_claim_card(
    req: ClaimCardCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    packet = await db.get(StoryPacket, req.story_packet_id)
    if not packet:
        raise NotFoundError("报道任务包", str(req.story_packet_id))
    visible_story_packet_ids = await _get_visible_story_packet_ids(db, current_user)
    if req.story_packet_id not in visible_story_packet_ids:
        raise NotFoundError("报道任务包", str(req.story_packet_id))

    card = ClaimCard(
        story_packet_id=req.story_packet_id,
        claim_text=req.claim_text,
        risk_level=req.risk_level,
        status=req.status,
        supporting_evidence=req.supporting_evidence,
        contradicting_evidence=req.contradicting_evidence,
        missing_evidence=req.missing_evidence,
        confidence_score=req.confidence_score,
        draft_anchor_ref=req.draft_anchor_ref,
    )
    db.add(card)
    await db.flush()
    await db.refresh(card)
    return card


@router.get("/{card_id}", response_model=ClaimCardResponse, summary="事实卡详情")
async def get_claim_card(
    card_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    card = await db.get(ClaimCard, card_id)
    if not card:
        raise NotFoundError("事实卡", card_id)
    await _assert_claim_visible(db, card, current_user)
    return card


@router.patch("/{card_id}", response_model=ClaimCardResponse, summary="更新事实卡")
async def update_claim_card(
    card_id: str,
    req: ClaimCardUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    card = await db.get(ClaimCard, card_id)
    if not card:
        raise NotFoundError("事实卡", card_id)
    await _assert_claim_visible(db, card, current_user)

    update_data = req.model_dump(exclude_unset=True)

    # outline 规则：manually_accepted 必须写理由
    if update_data.get("status") == "manually_accepted" and not update_data.get("manual_accept_reason"):
        from app.core.errors import AppError
        raise AppError("REASON_REQUIRED", "manually_accepted 状态必须填写 manual_accept_reason")

    for field, value in update_data.items():
        setattr(card, field, value)

    if "status" in update_data and update_data["status"] in ("supported", "manually_accepted"):
        card.verified_by = current_user.id

    await db.flush()
    await db.refresh(card)
    return card


@router.delete("/{card_id}", response_model=ClaimCardResponse, summary="删除事实卡（软删除）")
async def delete_claim_card(
    card_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    card = await db.get(ClaimCard, card_id)
    if not card:
        raise NotFoundError("事实卡", card_id)
    await _assert_claim_visible(db, card, current_user)
    card.status = "archived"
    await db.flush()
    await db.refresh(card)
    return card


@router.post("/{card_id}/restore", response_model=ClaimCardResponse, summary="恢复已删除事实卡")
async def restore_claim_card(
    card_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    card = await db.get(ClaimCard, card_id)
    if not card:
        raise NotFoundError("事实卡", card_id)
    await _assert_claim_visible(db, card, current_user)
    if card.status != "archived":
        from app.core.errors import AppError
        raise AppError("NOT_ARCHIVED", "该事实卡未被删除，无需恢复")
    card.status = "unverified"
    await db.flush()
    await db.refresh(card)
    return card


@router.get("/archived/list", response_model=list[ClaimCardResponse], summary="已删除事实卡列表")
async def list_archived_claim_cards(
    story_packet_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    visible_story_packet_ids = await _get_visible_story_packet_ids(db, current_user)
    if not visible_story_packet_ids:
        return []

    query = select(ClaimCard).where(ClaimCard.status == "archived")
    query = query.where(ClaimCard.story_packet_id.in_(visible_story_packet_ids))
    if story_packet_id:
        query = query.where(ClaimCard.story_packet_id == story_packet_id)
    query = query.order_by(ClaimCard.updated_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())
