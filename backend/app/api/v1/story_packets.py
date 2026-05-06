"""报道任务包 API：CRUD + 状态迁移 + 送审。"""

from datetime import datetime

import json

from fastapi import APIRouter, Depends, Query, Header
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import NotFoundError, InvalidTransitionError, BlockerExistsError, AppError
from app.core.state_machine import story_packet_engine
from app.models.story_packet import StoryPacket
from app.models.event_case import EventCase
from app.models.claim_card import ClaimCard
from app.models.draft_version import DraftVersion
from app.models.user import User
from app.api.deps import get_current_user
from app.api.v1.schemas import ErrorResponse
from app.services.precheck_service import precheck_service
from app.services.snapshot_service import snapshot_service
from app.services.approval_service import approval_service
from app.services.idempotency_service import idempotency_service
from app.services.event_audit_service import event_audit_service

router = APIRouter()


# ── 请求/响应模型 ──

class StoryPacketCreate(BaseModel):
    event_case_id: str | None = None
    title: str
    content_type: str
    angle_statement: str | None = None
    target_audience: str | None = None
    risk_level: str = "L0"
    desk: str | None = None
    deadline: datetime | None = None


class StoryPacketUpdate(BaseModel):
    title: str | None = None
    angle_statement: str | None = None
    target_audience: str | None = None
    risk_level: str | None = None
    deadline: datetime | None = None


class StoryPacketResponse(BaseModel):
    id: str
    event_case_id: str | None = None
    title: str
    angle_statement: str | None
    target_audience: str | None
    content_type: str
    status: str
    risk_level: str
    owner_id: str | None
    owner_display_name: str | None = None
    event_case_title: str | None = None
    desk: str | None
    deadline: datetime | None
    blockers: list
    created_at: datetime
    updated_at: datetime

    @field_validator("blockers", mode="before")
    @classmethod
    def _parse_blockers(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v if v is not None else []

    model_config = {"from_attributes": True}


class TransitionRequest(BaseModel):
    target_state: str


class SubmitReviewRequest(BaseModel):
    submit_note: str
    bundle_type: str = "editorial"  # editorial / risk / channel / final


class PrecheckResponse(BaseModel):
    passed: bool
    blocking_items: list[dict]
    warning_items: list[dict]


class ReviewBundleResponse(BaseModel):
    id: str
    story_packet_id: str
    bundle_type: str
    bundle_hash: str
    status: str
    submit_note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SubmitReviewResponse(BaseModel):
    precheck: PrecheckResponse
    review_bundle: ReviewBundleResponse | None = None
    approval_task_id: str | None = None
    idempotency_key: str | None = None
    replayed: bool = False


SUBMIT_REVIEW_ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "请求参数错误"},
    404: {"model": ErrorResponse, "description": "报道任务包不存在"},
    409: {"model": ErrorResponse, "description": "幂等冲突或请求处理中"},
    422: {"model": ErrorResponse, "description": "请求参数校验失败"},
}


class PaginatedSPResponse(BaseModel):
    items: list[StoryPacketResponse]
    total: int
    page: int
    page_size: int


async def _get_visibility_scope(db: AsyncSession, current_user: User) -> tuple[list[str], list[str]]:
    """Return (visible_owner_ids, visible_event_ids) for current user scope."""
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

    return visible_owner_ids, visible_event_ids


def _packet_visibility_filter(visible_owner_ids: list[str], visible_event_ids: list[str]):
    return or_(
        StoryPacket.owner_id.in_(visible_owner_ids),
        StoryPacket.event_case_id.in_(visible_event_ids),
    )


async def _assert_packet_visible(db: AsyncSession, packet: StoryPacket, current_user: User):
    visible_owner_ids, visible_event_ids = await _get_visibility_scope(db, current_user)
    owner_visible = packet.owner_id in visible_owner_ids if packet.owner_id else False
    event_visible = packet.event_case_id in visible_event_ids if packet.event_case_id else False
    if not (owner_visible or event_visible):
        raise NotFoundError("报道任务包", str(packet.id))


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
    created_at: datetime
    updated_at: datetime

    @field_validator("supporting_evidence", "contradicting_evidence", "missing_evidence", mode="before")
    @classmethod
    def _parse_evidence_list(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v if v is not None else []

    model_config = {"from_attributes": True}


class DraftVersionResponse(BaseModel):
    id: str
    story_packet_id: str
    version: int
    title: str | None
    lead: str | None
    body: str | None
    body_html: str | None
    claim_anchor_map: dict | None
    word_count: int | None
    is_frozen: bool
    created_at: datetime
    created_by: str | None

    @field_validator("claim_anchor_map", mode="before")
    @classmethod
    def _parse_anchor_map(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v

    model_config = {"from_attributes": True}


class DraftVersionUpdateRequest(BaseModel):
    title: str | None = None
    lead: str | None = None
    body: str | None = None
    body_html: str | None = None
    claim_anchor_map: dict | None = None


# ── 状态机配置（声明式，非硬编码 if-else） ──

VALID_TRANSITIONS: dict[str, list[str]] = {
    "created": ["researching", "killed"],
    "researching": ["verification_pending", "killed"],
    "verification_pending": ["drafting", "researching"],
    "drafting": ["editorial_review", "verification_pending", "killed"],
    "editorial_review": ["risk_review", "drafting"],
    "risk_review": ["channel_packaging", "drafting"],
    "channel_packaging": ["channel_review"],
    "channel_review": ["ready_to_publish", "channel_packaging"],
    "ready_to_publish": ["published"],
    "published": ["monitoring"],
    "monitoring": ["reopened", "archived"],
    "reopened": ["researching", "drafting"],
}

PRECONDITIONS: dict[str, list[str]] = {
    "researching": ["has_owner"],
    "verification_pending": ["has_evidence_pack"],
    "drafting": ["has_claim_cards"],
    "editorial_review": ["has_draft_version"],
    "risk_review": ["editorial_approved"],
    "channel_packaging": ["risk_cleared"],
    "ready_to_publish": ["all_channels_approved"],
    "published": ["human_publish_confirmed"],
    "reopened": ["has_reopen_trigger"],
}


# ── 接口 ──

@router.get("", response_model=PaginatedSPResponse, summary="报道任务包列表", description="分页获取报道任务包列表，支持按 event_case_id 和 status 筛选。")
async def list_story_packets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    event_case_id: str | None = None,
    status: str | None = None,
    scope: str | None = Query(None, description="预设筛选范围，如 in_progress"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(StoryPacket).where(StoryPacket.status != "archived")
    count_query = select(func.count(StoryPacket.id)).where(StoryPacket.status != "archived")

    visible_owner_ids, visible_event_ids = await _get_visibility_scope(db, current_user)
    visibility_filter = _packet_visibility_filter(visible_owner_ids, visible_event_ids)
    query = query.where(visibility_filter)
    count_query = count_query.where(visibility_filter)

    if event_case_id:
        query = query.where(StoryPacket.event_case_id == event_case_id)
        count_query = count_query.where(StoryPacket.event_case_id == event_case_id)
    if status:
        query = query.where(StoryPacket.status == status)
        count_query = count_query.where(StoryPacket.status == status)
    if scope == "in_progress":
        query = query.where(StoryPacket.status.notin_(["published", "killed", "archived"]))
        count_query = count_query.where(StoryPacket.status.notin_(["published", "killed", "archived"]))

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(StoryPacket.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    raw_items = list(result.scalars().all())
    items = []
    for sp in raw_items:
        resp = StoryPacketResponse.model_validate(sp)
        if sp.owner_id:
            owner = await db.get(User, sp.owner_id)
            resp.owner_display_name = owner.display_name if owner else None
        if sp.event_case_id:
            ev = await db.get(EventCase, sp.event_case_id)
            resp.event_case_title = ev.title if ev else None
        items.append(resp)
    return PaginatedSPResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=StoryPacketResponse, summary="创建报道任务包", description="在指定事件案卷下创建报道任务包，初始状态为 created。")
async def create_story_packet(
    req: StoryPacketCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = None
    if req.event_case_id:
        event = await db.get(EventCase, req.event_case_id)
        if not event:
            raise NotFoundError("事件案卷", str(req.event_case_id))

    packet = StoryPacket(
        event_case_id=req.event_case_id,
        title=req.title,
        content_type=req.content_type,
        angle_statement=req.angle_statement,
        target_audience=req.target_audience,
        risk_level=req.risk_level,
        desk=req.desk or (event.desk if event else None),
        deadline=req.deadline,
        owner_id=current_user.id,
    )
    db.add(packet)
    await db.commit()
    await db.refresh(packet)
    resp = StoryPacketResponse.model_validate(packet)
    resp.owner_display_name = current_user.display_name
    if event:
        resp.event_case_title = event.title
    return resp


@router.get("/archived/list", response_model=list[StoryPacketResponse], summary="已删除任务包列表", description="获取已归档/已删除的任务包。")
async def list_archived_packets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    visible_owner_ids, visible_event_ids = await _get_visibility_scope(db, current_user)
    visibility_filter = _packet_visibility_filter(visible_owner_ids, visible_event_ids)
    result = await db.execute(
        select(StoryPacket)
        .where(StoryPacket.status == "archived")
        .where(visibility_filter)
        .order_by(StoryPacket.updated_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{packet_id}", response_model=StoryPacketResponse, summary="报道任务包详情", description="获取单个报道任务包的完整信息。")
async def get_story_packet(
    packet_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    packet = await db.get(StoryPacket, packet_id)
    if not packet:
        raise NotFoundError("报道任务包", str(packet_id))
    await _assert_packet_visible(db, packet, current_user)
    resp = StoryPacketResponse.model_validate(packet)
    if packet.owner_id:
        owner = await db.get(User, packet.owner_id)
        resp.owner_display_name = owner.display_name if owner else None
    if packet.event_case_id:
        ev = await db.get(EventCase, packet.event_case_id)
        resp.event_case_title = ev.title if ev else None
    return resp


@router.get("/{packet_id}/claim-cards", response_model=list[ClaimCardResponse], summary="Claim Cards 列表（支持筛选）", description="获取指定任务包下的 Claim Cards，支持按风险等级和核验状态筛选（逗号分隔多值）。")
async def list_claim_cards(
    packet_id: str,
    risk_level: str | None = Query(None, description="风险等级，支持逗号分隔：L0,L1,L2,L3"),
    status: str | None = Query(None, description="核验状态，支持逗号分隔：supported,disputed,insufficient"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    packet = await db.get(StoryPacket, packet_id)
    if not packet:
        raise NotFoundError("报道任务包", str(packet_id))
    await _assert_packet_visible(db, packet, current_user)

    query = select(ClaimCard).where(ClaimCard.story_packet_id == packet_id).where(ClaimCard.status != "archived")

    if risk_level:
        risk_levels = [item.strip() for item in risk_level.split(",") if item.strip()]
        if risk_levels:
            query = query.where(ClaimCard.risk_level.in_(risk_levels))

    if status:
        statuses = [item.strip() for item in status.split(",") if item.strip()]
        if statuses:
            query = query.where(ClaimCard.status.in_(statuses))

    query = query.order_by(ClaimCard.updated_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{packet_id}/draft", response_model=DraftVersionResponse | None, summary="获取当前正文草稿", description="获取最新版本的正文草稿，若不存在返回 null。")
async def get_latest_draft(
    packet_id: str,
    auto_create: bool = Query(False, description="若无草稿是否自动创建 v1 空稿"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    packet = await db.get(StoryPacket, packet_id)
    if not packet:
        raise NotFoundError("报道任务包", str(packet_id))
    await _assert_packet_visible(db, packet, current_user)

    draft_result = await db.execute(
        select(DraftVersion)
        .where(DraftVersion.story_packet_id == packet_id)
        .order_by(DraftVersion.version.desc(), DraftVersion.created_at.desc())
        .limit(1)
    )
    draft = draft_result.scalar_one_or_none()

    if draft is None and auto_create:
        draft = DraftVersion(
            story_packet_id=packet_id,
            version=1,
            title=packet.title,
            lead=None,
            body="",
            body_html=None,
            claim_anchor_map={},
            word_count=0,
            created_by=current_user.id,
        )
        db.add(draft)
        await db.commit()
        await db.refresh(draft)

    return draft


@router.patch("/{packet_id}/draft", response_model=DraftVersionResponse, summary="编辑正文草稿并生成新版本", description="保存编辑内容并生成新版本号（不可变），支持 title/lead/body/body_html/claim_anchor_map。")
async def update_draft(
    packet_id: str,
    req: DraftVersionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    packet = await db.get(StoryPacket, packet_id)
    if not packet:
        raise NotFoundError("报道任务包", str(packet_id))
    await _assert_packet_visible(db, packet, current_user)

    latest_result = await db.execute(
        select(DraftVersion)
        .where(DraftVersion.story_packet_id == packet_id)
        .order_by(DraftVersion.version.desc(), DraftVersion.created_at.desc())
        .limit(1)
    )
    latest = latest_result.scalar_one_or_none()

    next_version = (latest.version + 1) if latest else 1
    base_title = latest.title if latest else packet.title
    base_lead = latest.lead if latest else None
    base_body = latest.body if latest else ""
    base_body_html = latest.body_html if latest else None
    base_anchor_map = latest.claim_anchor_map if latest else {}

    new_body = req.body if req.body is not None else base_body
    word_count = len(new_body.split()) if new_body else 0

    draft = DraftVersion(
        story_packet_id=packet_id,
        version=next_version,
        title=req.title if req.title is not None else base_title,
        lead=req.lead if req.lead is not None else base_lead,
        body=new_body,
        body_html=req.body_html if req.body_html is not None else base_body_html,
        claim_anchor_map=req.claim_anchor_map if req.claim_anchor_map is not None else base_anchor_map,
        word_count=word_count,
        is_frozen=False,
        created_by=current_user.id,
    )
    db.add(draft)
    await db.commit()
    await db.refresh(draft)
    return draft


@router.get("/{packet_id}/draft/versions", response_model=list[DraftVersionResponse], summary="获取草稿版本历史", description="返回该任务包所有草稿版本，按版本号降序排列。")
async def list_draft_versions(
    packet_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    packet = await db.get(StoryPacket, packet_id)
    if not packet:
        raise NotFoundError("报道任务包", str(packet_id))
    await _assert_packet_visible(db, packet, current_user)
    result = await db.execute(
        select(DraftVersion)
        .where(DraftVersion.story_packet_id == packet_id)
        .order_by(DraftVersion.version.desc())
    )
    return list(result.scalars().all())


@router.get("/{packet_id}/draft/{version_num}", response_model=DraftVersionResponse, summary="获取指定版本草稿")
async def get_draft_version(
    packet_id: str,
    version_num: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    packet = await db.get(StoryPacket, packet_id)
    if not packet:
        raise NotFoundError("报道任务包", str(packet_id))
    await _assert_packet_visible(db, packet, current_user)
    result = await db.execute(
        select(DraftVersion)
        .where(DraftVersion.story_packet_id == packet_id, DraftVersion.version == version_num)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise NotFoundError("草稿版本", f"v{version_num}")
    return draft


@router.patch("/{packet_id}", response_model=StoryPacketResponse, summary="更新报道任务包", description="部分更新报道任务包字段（title/angle_statement/target_audience/risk_level/deadline）。")
async def update_story_packet(
    packet_id: str,
    req: StoryPacketUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    packet = await db.get(StoryPacket, packet_id)
    if not packet:
        raise NotFoundError("报道任务包", str(packet_id))
    await _assert_packet_visible(db, packet, current_user)
    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(packet, field, value)
    await db.commit()
    await db.refresh(packet)
    return packet


@router.post("/{packet_id}/transition", response_model=StoryPacketResponse, summary="状态迁移", description="通过声明式状态机引擎推进任务包状态。自动校验前置条件和阻塞项。")
async def transition_story_packet(
    packet_id: str,
    req: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    packet = await db.get(StoryPacket, packet_id)
    if not packet:
        raise NotFoundError("报道任务包", str(packet_id))
    await _assert_packet_visible(db, packet, current_user)

    # 使用声明式状态机引擎，自动校验前置条件和阻塞项
    success, info = await story_packet_engine.attempt_transition(
        obj=packet,
        target_state=req.target_state,
        actor=current_user,
        db=db,
    )

    if info and info.startswith("requires_approval:"):
        # 需要审批的迁移，不直接推进状态
        pass

    await db.commit()
    await db.refresh(packet)
    return packet


@router.get("/{packet_id}/precheck", response_model=PrecheckResponse, summary="送审预检", description="执行送审前预检，返回阻断项和警告项。可指定 stage 参数模拟不同审批阶段。")
async def precheck_story_packet(
    packet_id: str,
    stage: str = Query("editorial_review", description="审批阶段"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行送审预检，返回阻断项和警告项"""
    packet = await db.get(StoryPacket, packet_id)
    if not packet:
        raise NotFoundError("报道任务包", str(packet_id))
    await _assert_packet_visible(db, packet, current_user)
    
    result = await precheck_service.run_precheck(packet, db, stage=stage)
    return result.to_dict()


@router.post(
    "/{packet_id}/submit-review",
    response_model=SubmitReviewResponse,
    responses=SUBMIT_REVIEW_ERROR_RESPONSES,
    summary="提交送审",
)
async def submit_review(
    packet_id: str,
    req: SubmitReviewRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    提交送审流程:
    1. 执行送审预检
    2. 如通过，创建 Review Bundle（冻结版本）
    3. 根据风险等级创建 Approval Task
    """
    packet = await db.get(StoryPacket, packet_id)
    if not packet:
        raise NotFoundError("报道任务包", str(packet_id))
    await _assert_packet_visible(db, packet, current_user)

    idem_scope = "submit_review"
    if idempotency_key:
        idem_state = await idempotency_service.begin_request(
            db,
            scope=idem_scope,
            object_id=packet_id,
            user_id=current_user.id,
            idem_key=idempotency_key,
            payload={
                "submit_note": req.submit_note,
                "bundle_type": req.bundle_type,
                "story_packet_status": packet.status,
                "story_packet_updated_at": packet.updated_at.isoformat() if packet.updated_at else None,
            },
        )
        if idem_state["state"] == "conflict":
            raise AppError("IDEMPOTENCY_CONFLICT", "同一 Idempotency-Key 对应的请求体不一致", 409)
        if idem_state["state"] == "processing":
            raise AppError("REQUEST_IN_PROGRESS", "相同请求正在处理中，请稍后重试", 409)
        if idem_state["state"] == "replay":
            record = idem_state["record"]
            raw_response = record.get("response_json")
            if isinstance(raw_response, str):
                try:
                    replay_data = json.loads(raw_response)
                except Exception:
                    replay_data = None
            else:
                replay_data = raw_response
            if replay_data:
                replay_data["idempotency_key"] = idempotency_key
                replay_data["replayed"] = True
                return SubmitReviewResponse(**replay_data)

    try:
        # 1. 执行预检
        precheck_result = await precheck_service.run_precheck(
            packet, db, submit_note=req.submit_note, stage=req.bundle_type
        )

        if not precheck_result.passed:
            response = SubmitReviewResponse(
                precheck=precheck_result.to_dict(),
                review_bundle=None,
                approval_task_id=None,
                idempotency_key=idempotency_key,
                replayed=False,
            )
            await event_audit_service.append_event(
                db,
                actor_id=current_user.id,
                actor_type="human",
                action="submit_review_precheck_failed",
                object_type="story_packet",
                object_id=packet_id,
                details={
                    "bundle_type": req.bundle_type,
                    "blocking_items": precheck_result.to_dict().get("blocking_items", []),
                    "idempotency_key": idempotency_key,
                },
            )
            if idempotency_key:
                await idempotency_service.mark_succeeded(
                    db,
                    scope=idem_scope,
                    object_id=packet_id,
                    user_id=current_user.id,
                    idem_key=idempotency_key,
                    response_payload=response.model_dump(mode="json"),
                )
            return response

        # 2. 废弃旧的活跃 bundle
        await snapshot_service.supersede_old_bundles(packet_id, db)

        # 3. 创建新的 Review Bundle
        bundle = await snapshot_service.create_review_bundle(
            story_packet_id=packet_id,
            bundle_type=req.bundle_type,
            submitted_by=current_user.id,
            submit_note=req.submit_note,
            db=db,
        )

        # 4. 创建审批任务
        approval_stage = f"{req.bundle_type}_review" if not req.bundle_type.endswith("_review") else req.bundle_type
        task = await approval_service.create_approval_task(
            review_bundle=bundle,
            story_packet=packet,
            approval_stage=approval_stage,
            db=db,
        )

        response = SubmitReviewResponse(
            precheck=precheck_result.to_dict(),
            review_bundle=ReviewBundleResponse.model_validate(bundle),
            approval_task_id=task.id if task else None,
            idempotency_key=idempotency_key,
            replayed=False,
        )

        await event_audit_service.append_event(
            db,
            actor_id=current_user.id,
            actor_type="human",
            action="submit_review_succeeded",
            object_type="story_packet",
            object_id=packet_id,
            details={
                "bundle_id": bundle.id,
                "bundle_type": bundle.bundle_type,
                "approval_task_id": task.id if task else None,
                "idempotency_key": idempotency_key,
            },
        )

        if idempotency_key:
            await idempotency_service.mark_succeeded(
                db,
                scope=idem_scope,
                object_id=packet_id,
                user_id=current_user.id,
                idem_key=idempotency_key,
                response_payload=response.model_dump(mode="json"),
            )

        await db.commit()
        return response
    except Exception as exc:
        if idempotency_key:
            await idempotency_service.mark_failed(
                db,
                scope=idem_scope,
                object_id=packet_id,
                user_id=current_user.id,
                idem_key=idempotency_key,
                error_message=str(exc),
            )
        raise


@router.delete("/{packet_id}", response_model=dict, summary="删除任务包", description="软删除任务包（状态设为 archived）。")
async def delete_story_packet(
    packet_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    packet = await db.get(StoryPacket, packet_id)
    if not packet:
        raise NotFoundError("报道任务包", str(packet_id))
    await _assert_packet_visible(db, packet, current_user)
    packet.status = "archived"
    await db.commit()
    return {"message": "已删除", "id": packet_id}


@router.post("/{packet_id}/restore", response_model=StoryPacketResponse, summary="恢复任务包", description="恢复已删除的任务包。")
async def restore_story_packet(
    packet_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    packet = await db.get(StoryPacket, packet_id)
    if not packet:
        raise NotFoundError("报道任务包", str(packet_id))
    await _assert_packet_visible(db, packet, current_user)
    packet.status = "created"
    await db.commit()
    await db.refresh(packet)
    return packet
