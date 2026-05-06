"""声明式状态机引擎：通用执行器 + 配置驱动。"""

from typing import Any, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidTransitionError, BlockerExistsError, PreconditionError


@dataclass
class Transition:
    """状态迁移配置"""
    from_state: str
    to_state: str
    preconditions: list[str] = field(default_factory=list)
    action: str | None = None
    requires_approval: bool = False
    approval_stage: str | None = None
    auto_trigger: bool = False


@dataclass
class StateMachineConfig:
    """状态机配置"""
    name: str
    states: list[str]
    transitions: list[Transition]
    lateral_actions: list[str] = field(default_factory=list)


class StateMachineEngine:
    """通用状态机执行引擎"""

    def __init__(self, config: StateMachineConfig):
        self.config = config
        self._precondition_checkers: dict[str, Callable] = {}
        self._action_handlers: dict[str, Callable] = {}
        self._build_transition_map()

    def _build_transition_map(self):
        """构建状态转换映射表"""
        self._transitions: dict[tuple[str, str], Transition] = {}
        for t in self.config.transitions:
            self._transitions[(t.from_state, t.to_state)] = t

    def register_precondition(self, name: str, checker: Callable):
        """注册前置条件检查器"""
        self._precondition_checkers[name] = checker

    def register_action(self, name: str, handler: Callable):
        """注册状态迁移动作处理器"""
        self._action_handlers[name] = handler

    def get_available_transitions(self, current_state: str) -> list[str]:
        """获取当前状态可达的目标状态列表"""
        return [
            t.to_state
            for t in self.config.transitions
            if t.from_state == current_state
        ]

    async def check_preconditions(
        self,
        obj: Any,
        preconditions: list[str],
        db: AsyncSession,
        context: dict | None = None
    ) -> tuple[bool, list[str]]:
        """
        校验所有前置条件
        返回: (是否全部通过, 失败的条件列表)
        """
        failed = []
        for pc in preconditions:
            checker = self._precondition_checkers.get(pc)
            if checker is None:
                failed.append(f"{pc} (checker not registered)")
                continue
            try:
                result = await checker(obj, db, context or {})
                if not result:
                    failed.append(pc)
            except Exception as e:
                failed.append(f"{pc} (error: {str(e)})")
        return len(failed) == 0, failed

    def check_blockers(self, obj: Any) -> list[dict]:
        """
        高风险默认 fail-close：有 blocker 就不能推进
        返回未解决的 blocker 列表
        """
        blockers = getattr(obj, "blockers", None)
        if not blockers:
            return []
        
        # blockers 可能是 JSON 字符串或列表
        if isinstance(blockers, str):
            import json
            try:
                blockers = json.loads(blockers)
            except:
                return []
        
        return [b for b in blockers if not b.get("resolved", False)]

    async def attempt_transition(
        self,
        obj: Any,
        target_state: str,
        actor: Any,
        db: AsyncSession,
        context: dict | None = None,
        force: bool = False
    ) -> tuple[bool, str | None]:
        """
        尝试状态迁移
        
        流程:
        1. 查找 from=obj.status, to=target_state 的 transition 配置
        2. 逐一校验 preconditions
        3. 校验 blockers 是否为空（fail-close 规则）
        4. 如需审批，返回需要创建审批流程的标识
        5. 执行 action 回调
        6. 更新状态
        7. 返回 (成功, 错误信息/审批阶段)
        """
        current_state = getattr(obj, "status", None)
        if current_state is None:
            return False, "对象没有 status 属性"

        # 1. 查找转换配置
        transition = self._transitions.get((current_state, target_state))
        if transition is None:
            allowed = self.get_available_transitions(current_state)
            raise InvalidTransitionError(
                current_state, target_state,
                f"允许的目标状态：{allowed}"
            )

        # 2. 校验前置条件
        if transition.preconditions and not force:
            passed, failed = await self.check_preconditions(
                obj, transition.preconditions, db, context
            )
            if not passed:
                raise PreconditionError(failed)

        # 3. 校验阻塞项（kill/reopen 等特殊状态除外）
        bypass_blocker_states = {"killed", "reopened", "researching", "drafting"}
        if target_state not in bypass_blocker_states and not force:
            unresolved = self.check_blockers(obj)
            if unresolved:
                raise BlockerExistsError(unresolved)

        # 4. 如需审批，返回审批阶段
        if transition.requires_approval:
            return True, f"requires_approval:{transition.approval_stage}"

        # 5. 执行 action 回调
        if transition.action and transition.action in self._action_handlers:
            handler = self._action_handlers[transition.action]
            await handler(obj, actor, db, context or {})

        # 6. 更新状态
        obj.status = target_state
        if hasattr(obj, "updated_at"):
            obj.updated_at = datetime.utcnow()

        return True, None


# ══════════════════════════════════════════════════════════════════
# Story Packet 状态机配置
# ══════════════════════════════════════════════════════════════════

STORY_PACKET_SM_CONFIG = StateMachineConfig(
    name="story_packet",
    states=[
        "created", "researching", "verification_pending", "drafting",
        "editorial_review", "risk_review", "channel_packaging",
        "channel_review", "ready_to_publish", "published",
        "monitoring", "reopened", "killed", "archived"
    ],
    transitions=[
        Transition("created", "researching", ["has_owner"]),
        Transition("created", "killed"),
        Transition("researching", "verification_pending", ["has_evidence_pack"]),
        Transition("researching", "killed"),
        Transition("verification_pending", "drafting", ["has_claim_cards"]),
        Transition("verification_pending", "researching"),
        Transition("drafting", "editorial_review", ["has_draft_version"], 
                   requires_approval=True, approval_stage="editorial_review"),
        Transition("drafting", "verification_pending"),
        Transition("drafting", "killed"),
        Transition("editorial_review", "risk_review", ["editorial_approved"],
                   requires_approval=True, approval_stage="risk_review"),
        Transition("editorial_review", "drafting"),
        Transition("risk_review", "channel_packaging", ["risk_cleared"]),
        Transition("risk_review", "drafting"),
        Transition("channel_packaging", "channel_review", ["all_channels_ready"],
                   requires_approval=True, approval_stage="channel_review"),
        Transition("channel_review", "ready_to_publish", ["all_channels_approved"]),
        Transition("channel_review", "channel_packaging"),
        Transition("ready_to_publish", "published", ["human_publish_confirmed"]),
        Transition("published", "monitoring", auto_trigger=True),
        Transition("monitoring", "reopened", ["has_reopen_trigger"]),
        Transition("monitoring", "archived"),
        Transition("reopened", "researching"),
        Transition("reopened", "drafting"),
    ],
    lateral_actions=["merge", "split", "escalate_risk", "kill"]
)


# ══════════════════════════════════════════════════════════════════
# Event Case 状态机配置
# ══════════════════════════════════════════════════════════════════

EVENT_CASE_SM_CONFIG = StateMachineConfig(
    name="event_case",
    states=["candidate", "triaging", "active", "monitoring", "archived"],
    transitions=[
        Transition("candidate", "triaging"),
        Transition("candidate", "archived"),
        Transition("triaging", "active", ["has_risk_assessment"]),
        Transition("triaging", "archived"),
        Transition("active", "monitoring"),
        Transition("monitoring", "active", ["has_new_development"]),
        Transition("monitoring", "archived"),
    ],
    lateral_actions=["merge", "split", "escalate", "reopen"]
)


# ══════════════════════════════════════════════════════════════════
# Channel Package 状态机配置
# ══════════════════════════════════════════════════════════════════

CHANNEL_PACKAGE_SM_CONFIG = StateMachineConfig(
    name="channel_package",
    states=["draft", "review_pending", "approved", "published", "recalled", "corrected"],
    transitions=[
        Transition("draft", "review_pending", ["content_ready", "drift_check_passed"]),
        Transition("review_pending", "approved"),
        Transition("review_pending", "draft"),
        Transition("approved", "published", ["human_publish_confirmed"]),
        Transition("published", "recalled"),
        Transition("published", "corrected"),
        Transition("recalled", "corrected"),
    ]
)


# ══════════════════════════════════════════════════════════════════
# Approval Task 状态机配置
# ══════════════════════════════════════════════════════════════════

APPROVAL_TASK_SM_CONFIG = StateMachineConfig(
    name="approval_task",
    states=["pending", "in_review", "approved", "returned", "escalated", "held", "rejected", "cancelled"],
    transitions=[
        Transition("pending", "in_review"),
        Transition("in_review", "approved", ["all_signers_approved"]),
        Transition("in_review", "returned"),
        Transition("in_review", "escalated"),
        Transition("in_review", "held"),
        Transition("in_review", "rejected"),
        Transition("held", "in_review"),
        Transition("pending", "cancelled"),
        Transition("in_review", "cancelled"),
    ]
)


def create_story_packet_engine() -> StateMachineEngine:
    """创建并配置 Story Packet 状态机引擎"""
    engine = StateMachineEngine(STORY_PACKET_SM_CONFIG)
    
    # 注册前置条件检查器
    async def has_owner(obj, db, ctx):
        return obj.owner_id is not None
    
    async def has_evidence_pack(obj, db, ctx):
        from sqlalchemy import select, func
        from app.models.evidence_pack import EvidencePack
        count = await db.scalar(
            select(func.count(EvidencePack.id))
            .where(EvidencePack.story_packet_id == obj.id)
        )
        return count > 0
    
    async def has_claim_cards(obj, db, ctx):
        from sqlalchemy import select, func
        from app.models.claim_card import ClaimCard
        count = await db.scalar(
            select(func.count(ClaimCard.id))
            .where(ClaimCard.story_packet_id == obj.id)
        )
        return count > 0
    
    async def has_draft_version(obj, db, ctx):
        from sqlalchemy import select, func
        from app.models.draft_version import DraftVersion
        count = await db.scalar(
            select(func.count(DraftVersion.id))
            .where(DraftVersion.story_packet_id == obj.id)
        )
        return count > 0
    
    async def editorial_approved(obj, db, ctx):
        # 检查是否存在已通过的编辑审批
        return ctx.get("editorial_approved", False)
    
    async def risk_cleared(obj, db, ctx):
        # 低风险或已通过风险审核
        return obj.risk_level == "L0" or ctx.get("risk_cleared", False)
    
    async def all_channels_ready(obj, db, ctx):
        from sqlalchemy import select, func
        from app.models.channel_package import ChannelPackage
        count = await db.scalar(
            select(func.count(ChannelPackage.id))
            .where(ChannelPackage.story_packet_id == obj.id)
            .where(ChannelPackage.status == "draft")
        )
        return count > 0
    
    async def all_channels_approved(obj, db, ctx):
        return ctx.get("all_channels_approved", False)
    
    async def human_publish_confirmed(obj, db, ctx):
        return ctx.get("human_publish_confirmed", False)
    
    async def has_reopen_trigger(obj, db, ctx):
        from sqlalchemy import select, func
        from app.models.correction_ticket import CorrectionTicket
        count = await db.scalar(
            select(func.count(CorrectionTicket.id))
            .where(CorrectionTicket.story_packet_id == obj.id)
            .where(CorrectionTicket.status == "open")
        )
        return count > 0
    
    engine.register_precondition("has_owner", has_owner)
    engine.register_precondition("has_evidence_pack", has_evidence_pack)
    engine.register_precondition("has_claim_cards", has_claim_cards)
    engine.register_precondition("has_draft_version", has_draft_version)
    engine.register_precondition("editorial_approved", editorial_approved)
    engine.register_precondition("risk_cleared", risk_cleared)
    engine.register_precondition("all_channels_ready", all_channels_ready)
    engine.register_precondition("all_channels_approved", all_channels_approved)
    engine.register_precondition("human_publish_confirmed", human_publish_confirmed)
    engine.register_precondition("has_reopen_trigger", has_reopen_trigger)
    
    return engine


def create_event_case_engine() -> StateMachineEngine:
    """创建并配置 Event Case 状态机引擎"""
    engine = StateMachineEngine(EVENT_CASE_SM_CONFIG)

    async def has_risk_assessment(obj, db, ctx):
        return obj.risk_level is not None and obj.risk_level != ""

    async def has_new_development(obj, db, ctx):
        return ctx.get("has_new_development", False)

    engine.register_precondition("has_risk_assessment", has_risk_assessment)
    engine.register_precondition("has_new_development", has_new_development)

    return engine


def create_channel_package_engine() -> StateMachineEngine:
    """创建并配置 Channel Package 状态机引擎"""
    engine = StateMachineEngine(CHANNEL_PACKAGE_SM_CONFIG)

    async def content_ready(obj, db, ctx):
        # 检查渠道包是否有实际内容
        content = getattr(obj, "content", None)
        if not content:
            return False
        if isinstance(content, str):
            import json
            try:
                content = json.loads(content)
            except Exception:
                return False
        return bool(content)

    async def drift_check_passed(obj, db, ctx):
        drift_score = getattr(obj, "drift_score", None)
        drift_threshold = getattr(obj, "drift_threshold", 0.30)
        if drift_score is None:
            return True  # 尚未计算漂移分时允许通过
        return drift_score <= drift_threshold

    async def human_publish_confirmed(obj, db, ctx):
        return ctx.get("human_publish_confirmed", False)

    engine.register_precondition("content_ready", content_ready)
    engine.register_precondition("drift_check_passed", drift_check_passed)
    engine.register_precondition("human_publish_confirmed", human_publish_confirmed)

    return engine


# 全局引擎实例
story_packet_engine = create_story_packet_engine()
event_case_engine = create_event_case_engine()
channel_package_engine = create_channel_package_engine()
