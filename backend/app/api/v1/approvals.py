"""签发中心 API：审批任务列表、执行签发决策、Decision Log 查询。"""

from datetime import datetime
import json

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import NotFoundError, ApprovalError
from app.models.approval_task import ApprovalTask
from app.models.channel_package import ChannelPackage
from app.models.decision_log import DecisionLog
from app.models.event_case import EventCase
from app.models.review_bundle import ReviewBundle
from app.models.story_packet import StoryPacket
from app.models.user import User
from app.api.deps import get_current_user
from app.api.v1.schemas import ErrorResponse
from app.services.event_audit_service import event_audit_service

router = APIRouter()


# ── 请求/响应模型 ──

class ApprovalTaskResponse(BaseModel):
    id: str
    review_bundle_id: str
    approval_stage: str
    status: str
    signer_slots: list
    execution_mode: str
    sla_deadline: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_validator("signer_slots", mode="before")
    @classmethod
    def _parse_signer_slots(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v if v is not None else []

    model_config = {"from_attributes": True}


class EnrichedApprovalTaskResponse(ApprovalTaskResponse):
    """带关联信息的签发任务响应（用于队列和详情页）"""
    title: str | None = None
    risk_level: str | None = None
    desk: str | None = None
    owner: str | None = None
    bundle_hash: str | None = None
    bundle_type: str | None = None
    story_packet_id: str | None = None
    channel_package_id: str | None = None


class DecisionRequest(BaseModel):
    action: str  # approve / return / escalate / hold / reject
    decision_reason: str | None = None
    override_ai_flag: bool = False
    override_reason: str | None = None
    return_category: str | None = None


class DecisionLogResponse(BaseModel):
    id: str
    approval_task_id: str
    review_bundle_id: str
    signer_id: str
    signer_role: str
    action: str
    decision_reason: str | None
    override_ai_flag: bool
    override_reason: str | None
    return_category: str | None
    story_packet_id: str | None = None
    story_packet_title: str | None = None
    bundle_type: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedApprovalResponse(BaseModel):
    items: list[EnrichedApprovalTaskResponse]
    total: int
    page: int
    page_size: int


DECIDE_APPROVAL_ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "审批请求不合法"},
    404: {"model": ErrorResponse, "description": "签发任务不存在"},
    422: {"model": ErrorResponse, "description": "请求参数校验失败"},
}


def _parse_roles(raw_roles: str | list[str]) -> set[str]:
    if isinstance(raw_roles, list):
        return set(raw_roles)
    if isinstance(raw_roles, str):
        try:
            parsed = json.loads(raw_roles)
            if isinstance(parsed, list):
                return set(parsed)
        except Exception:
            return set()
    return set()


def _is_task_for_user(task: ApprovalTask, user: User) -> bool:
    signer_slots = task.signer_slots
    if isinstance(signer_slots, str):
        try:
            signer_slots = json.loads(signer_slots)
        except Exception:
            signer_slots = []
    if not isinstance(signer_slots, list):
        return False

    user_roles = _parse_roles(user.roles)
    for slot in signer_slots:
        if not isinstance(slot, dict):
            continue
        if slot.get("user_id") == user.id:
            return True
        role = slot.get("role")
        if role and role in user_roles and slot.get("status") == "pending":
            return True
    return False


async def _get_visible_bundle_ids(db: AsyncSession, current_user: User) -> set[str]:
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

    visible_channel_package_ids = list((await db.execute(
        select(ChannelPackage.id).where(ChannelPackage.story_packet_id.in_(visible_story_packet_ids))
    )).scalars().all()) if visible_story_packet_ids else []

    visible_bundle_ids = set((await db.execute(
        select(ReviewBundle.id).where(
            (ReviewBundle.story_packet_id.in_(visible_story_packet_ids)) |
            (ReviewBundle.channel_package_id.in_(visible_channel_package_ids))
        )
    )).scalars().all())
    return visible_bundle_ids


# ── 辅助函数 ──

async def _enrich_tasks(tasks: list[ApprovalTask], db: AsyncSession) -> list[EnrichedApprovalTaskResponse]:
    """从 ReviewBundle → StoryPacket 关联表获取 title、risk_level 等字段"""
    if not tasks:
        return []

    bundle_ids = list({t.review_bundle_id for t in tasks})
    bundle_result = await db.execute(
        select(ReviewBundle).where(ReviewBundle.id.in_(bundle_ids))
    )
    bundles = {b.id: b for b in bundle_result.scalars().all()}

    sp_ids = list({b.story_packet_id for b in bundles.values() if b.story_packet_id})
    sp_map: dict[str, StoryPacket] = {}
    if sp_ids:
        sp_result = await db.execute(
            select(StoryPacket).where(StoryPacket.id.in_(sp_ids))
        )
        sp_map = {sp.id: sp for sp in sp_result.scalars().all()}

    enriched = []
    for t in tasks:
        bundle = bundles.get(t.review_bundle_id)
        sp = sp_map.get(bundle.story_packet_id) if bundle and bundle.story_packet_id else None

        data = EnrichedApprovalTaskResponse.model_validate(t)
        if sp:
            data.title = sp.title
            data.risk_level = sp.risk_level
            data.desk = sp.desk
            data.owner = sp.owner_id
            data.story_packet_id = sp.id
        if bundle:
            data.bundle_hash = bundle.bundle_hash
            data.bundle_type = bundle.bundle_type
            data.channel_package_id = bundle.channel_package_id
        enriched.append(data)

    return enriched


# ── 接口 ──

@router.get("/tasks", response_model=PaginatedApprovalResponse, summary="签发任务列表", description="分页获取签发任务队列。支持 view 参数筛选：pending（待我处理）/ initiated（我发起的）/ returned（我退回的）。")
async def list_approval_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    view: str | None = Query(None, description="pending / initiated / returned"),
    mine_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(ApprovalTask)

    if status:
        query = query.where(ApprovalTask.status == status)

    query = query.order_by(ApprovalTask.created_at.desc())
    result = await db.execute(query)
    tasks = list(result.scalars().all())
    visible_bundle_ids = await _get_visible_bundle_ids(db, current_user)
    tasks = [t for t in tasks if t.review_bundle_id in visible_bundle_ids]

    if view == "pending":
        tasks = [
            t for t in tasks
            if t.status in ("pending", "in_review") and _is_task_for_user(t, current_user)
        ]
    elif view == "initiated":
        bundle_ids = [t.review_bundle_id for t in tasks]
        submitted_bundle_ids: set[str] = set()
        if bundle_ids:
            bundle_result = await db.execute(
                select(ReviewBundle.id).where(
                    ReviewBundle.id.in_(bundle_ids),
                    ReviewBundle.submitted_by == current_user.id,
                )
            )
            submitted_bundle_ids = set(bundle_result.scalars().all())
        tasks = [t for t in tasks if t.review_bundle_id in submitted_bundle_ids]
    elif view == "returned":
        return_logs = await db.execute(
            select(DecisionLog.approval_task_id).where(
                DecisionLog.signer_id == current_user.id,
                DecisionLog.action == "return",
            )
        )
        returned_task_ids = set(return_logs.scalars().all())
        tasks = [t for t in tasks if t.id in returned_task_ids]

    if mine_only:
        tasks = [t for t in tasks if _is_task_for_user(t, current_user)]

    total = len(tasks)
    start = (page - 1) * page_size
    end = start + page_size
    page_tasks = tasks[start:end]

    enriched = await _enrich_tasks(page_tasks, db)
    return PaginatedApprovalResponse(items=enriched, total=total, page=page, page_size=page_size)


@router.get("/tasks/{task_id}", response_model=EnrichedApprovalTaskResponse, summary="签发任务详情", description="获取单个签发任务详情，包含关联的 Story Packet 和 Review Bundle 信息。")
async def get_approval_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await db.get(ApprovalTask, task_id)
    if not task:
        raise NotFoundError("签发任务", str(task_id))
    visible_bundle_ids = await _get_visible_bundle_ids(db, current_user)
    if task.review_bundle_id not in visible_bundle_ids:
        raise NotFoundError("签发任务", str(task_id))
    enriched = await _enrich_tasks([task], db)
    return enriched[0]


@router.post(
    "/tasks/{task_id}/decide",
    response_model=DecisionLogResponse,
    responses=DECIDE_APPROVAL_ERROR_RESPONSES,
    summary="执行签发决策",
    description="执行签发决策（approve/return/escalate/hold/reject）。L2/L3 风险等级必须填写 decision_reason；覆盖 AI 建议时必须填写 override_reason。",
)
async def decide_approval(
    task_id: str,
    req: DecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await db.get(ApprovalTask, task_id)
    if not task:
        raise NotFoundError("签发任务", str(task_id))
    visible_bundle_ids = await _get_visible_bundle_ids(db, current_user)
    if task.review_bundle_id not in visible_bundle_ids:
        raise NotFoundError("签发任务", str(task_id))

    if task.status in ("approved", "cancelled"):
        raise ApprovalError(f"任务已处于 {task.status} 状态，无法操作")

    bundle = await db.get(ReviewBundle, task.review_bundle_id)
    if not bundle or bundle.status != "active":
        raise ApprovalError("关联的送审快照包已失效，请重新提交送审")

    valid_actions = {"approve", "return", "escalate", "hold", "reject"}
    if req.action not in valid_actions:
        raise ApprovalError(f"无效的决策动作，允许: {valid_actions}")

    if req.override_ai_flag and not req.override_reason:
        raise ApprovalError("覆盖 AI 建议时必须填写 override 理由")

    # return_category is recommended but not strictly required
    # Frontend may not always provide it

    # outline 规则 1：L2/L3 高风险签发必须填写决策理由
    risk_level = "L0"
    if bundle.story_packet_id:
        sp = await db.get(StoryPacket, bundle.story_packet_id)
        if sp:
            risk_level = sp.risk_level
    if risk_level in ("L2", "L3") and req.action in ("approve", "return", "reject") and not req.decision_reason:
        raise ApprovalError(f"{risk_level} 风险等级内容签发必须填写决策理由")

    decision_log = DecisionLog(
        approval_task_id=task.id,
        review_bundle_id=task.review_bundle_id,
        signer_id=current_user.id,
        signer_role=list(_parse_roles(current_user.roles))[0] if _parse_roles(current_user.roles) else "unknown",
        action=req.action,
        decision_reason=req.decision_reason,
        override_ai_flag=req.override_ai_flag,
        override_reason=req.override_reason,
        return_category=req.return_category,
    )
    db.add(decision_log)

    action_to_status = {
        "approve": "approved",
        "return": "returned",
        "escalate": "escalated",
        "hold": "held",
        "reject": "rejected",
    }
    task.status = action_to_status.get(req.action, task.status)
    task.completed_at = datetime.utcnow() if req.action in ("approve", "return", "reject") else None

    await event_audit_service.append_event(
        db,
        actor_id=current_user.id,
        actor_type="human",
        action="approval_decision_made",
        object_type="approval_task",
        object_id=task.id,
        details={
            "review_bundle_id": task.review_bundle_id,
            "decision_action": req.action,
            "task_status": task.status,
            "decision_reason": req.decision_reason,
            "return_category": req.return_category,
        },
        override_ai_flag=req.override_ai_flag,
        override_reason=req.override_reason,
    )

    await db.flush()
    await db.refresh(decision_log)
    return decision_log


@router.get("/decision-logs", response_model=list[DecisionLogResponse], summary="签发记录查询（只读）", description="查询签发决策日志，可按 review_bundle_id、approval_task_id 或 event_case_id 筛选。")
async def list_decision_logs(
    review_bundle_id: str | None = None,
    approval_task_id: str | None = None,
    event_case_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    visible_bundle_ids = await _get_visible_bundle_ids(db, current_user)
    query = select(DecisionLog)
    if visible_bundle_ids:
        query = query.where(DecisionLog.review_bundle_id.in_(visible_bundle_ids))
    else:
        return []
    if review_bundle_id:
        query = query.where(DecisionLog.review_bundle_id == review_bundle_id)
    if approval_task_id:
        query = query.where(DecisionLog.approval_task_id == approval_task_id)
    if event_case_id:
        # Join through ReviewBundle → StoryPacket to filter by event_case_id
        query = query.join(ReviewBundle, DecisionLog.review_bundle_id == ReviewBundle.id)\
                      .join(StoryPacket, ReviewBundle.story_packet_id == StoryPacket.id)\
                      .where(StoryPacket.event_case_id == event_case_id)
    query = query.order_by(DecisionLog.created_at.desc()).limit(100)
    result = await db.execute(query)
    logs = list(result.scalars().all())
    if not logs:
        return []

    bundle_ids = list({log.review_bundle_id for log in logs})
    bundle_result = await db.execute(select(ReviewBundle).where(ReviewBundle.id.in_(bundle_ids)))
    bundles = {bundle.id: bundle for bundle in bundle_result.scalars().all()}

    story_packet_ids = list({bundle.story_packet_id for bundle in bundles.values() if bundle.story_packet_id})
    story_packets: dict[str, StoryPacket] = {}
    if story_packet_ids:
        sp_result = await db.execute(select(StoryPacket).where(StoryPacket.id.in_(story_packet_ids)))
        story_packets = {packet.id: packet for packet in sp_result.scalars().all()}

    enriched: list[DecisionLogResponse] = []
    for log in logs:
        bundle = bundles.get(log.review_bundle_id)
        packet = story_packets.get(bundle.story_packet_id) if bundle and bundle.story_packet_id else None
        item = DecisionLogResponse.model_validate(log)
        if bundle:
            item.bundle_type = bundle.bundle_type
        if packet:
            item.story_packet_id = packet.id
            item.story_packet_title = packet.title
        enriched.append(item)
    return enriched
