"""今日概览仪表盘 API。"""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.event_case import EventCase
from app.models.story_packet import StoryPacket
from app.models.approval_task import ApprovalTask
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter()


class DashboardStats(BaseModel):
    active_events: int
    in_progress_packets: int
    pending_approval: int
    published_today: int
    high_risk_count: int


class HighPriorityEvent(BaseModel):
    id: str
    title: str
    risk_level: str
    status: str
    desk: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentActivity(BaseModel):
    timestamp: datetime
    agent_name: str
    action: str
    object_type: str
    object_id: str
    summary: str


class SLAAlert(BaseModel):
    task_id: str
    story_packet_title: str
    approval_stage: str
    sla_status: str  # overdue / near
    minutes_remaining: int | None
    minutes_overdue: int | None


class DashboardResponse(BaseModel):
    stats: DashboardStats
    high_priority_events: list[HighPriorityEvent]
    agent_activities: list[AgentActivity]
    sla_alerts: list[SLAAlert]


@router.get("/stats", response_model=DashboardStats, summary="仪表盘统计数据")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取仪表盘统计卡片数据（按团队隔离）"""

    # 团队隔离：获取可见的事件ID范围
    if current_user.org_id:
        org_member_ids = (await db.execute(
            select(User.id).where(User.org_id == current_user.org_id)
        )).scalars().all()
        event_filter = EventCase.owner_id.in_(org_member_ids)
    else:
        event_filter = EventCase.owner_id == current_user.id

    # 可见的事件ID
    visible_event_ids_result = await db.execute(
        select(EventCase.id).where(EventCase.archived_at.is_(None)).where(event_filter)
    )
    visible_event_ids = [r[0] for r in visible_event_ids_result.fetchall()]

    if current_user.org_id:
        visible_owner_ids = list((await db.execute(
            select(User.id).where(User.org_id == current_user.org_id)
        )).scalars().all())
        if not visible_owner_ids:
            visible_owner_ids = [current_user.id]
    else:
        visible_owner_ids = [current_user.id]

    # 活跃事件数（包含 candidate, triaging, active, monitoring —— 与事件列表页一致）
    active_events = await db.scalar(
        select(func.count(EventCase.id))
        .where(EventCase.status.in_(["candidate", "active", "triaging", "monitoring"]))
        .where(EventCase.archived_at.is_(None))
        .where(event_filter)
    ) or 0

    # 进行中任务包数（团队可见口径，与任务包列表可见范围保持一致）
    packet_visibility = [StoryPacket.owner_id.in_(visible_owner_ids)]
    if visible_event_ids:
        packet_visibility.append(StoryPacket.event_case_id.in_(visible_event_ids))
    in_progress_packets = await db.scalar(
        select(func.count(StoryPacket.id))
        .where(or_(*packet_visibility))
        .where(StoryPacket.status.notin_(["published", "killed", "archived"]))
    ) or 0

    # 待签发数（可见事件下的）
    if visible_event_ids:
        visible_sp_ids_result = await db.execute(
            select(StoryPacket.id).where(StoryPacket.event_case_id.in_(visible_event_ids))
        )
        visible_sp_ids = [r[0] for r in visible_sp_ids_result.fetchall()]
    else:
        visible_sp_ids = []

    from app.models.review_bundle import ReviewBundle
    from app.api.v1.approvals import _is_task_for_user

    if visible_sp_ids:
        visible_bundle_ids_result = await db.execute(
            select(ReviewBundle.id).where(ReviewBundle.story_packet_id.in_(visible_sp_ids))
        )
        visible_bundle_ids = [r[0] for r in visible_bundle_ids_result.fetchall()]
    else:
        visible_bundle_ids = []

    if visible_bundle_ids:
        pending_tasks_result = await db.execute(
            select(ApprovalTask)
            .where(ApprovalTask.review_bundle_id.in_(visible_bundle_ids))
            .where(ApprovalTask.status.in_(["pending", "in_review"]))
        )
        pending_tasks = list(pending_tasks_result.scalars().all())
        pending_approval = len([t for t in pending_tasks if _is_task_for_user(t, current_user)])
    else:
        pending_approval = 0

    # 今日发布数
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    if visible_event_ids:
        published_today = await db.scalar(
            select(func.count(StoryPacket.id))
            .where(StoryPacket.event_case_id.in_(visible_event_ids))
            .where(StoryPacket.status == "published")
            .where(StoryPacket.updated_at >= today_start)
        ) or 0
    else:
        published_today = 0

    # 高风险数
    if visible_event_ids:
        high_risk_count = await db.scalar(
            select(func.count(StoryPacket.id))
            .where(StoryPacket.event_case_id.in_(visible_event_ids))
            .where(StoryPacket.risk_level.in_(["L2", "L3"]))
            .where(StoryPacket.status.notin_(["published", "killed", "archived"]))
        ) or 0
    else:
        high_risk_count = 0

    return DashboardStats(
        active_events=active_events,
        in_progress_packets=in_progress_packets,
        pending_approval=pending_approval,
        published_today=published_today,
        high_risk_count=high_risk_count,
    )


@router.get("/high-priority-events", response_model=list[HighPriorityEvent], summary="高优先级事件")
async def get_high_priority_events(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取高优先级事件列表（L2/L3 风险等级，按团队隔离）"""
    # 团队隔离
    if current_user.org_id:
        org_member_ids = (await db.execute(
            select(User.id).where(User.org_id == current_user.org_id)
        )).scalars().all()
        owner_filter = EventCase.owner_id.in_(org_member_ids)
    else:
        owner_filter = EventCase.owner_id == current_user.id

    result = await db.execute(
        select(EventCase)
        .where(EventCase.risk_level.in_(["L2", "L3"]))
        .where(EventCase.status.in_(["active", "triaging"]))
        .where(owner_filter)
        .order_by(EventCase.updated_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    return [HighPriorityEvent.model_validate(e) for e in events]


@router.get("/sla-alerts", response_model=list[SLAAlert], summary="SLA告警")
async def get_sla_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取 SLA 告警列表（超时或临近超时的审批任务）"""
    now = datetime.utcnow()
    near_threshold = now + timedelta(hours=1)

    # 查询有 SLA 截止时间的待处理任务
    from app.models.review_bundle import ReviewBundle

    result = await db.execute(
        select(ApprovalTask)
        .where(ApprovalTask.status.in_(["pending", "in_review"]))
        .where(ApprovalTask.sla_deadline.isnot(None))
    )
    tasks = result.scalars().all()

    # 预加载 review_bundle → story_packet 标题映射
    bundle_ids = list({t.review_bundle_id for t in tasks})
    title_map: dict[str, str] = {}
    if bundle_ids:
        for bid in bundle_ids:
            rb = await db.get(ReviewBundle, bid)
            if rb:
                sp = await db.get(StoryPacket, rb.story_packet_id)
                if sp:
                    title_map[bid] = sp.title
    
    alerts = []
    for task in tasks:
        if not task.sla_deadline:
            continue

        sp_title = title_map.get(task.review_bundle_id, f"任务 {task.id[:8]}")

        sla_deadline = task.sla_deadline
        if sla_deadline.tzinfo is None:
            sla_deadline = sla_deadline.replace(tzinfo=timezone.utc)

        if sla_deadline < now:
            # 已超时
            overdue_minutes = int((now - sla_deadline).total_seconds() / 60)
            alerts.append(SLAAlert(
                task_id=task.id,
                story_packet_title=sp_title,
                approval_stage=task.approval_stage,
                sla_status="overdue",
                minutes_remaining=None,
                minutes_overdue=overdue_minutes,
            ))
        elif sla_deadline < near_threshold:
            # 临近超时
            remaining_minutes = int((sla_deadline - now).total_seconds() / 60)
            alerts.append(SLAAlert(
                task_id=task.id,
                story_packet_title=sp_title,
                approval_stage=task.approval_stage,
                sla_status="near",
                minutes_remaining=remaining_minutes,
                minutes_overdue=None,
            ))

    # 按紧急程度排序
    alerts.sort(key=lambda x: (x.sla_status != "overdue", x.minutes_overdue or 0, x.minutes_remaining or 999))
    return alerts


class SidebarCountsResponse(BaseModel):
    event_cases: int
    story_packets: int
    pending_me: int
    my_submitted: int
    my_returned: int
    sign_off_badge: int


@router.get("/sidebar-counts", response_model=SidebarCountsResponse, summary="侧边栏计数")
async def get_sidebar_counts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取侧边栏各菜单项的真实计数（按团队隔离）"""
    import json

    # 团队隔离
    if current_user.org_id:
        org_member_ids = (await db.execute(
            select(User.id).where(User.org_id == current_user.org_id)
        )).scalars().all()
        event_owner_filter = EventCase.owner_id.in_(org_member_ids)
    else:
        event_owner_filter = EventCase.owner_id == current_user.id

    # 事件案卷数（非归档，团队可见）
    event_cases = await db.scalar(
        select(func.count(EventCase.id)).where(EventCase.archived_at.is_(None)).where(event_owner_filter)
    ) or 0

    # 可见事件ID
    visible_event_ids_result = await db.execute(
        select(EventCase.id).where(EventCase.archived_at.is_(None)).where(event_owner_filter)
    )
    visible_event_ids = [r[0] for r in visible_event_ids_result.fetchall()]

    if current_user.org_id:
        visible_owner_ids = list((await db.execute(
            select(User.id).where(User.org_id == current_user.org_id)
        )).scalars().all())
        if not visible_owner_ids:
            visible_owner_ids = [current_user.id]
    else:
        visible_owner_ids = [current_user.id]

    # 全部可见任务包数（非归档，团队口径与任务包列表一致）
    packet_visibility = [StoryPacket.owner_id.in_(visible_owner_ids)]
    if visible_event_ids:
        packet_visibility.append(StoryPacket.event_case_id.in_(visible_event_ids))
    story_packets = await db.scalar(
        select(func.count(StoryPacket.id))
        .where(StoryPacket.status != "archived")
        .where(or_(*packet_visibility))
    ) or 0

    # 待签发任务
    result = await db.execute(
        select(ApprovalTask).where(ApprovalTask.status.in_(["pending", "in_review"]))
    )
    all_pending_tasks = list(result.scalars().all())

    user_roles = set()
    if current_user.roles:
        raw = current_user.roles
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    user_roles = set(parsed)
            except Exception:
                pass
        elif isinstance(raw, list):
            user_roles = set(raw)

    pending_me = 0
    for task in all_pending_tasks:
        slots = task.signer_slots
        if isinstance(slots, str):
            try:
                slots = json.loads(slots)
            except Exception:
                slots = []
        if not isinstance(slots, list):
            continue
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            if slot.get("user_id") == current_user.id:
                pending_me += 1
                break
            role = slot.get("role")
            if role and role in user_roles and slot.get("status") == "pending":
                pending_me += 1
                break

    # 我发起的
    from app.models.review_bundle import ReviewBundle as RB
    my_bundle_result = await db.execute(
        select(RB.id).where(RB.submitted_by == current_user.id)
    )
    my_bundle_ids = set(my_bundle_result.scalars().all())

    task_result = await db.execute(select(ApprovalTask))
    all_tasks = list(task_result.scalars().all())
    my_submitted = len([t for t in all_tasks if t.review_bundle_id in my_bundle_ids])

    # 我退回的
    from app.models.decision_log import DecisionLog
    return_logs = await db.execute(
        select(DecisionLog.approval_task_id).where(
            DecisionLog.signer_id == current_user.id,
            DecisionLog.action == "return",
        )
    )
    my_returned = len(set(return_logs.scalars().all()))

    return SidebarCountsResponse(
        event_cases=event_cases,
        story_packets=story_packets,
        pending_me=pending_me,
        my_submitted=my_submitted,
        my_returned=my_returned,
        sign_off_badge=pending_me,
    )


@router.get("/agent-activities", response_model=list[AgentActivity], summary="Agent活动时间线")
async def get_agent_activities(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取最近的 Agent 活动时间线（从数据库审计日志读取，重启不丢失）"""
    import json as _json
    from app.models.audit_log import AuditLog

    # 团队隔离：只看当前用户可见事件的 Agent 活动
    if current_user.org_id:
        org_member_ids = (await db.execute(
            select(User.id).where(User.org_id == current_user.org_id)
        )).scalars().all()
        event_filter = EventCase.owner_id.in_(org_member_ids)
    else:
        event_filter = EventCase.owner_id == current_user.id

    visible_event_ids = list((await db.execute(
        select(EventCase.id).where(EventCase.archived_at.is_(None)).where(event_filter)
    )).scalars().all())

    if not visible_event_ids:
        return []

    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.actor_type == "agent")
        .where(AuditLog.object_type == "event_case")
        .where(AuditLog.object_id.in_(visible_event_ids))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()

    activities = []
    for log in logs:
        details = log.details
        if isinstance(details, str):
            try:
                details = _json.loads(details)
            except Exception:
                details = {}
        if not isinstance(details, dict):
            details = {}
        agent_name = details.get("agent_name", "Unknown Agent")
        summary = details.get("summary", f"{agent_name} 执行 {log.action}")
        activities.append(AgentActivity(
            timestamp=log.created_at,
            agent_name=agent_name,
            action=log.action,
            object_type=log.object_type,
            object_id=log.object_id,
            summary=summary,
        ))

    return activities
