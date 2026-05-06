"""勘误单 API：CRUD + 状态操作。"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import NotFoundError
from app.models.correction_ticket import CorrectionTicket
from app.models.event_case import EventCase
from app.models.story_packet import StoryPacket
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter()


# ── 请求/响应模型 ──

class CorrectionTicketCreate(BaseModel):
    story_packet_id: str | None = None
    event_case_id: str | None = None
    source_publish_id: str | None = None
    trigger_reason: str
    impact_scope: str | None = None
    proposed_fix: str | None = None


class CorrectionTicketUpdate(BaseModel):
    trigger_reason: str | None = None
    impact_scope: str | None = None
    proposed_fix: str | None = None
    status: str | None = None


class CorrectionTicketResponse(BaseModel):
    id: str
    story_packet_id: str | None
    event_case_id: str | None
    source_publish_id: str | None
    trigger_reason: str
    impact_scope: str | None
    proposed_fix: str | None
    status: str
    owner_id: str | None
    closed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class PaginatedCTResponse(BaseModel):
    items: list[CorrectionTicketResponse]
    total: int
    page: int
    page_size: int


async def _get_visibility_scope(db: AsyncSession, current_user: User) -> tuple[list[str], list[str], list[str]]:
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

    return visible_owner_ids, visible_event_ids, visible_story_packet_ids


async def _assert_ticket_visible(db: AsyncSession, ticket: CorrectionTicket, current_user: User):
    _, visible_event_ids, visible_story_packet_ids = await _get_visibility_scope(db, current_user)
    visible = (
        (ticket.story_packet_id and ticket.story_packet_id in visible_story_packet_ids) or
        (ticket.event_case_id and ticket.event_case_id in visible_event_ids) or
        (ticket.owner_id == current_user.id)
    )
    if not visible:
        raise NotFoundError("勘误单", str(ticket.id))


# ── 端点 ──

@router.get("", response_model=PaginatedCTResponse, summary="勘误单列表")
async def list_correction_tickets(
    story_packet_id: str | None = None,
    event_case_id: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, visible_event_ids, visible_story_packet_ids = await _get_visibility_scope(db, current_user)
    query = select(CorrectionTicket)
    count_query = select(func.count(CorrectionTicket.id))

    base_visibility = or_(
        CorrectionTicket.story_packet_id.in_(visible_story_packet_ids),
        CorrectionTicket.event_case_id.in_(visible_event_ids),
        CorrectionTicket.owner_id == current_user.id,
    )
    query = query.where(base_visibility)
    count_query = count_query.where(base_visibility)

    if story_packet_id:
        query = query.where(CorrectionTicket.story_packet_id == story_packet_id)
        count_query = count_query.where(CorrectionTicket.story_packet_id == story_packet_id)
    if event_case_id:
        query = query.where(CorrectionTicket.event_case_id == event_case_id)
        count_query = count_query.where(CorrectionTicket.event_case_id == event_case_id)
    if status:
        query = query.where(CorrectionTicket.status == status)
        count_query = count_query.where(CorrectionTicket.status == status)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(CorrectionTicket.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return PaginatedCTResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=CorrectionTicketResponse, summary="创建勘误单")
async def create_correction_ticket(
    req: CorrectionTicketCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = CorrectionTicket(
        story_packet_id=req.story_packet_id,
        event_case_id=req.event_case_id,
        source_publish_id=req.source_publish_id,
        trigger_reason=req.trigger_reason,
        impact_scope=req.impact_scope,
        proposed_fix=req.proposed_fix,
        owner_id=current_user.id,
    )
    db.add(ticket)
    await db.flush()
    await db.refresh(ticket)
    return ticket


@router.get("/{ticket_id}", response_model=CorrectionTicketResponse, summary="勘误单详情")
async def get_correction_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = await db.get(CorrectionTicket, ticket_id)
    if not ticket:
        raise NotFoundError("勘误单", ticket_id)
    await _assert_ticket_visible(db, ticket, current_user)
    return ticket


@router.patch("/{ticket_id}", response_model=CorrectionTicketResponse, summary="更新勘误单")
async def update_correction_ticket(
    ticket_id: str,
    req: CorrectionTicketUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = await db.get(CorrectionTicket, ticket_id)
    if not ticket:
        raise NotFoundError("勘误单", ticket_id)
    await _assert_ticket_visible(db, ticket, current_user)

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(ticket, field, value)

    await db.flush()
    await db.refresh(ticket)
    return ticket


@router.post("/{ticket_id}/close", response_model=CorrectionTicketResponse, summary="关闭勘误单")
async def close_correction_ticket(
    ticket_id: str,
    status: str = "corrected",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = await db.get(CorrectionTicket, ticket_id)
    if not ticket:
        raise NotFoundError("勘误单", ticket_id)
    await _assert_ticket_visible(db, ticket, current_user)

    allowed = {"corrected", "not_corrected", "rejected", "closed"}
    ticket.status = status if status in allowed else "corrected"
    ticket.closed_at = datetime.utcnow()

    await db.flush()
    await db.refresh(ticket)
    return ticket
