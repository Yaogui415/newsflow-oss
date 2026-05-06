"""工作流可观测 API：提供 canonical workflow 模板与任务包进度查询。"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import NotFoundError, AppError
from app.models.story_packet import StoryPacket
from app.models.review_bundle import ReviewBundle
from app.models.approval_task import ApprovalTask
from app.models.user import User
from app.api.deps import get_current_user
from app.api.v1.schemas import ErrorResponse
from app.services.event_audit_service import event_audit_service
from app.services.workflow_runtime_service import workflow_runtime_service

router = APIRouter()


CANONICAL_STAGES: list[dict] = [
    {"key": "source_ingestion", "name": "Source Item 进入系统", "type": "agent"},
    {"key": "preprocess_gate1", "name": "材料预处理 + 脱敏门1", "type": "agent"},
    {"key": "event_case_merge", "name": "归并/命中 Event Case", "type": "agent"},
    {"key": "human_triage", "name": "人工 Triage/立项", "type": "human_gate"},
    {"key": "story_packet_created", "name": "创建 Story Packet", "type": "system"},
    {"key": "ai_workpack", "name": "AI 生成 Evidence/Claim 等工作包", "type": "agent"},
    {"key": "human_supplement", "name": "人工补充与修正", "type": "human_gate"},
    {"key": "redaction_gate2", "name": "脱敏门2：AI内容脱敏审查", "type": "agent"},
    {"key": "draft_version", "name": "形成 Draft Version 基准稿", "type": "system"},
    {"key": "risk_redaction_gate3", "name": "发布前风控/脱敏门3", "type": "agent"},
    {"key": "review_bundle", "name": "冻结送审 Review Bundle", "type": "system"},
    {"key": "approval_task", "name": "人工签发 Approval Task", "type": "human_gate"},
    {"key": "channel_package", "name": "生成 Channel Package", "type": "agent"},
    {"key": "channel_review", "name": "渠道审", "type": "human_gate"},
    {"key": "human_publish_gate", "name": "人工确认发布", "type": "human_gate"},
    {"key": "published", "name": "发布", "type": "system"},
    {"key": "post_monitoring", "name": "发布后持续监测", "type": "agent"},
]


STATUS_TO_INDEX = {
    "created": 4,
    "researching": 5,
    "verification_pending": 6,
    "supplement": 7,
    "redaction_gate2": 7,
    "drafting": 8,
    "editorial_review": 11,
    "risk_review": 11,
    "channel_packaging": 12,
    "channel_review": 13,
    "ready_to_publish": 14,
    "published": 15,
    "monitoring": 16,
    "reopened": 8,
    "killed": 4,
}


class WorkflowStageItem(BaseModel):
    key: str
    name: str
    type: str
    state: str  # completed/current/pending/blocked


class WorkflowTemplateResponse(BaseModel):
    stages: list[dict]


class StoryPacketWorkflowProgressResponse(BaseModel):
    story_packet_id: str
    story_packet_status: str
    current_stage_key: str
    blocked: bool
    blockers_count: int
    approval_pending_count: int
    approval_returned_count: int
    stages: list[WorkflowStageItem]
    generated_at: datetime


class WorkflowRunCreateRequest(BaseModel):
    event_case_id: str | None = None
    source_items: list[dict] = Field(default_factory=list)


class WorkflowDecisionRequest(BaseModel):
    decision_type: str
    action: str
    reason: str | None = None


class WorkflowRunResponse(BaseModel):
    run_id: str
    event_case_id: str | None
    story_packet_id: str | None
    current_stage: str
    status: str
    last_error: str | None
    created_by: str | None
    created_at: str
    updated_at: str
    state: dict


class WorkflowRunEventResponse(BaseModel):
    id: int
    run_id: str
    event_type: str
    payload: dict
    created_at: str


class WorkflowRunEventCursorPageResponse(BaseModel):
    items: list[WorkflowRunEventResponse]
    next_cursor: str | None
    has_more: bool
    limit: int


class UnifiedAuditEventResponse(BaseModel):
    id: str
    actor_id: str | None
    actor_type: str
    action: str
    object_type: str
    object_id: str
    details: dict
    previous_hash: str | None
    override_ai_flag: bool
    override_reason: str | None
    created_at: str


class UnifiedAuditCursorPageResponse(BaseModel):
    items: list[UnifiedAuditEventResponse]
    next_cursor: str | None
    has_more: bool
    limit: int


CURSOR_ERROR_RESPONSES = {
    400: {
        "model": ErrorResponse,
        "description": "cursor 非法或损坏",
    },
    422: {
        "model": ErrorResponse,
        "description": "请求参数校验失败",
    },
}


def _normalize_blockers(raw_blockers) -> list[dict]:
    if raw_blockers is None:
        return []
    if isinstance(raw_blockers, str):
        try:
            parsed = json.loads(raw_blockers)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return raw_blockers if isinstance(raw_blockers, list) else []


def _map_run_row(row) -> WorkflowRunResponse:
    if not row:
        raise NotFoundError("工作流实例")

    state = row["state_json"]
    if isinstance(state, str):
        try:
            state = json.loads(state)
        except Exception:
            state = {}

    return WorkflowRunResponse(
        run_id=row["run_id"],
        event_case_id=row["event_case_id"],
        story_packet_id=row["story_packet_id"],
        current_stage=row["current_stage"],
        status=row["status"],
        last_error=row["last_error"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        state=state,
    )


@router.post("/runs", response_model=WorkflowRunResponse, summary="创建工作流实例")
async def create_workflow_run(
    req: WorkflowRunCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    state = await workflow_runtime_service.create_run(
        db=db,
        created_by=current_user.id,
        event_case_id=req.event_case_id,
        source_items=req.source_items,
    )
    row = await workflow_runtime_service.get_run_row(db, state.workflow_id)
    return _map_run_row(row)


@router.get("/runs/{run_id}", response_model=WorkflowRunResponse, summary="获取工作流实例详情")
async def get_workflow_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await workflow_runtime_service.get_run_row(db, run_id)
    if not row:
        raise NotFoundError("工作流实例", run_id)
    return _map_run_row(row)


@router.post("/runs/{run_id}/advance", response_model=WorkflowRunResponse, summary="推进工作流实例")
async def advance_workflow_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await workflow_runtime_service.get_run_row(db, run_id)
    if not row:
        raise NotFoundError("工作流实例", run_id)

    await workflow_runtime_service.advance_run(db, run_id)
    updated = await workflow_runtime_service.get_run_row(db, run_id)
    return _map_run_row(updated)


@router.post("/runs/{run_id}/decisions", response_model=WorkflowRunResponse, summary="提交人工决策并推进")
async def submit_workflow_decision(
    run_id: str,
    req: WorkflowDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await workflow_runtime_service.get_run_row(db, run_id)
    if not row:
        raise NotFoundError("工作流实例", run_id)

    await workflow_runtime_service.submit_decision(
        db,
        run_id,
        decision_type=req.decision_type,
        action=req.action,
        reason=req.reason,
        actor_id=current_user.id,
    )
    updated = await workflow_runtime_service.get_run_row(db, run_id)
    return _map_run_row(updated)


@router.get(
    "/runs/{run_id}/events",
    response_model=WorkflowRunEventCursorPageResponse,
    responses=CURSOR_ERROR_RESPONSES,
    summary="工作流实例事件流",
)
async def get_workflow_run_events(
    run_id: str,
    cursor: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await workflow_runtime_service.get_run_row(db, run_id)
    if not row:
        raise NotFoundError("工作流实例", run_id)
    if cursor and workflow_runtime_service.decode_event_cursor(cursor) is None:
        raise AppError("INVALID_CURSOR", "cursor 非法或已损坏", 400)
    page = await workflow_runtime_service.list_events_cursor_page(
        db,
        run_id,
        cursor=cursor,
        limit=limit,
    )
    return WorkflowRunEventCursorPageResponse(
        items=[WorkflowRunEventResponse(**event) for event in page["items"]],
        next_cursor=page["next_cursor"],
        has_more=page["has_more"],
        limit=page["limit"],
    )


@router.get(
    "/audit/events",
    response_model=UnifiedAuditCursorPageResponse,
    responses=CURSOR_ERROR_RESPONSES,
    summary="统一审计事件流",
)
async def list_unified_audit_events(
    object_type: str | None = None,
    object_id: str | None = None,
    action: str | None = None,
    actor_type: str | None = None,
    cursor: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if cursor and event_audit_service.decode_cursor(cursor) is None:
        raise AppError("INVALID_CURSOR", "cursor 非法或已损坏", 400)
    page = await event_audit_service.list_events(
        db,
        object_type=object_type,
        object_id=object_id,
        action=action,
        actor_type=actor_type,
        cursor=cursor,
        limit=limit,
    )
    return UnifiedAuditCursorPageResponse(
        items=[UnifiedAuditEventResponse(**item) for item in page["items"]],
        next_cursor=page["next_cursor"],
        has_more=page["has_more"],
        limit=page["limit"],
    )


@router.get("/template", response_model=WorkflowTemplateResponse, summary="标准工作流模板")
async def get_workflow_template(
    current_user: User = Depends(get_current_user),
):
    return WorkflowTemplateResponse(stages=CANONICAL_STAGES)


@router.get("/story-packets/{packet_id}/progress", response_model=StoryPacketWorkflowProgressResponse, summary="Story Packet 工作流进度")
async def get_story_packet_workflow_progress(
    packet_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    packet = await db.get(StoryPacket, packet_id)
    if not packet:
        raise NotFoundError("报道任务包", packet_id)

    stage_index = STATUS_TO_INDEX.get(packet.status, 0)
    current_stage = CANONICAL_STAGES[stage_index]["key"]

    blockers = _normalize_blockers(packet.blockers)
    unresolved = [b for b in blockers if not b.get("resolved", False)]

    bundle_rows = await db.execute(
        select(ReviewBundle.id).where(ReviewBundle.story_packet_id == packet_id)
    )
    bundle_ids = list(bundle_rows.scalars().all())

    approval_tasks: list[ApprovalTask] = []
    if bundle_ids:
        task_rows = await db.execute(
            select(ApprovalTask).where(ApprovalTask.review_bundle_id.in_(bundle_ids))
        )
        approval_tasks = list(task_rows.scalars().all())

    approval_pending_count = len([t for t in approval_tasks if t.status in ("pending", "in_review")])
    approval_returned_count = len([t for t in approval_tasks if t.status == "returned"])

    stage_items: list[WorkflowStageItem] = []
    for i, stage in enumerate(CANONICAL_STAGES):
        if unresolved and i == stage_index:
            state = "blocked"
        elif i < stage_index:
            state = "completed"
        elif i == stage_index:
            state = "current"
        else:
            state = "pending"

        stage_items.append(
            WorkflowStageItem(
                key=stage["key"],
                name=stage["name"],
                type=stage["type"],
                state=state,
            )
        )

    return StoryPacketWorkflowProgressResponse(
        story_packet_id=packet.id,
        story_packet_status=packet.status,
        current_stage_key=current_stage,
        blocked=len(unresolved) > 0,
        blockers_count=len(unresolved),
        approval_pending_count=approval_pending_count,
        approval_returned_count=approval_returned_count,
        stages=stage_items,
        generated_at=datetime.utcnow(),
    )
