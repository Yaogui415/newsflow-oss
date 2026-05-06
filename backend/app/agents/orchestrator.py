"""Orchestrator Agent：总控编排 Agent，负责协调全链路状态流和Agent调度。"""

import uuid
import json
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from enum import Enum

from app.core.config import settings


class WorkflowStage(str, Enum):
    """工作流阶段"""
    SOURCE_INGESTION = "source_ingestion"
    DEDUP_CLUSTER = "dedup_cluster"
    TRIAGE = "triage"
    HUMAN_GATE_PROJECT = "human_gate_project"
    CREATE_STORY_PACKET = "create_story_packet"
    EVIDENCE_STRUCTURING = "evidence_structuring"
    COGNITIVE_PARALLEL = "cognitive_parallel"
    HUMAN_SUPPLEMENT = "human_supplement"
    REDACTION_GATE2 = "redaction_gate2"
    DRAFTING = "drafting"
    REDACTION_GATE3 = "redaction_gate3"
    EDITORIAL_REVIEW = "editorial_review"
    RISK_REVIEW = "risk_review"
    CHANNEL_ADAPTATION = "channel_adaptation"
    CHANNEL_REVIEW = "channel_review"
    HUMAN_GATE_PUBLISH = "human_gate_publish"
    PUBLISH = "publish"
    POST_PUBLISH_MONITOR = "post_publish_monitor"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkflowState:
    """全局工作流状态"""
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_case_id: str | None = None
    story_packet_id: str | None = None
    current_stage: WorkflowStage = WorkflowStage.SOURCE_INGESTION
    source_items: list[dict] = field(default_factory=list)
    evidence_pack: dict | None = None
    claim_cards: list[dict] = field(default_factory=list)
    event_graph: dict | None = None
    risk_report: dict | None = None
    draft_version: dict | None = None
    channel_packages: list[dict] = field(default_factory=list)
    review_bundle: dict | None = None
    approval_tasks: list[dict] = field(default_factory=list)
    blockers: list[dict] = field(default_factory=list)
    human_decisions: list[dict] = field(default_factory=list)
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = field(default_factory=lambda: datetime.utcnow())

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "event_case_id": self.event_case_id,
            "story_packet_id": self.story_packet_id,
            "current_stage": self.current_stage.value,
            "source_items_count": len(self.source_items),
            "has_evidence_pack": self.evidence_pack is not None,
            "claim_cards_count": len(self.claim_cards),
            "has_event_graph": self.event_graph is not None,
            "blockers_count": len(self.blockers),
            "human_decisions_count": len(self.human_decisions),
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class AgentEvent:
    """Agent 间通信的事件消息"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    source_agent: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())
    story_packet_id: str | None = None
    event_case_id: str | None = None
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source_agent": self.source_agent,
            "timestamp": self.timestamp.isoformat(),
            "story_packet_id": self.story_packet_id,
            "event_case_id": self.event_case_id,
            "payload": self.payload,
        }


# 事件类型定义
EVENT_TYPES = {
    "source_item_ingested": "新线索入库",
    "cluster_decided": "聚类决策完成",
    "triage_completed": "分诊评估完成",
    "evidence_pack_ready": "证据包就绪",
    "evidence_pack_updated": "证据包更新",
    "verification_completed": "核验完成",
    "event_graph_ready": "事件图谱就绪",
    "gate1_completed": "脱敏门1完成",
    "gate2_completed": "脱敏门2完成",
    "gate3_completed": "脱敏门3完成",
    "risk_report_ready": "风险报告就绪",
    "blocker_detected": "发现阻塞项",
    "blocker_resolved": "阻塞项已解决",
    "draft_generated": "初稿生成",
    "draft_updated": "草稿更新",
    "channel_packages_ready": "渠道包就绪",
    "review_bundle_created": "送审包创建",
    "approval_task_created": "签发任务创建",
    "approval_decided": "签发决策完成",
    "bundle_superseded": "送审包失效",
    "published": "已发布",
    "correction_needed": "需要更正",
    "human_decision_made": "人工决策完成",
    "material_uploaded": "新材料上传",
}


# SLA 规则配置
SLA_RULES = {
    "editorial_review": {"default_hours": 4, "urgent_hours": 1},
    "risk_review": {"default_hours": 8, "urgent_hours": 2},
    "channel_review": {"default_hours": 2, "urgent_hours": 0.5},
    "final_signoff": {"default_hours": 2, "urgent_hours": 0.5},
}


# 状态转换规则
STAGE_TRANSITIONS = {
    WorkflowStage.SOURCE_INGESTION: [WorkflowStage.DEDUP_CLUSTER],
    WorkflowStage.DEDUP_CLUSTER: [WorkflowStage.TRIAGE],
    WorkflowStage.TRIAGE: [WorkflowStage.HUMAN_GATE_PROJECT],
    WorkflowStage.HUMAN_GATE_PROJECT: [WorkflowStage.CREATE_STORY_PACKET, WorkflowStage.COMPLETED],
    WorkflowStage.CREATE_STORY_PACKET: [WorkflowStage.EVIDENCE_STRUCTURING],
    WorkflowStage.EVIDENCE_STRUCTURING: [WorkflowStage.COGNITIVE_PARALLEL],
    WorkflowStage.COGNITIVE_PARALLEL: [WorkflowStage.HUMAN_SUPPLEMENT],
    WorkflowStage.HUMAN_SUPPLEMENT: [WorkflowStage.REDACTION_GATE2],
    WorkflowStage.REDACTION_GATE2: [WorkflowStage.DRAFTING, WorkflowStage.HUMAN_SUPPLEMENT],
    WorkflowStage.DRAFTING: [WorkflowStage.REDACTION_GATE3],
    WorkflowStage.REDACTION_GATE3: [WorkflowStage.EDITORIAL_REVIEW, WorkflowStage.DRAFTING],
    WorkflowStage.EDITORIAL_REVIEW: [WorkflowStage.RISK_REVIEW, WorkflowStage.DRAFTING],
    WorkflowStage.RISK_REVIEW: [WorkflowStage.CHANNEL_ADAPTATION, WorkflowStage.DRAFTING],
    WorkflowStage.CHANNEL_ADAPTATION: [WorkflowStage.CHANNEL_REVIEW],
    WorkflowStage.CHANNEL_REVIEW: [WorkflowStage.HUMAN_GATE_PUBLISH, WorkflowStage.CHANNEL_ADAPTATION],
    WorkflowStage.HUMAN_GATE_PUBLISH: [WorkflowStage.PUBLISH, WorkflowStage.COMPLETED],
    WorkflowStage.PUBLISH: [WorkflowStage.POST_PUBLISH_MONITOR],
    WorkflowStage.POST_PUBLISH_MONITOR: [WorkflowStage.COMPLETED],
}


class OrchestratorAgent:
    """总控编排 Agent"""

    def __init__(self):
        self._workflows: dict[str, WorkflowState] = {}
        self._event_handlers: dict[str, list[Callable]] = {}
        self._pending_human_decisions: dict[str, dict] = {}

    async def create_workflow(
        self, event_case_id: str | None = None, source_items: list[dict] | None = None
    ) -> WorkflowState:
        """创建新的工作流"""
        state = WorkflowState(
            event_case_id=event_case_id,
            source_items=source_items or [],
        )
        self._workflows[state.workflow_id] = state
        return state

    async def get_workflow(self, workflow_id: str) -> WorkflowState | None:
        """获取工作流状态"""
        return self._workflows.get(workflow_id)

    async def advance_workflow(self, workflow_id: str) -> WorkflowState:
        """推进工作流到下一阶段"""
        state = self._workflows.get(workflow_id)
        if not state:
            raise ValueError(f"Workflow {workflow_id} not found")

        # 检查是否有阻塞项
        if state.blockers:
            state.error = f"Workflow blocked by {len(state.blockers)} blockers"
            return state

        # 获取当前阶段的下一阶段
        next_stages = STAGE_TRANSITIONS.get(state.current_stage, [])
        if not next_stages:
            state.current_stage = WorkflowStage.COMPLETED
            return state

        # 根据条件选择下一阶段
        next_stage = await self._route_next_stage(state, next_stages)
        state.current_stage = next_stage
        state.updated_at = datetime.utcnow()

        # 执行阶段对应的 Agent
        await self._execute_stage(state)

        return state

    async def _route_next_stage(
        self, state: WorkflowState, candidates: list[WorkflowStage]
    ) -> WorkflowStage:
        """根据状态条件路由到下一阶段"""
        if len(candidates) == 1:
            return candidates[0]

        current = state.current_stage

        # 脱敏门2：AI生成内容脱敏审查，有 blocker 退回人工补充
        if current == WorkflowStage.REDACTION_GATE2:
            if state.blockers:
                return WorkflowStage.HUMAN_SUPPLEMENT
            return WorkflowStage.DRAFTING

        # 脱敏门3：有 blocker 退回修改
        if current == WorkflowStage.REDACTION_GATE3:
            if state.blockers:
                return WorkflowStage.DRAFTING
            return WorkflowStage.EDITORIAL_REVIEW

        # 编辑审：根据决策路由
        if current == WorkflowStage.EDITORIAL_REVIEW:
            decision = self._get_latest_decision(state, "editorial_review")
            if decision:
                if decision.get("action") == "approved":
                    return WorkflowStage.RISK_REVIEW
                elif decision.get("action") == "returned":
                    return WorkflowStage.DRAFTING
            return WorkflowStage.RISK_REVIEW

        # 风险审：根据决策路由
        if current == WorkflowStage.RISK_REVIEW:
            decision = self._get_latest_decision(state, "risk_review")
            if decision:
                if decision.get("action") == "approved":
                    return WorkflowStage.CHANNEL_ADAPTATION
                elif decision.get("action") == "returned":
                    return WorkflowStage.DRAFTING
            return WorkflowStage.CHANNEL_ADAPTATION

        # 人审闸口：根据人工决策路由
        if current == WorkflowStage.HUMAN_GATE_PROJECT:
            decision = self._get_latest_decision(state, "project_decision")
            if decision and decision.get("action") in ("deferred", "rejected"):
                return WorkflowStage.COMPLETED
            return WorkflowStage.CREATE_STORY_PACKET

        if current == WorkflowStage.HUMAN_GATE_PUBLISH:
            decision = self._get_latest_decision(state, "publish_decision")
            if decision and decision.get("action") == "hold":
                return WorkflowStage.COMPLETED
            return WorkflowStage.PUBLISH

        return candidates[0]

    def _get_latest_decision(self, state: WorkflowState, decision_type: str) -> dict | None:
        """获取最新的指定类型决策"""
        for decision in reversed(state.human_decisions):
            if decision.get("type") == decision_type:
                return decision
        return None

    async def _execute_stage(self, state: WorkflowState):
        """执行当前阶段对应的 Agent"""
        stage = state.current_stage

        # 导入 Agent（延迟导入避免循环依赖）
        from app.agents import (
            source_monitor_agent,
            dedup_cluster_agent,
            triage_agent,
            evidence_structuring_agent,
            relationship_investigation_agent,
            verification_agent,
            redaction_risk_agent,
            drafting_agent,
            channel_adaptation_agent,
        )

        try:
            if stage == WorkflowStage.SOURCE_INGESTION:
                # Source Monitor 已在外部执行，这里只记录
                pass

            elif stage == WorkflowStage.DEDUP_CLUSTER:
                for source in state.source_items:
                    result = await dedup_cluster_agent.process_source(
                        source.get("content", ""),
                        source.get("id", ""),
                    )
                    source["cluster_result"] = result.to_dict()

            elif stage == WorkflowStage.TRIAGE:
                if state.source_items:
                    content = state.source_items[0].get("content", "")
                    result = await triage_agent.assess_event(content, state.event_case_id or "")
                    state.source_items[0]["triage_result"] = result.to_dict()

            elif stage == WorkflowStage.HUMAN_GATE_PROJECT:
                # 等待人工立项决策
                await self._wait_for_human_decision(state, "project_decision")

            elif stage == WorkflowStage.CREATE_STORY_PACKET:
                state.story_packet_id = str(uuid.uuid4())

            elif stage == WorkflowStage.EVIDENCE_STRUCTURING:
                results = []
                for source in state.source_items:
                    result = await evidence_structuring_agent.extract_from_source(
                        source.get("id", ""),
                        source.get("content", ""),
                    )
                    results.append(result)
                if results:
                    merged = await evidence_structuring_agent.merge_extractions(results)
                    state.evidence_pack = await evidence_structuring_agent.build_evidence_pack(
                        state.story_packet_id or "", merged
                    )
                    state.claim_cards = await evidence_structuring_agent.generate_initial_claim_cards(merged)

            elif stage == WorkflowStage.COGNITIVE_PARALLEL:
                # 并行执行核验和关系调查
                if state.evidence_pack:
                    # 核验
                    matrix = await verification_agent.build_evidence_matrix(
                        state.story_packet_id or "",
                        state.claim_cards,
                        state.source_items,
                    )
                    state.evidence_pack["verification_matrix"] = matrix.to_dict()

                    # 关系调查
                    entities = state.evidence_pack.get("entities", [])
                    events = state.evidence_pack.get("events", [])
                    graph = await relationship_investigation_agent.build_event_graph(
                        state.event_case_id or "", entities, events
                    )
                    state.event_graph = graph.to_dict()

            elif stage == WorkflowStage.HUMAN_SUPPLEMENT:
                # 等待人工补充材料（可跳过）
                pass

            elif stage == WorkflowStage.REDACTION_GATE2:
                # 脱敏门2：AI生成内容的中间脱敏审查
                if state.evidence_pack or state.claim_cards:
                    content_to_check = json.dumps(
                        {"claims": [c.get("text", "") for c in state.claim_cards],
                         "evidence": state.evidence_pack.get("sources", []) if state.evidence_pack else []},
                        ensure_ascii=False,
                    )
                    result = await redaction_risk_agent.gate3_full_scan(content_to_check)
                    if not result.can_proceed:
                        state.blockers = result.blockers
                        self._emit_event(AgentEvent(
                            event_type="blocker_detected",
                            source_agent="redaction_risk_gate2",
                            story_packet_id=state.story_packet_id,
                            payload={"blockers": result.blockers},
                        ))
                    else:
                        self._emit_event(AgentEvent(
                            event_type="gate2_completed",
                            source_agent="redaction_risk_gate2",
                            story_packet_id=state.story_packet_id,
                        ))

            elif stage == WorkflowStage.DRAFTING:
                if state.evidence_pack:
                    draft = await drafting_agent.generate_draft(
                        angle=state.evidence_pack.get("angle", ""),
                        audience="一般读者",
                        content_type="in_depth",
                        evidence_summary=json.dumps(state.evidence_pack.get("claims", []), ensure_ascii=False),
                        verified_claims=state.claim_cards,
                    )
                    state.draft_version = draft.to_dict()

            elif stage == WorkflowStage.REDACTION_GATE3:
                if state.draft_version:
                    result = await redaction_risk_agent.gate3_full_scan(
                        state.draft_version.get("body", "")
                    )
                    state.risk_report = result.to_dict()
                    state.blockers = result.blockers
                    if not result.can_proceed:
                        self._emit_event(AgentEvent(
                            event_type="blocker_detected",
                            source_agent="redaction_risk",
                            story_packet_id=state.story_packet_id,
                            payload={"blockers": result.blockers},
                        ))

            elif stage == WorkflowStage.EDITORIAL_REVIEW:
                await self._wait_for_human_decision(state, "editorial_review")

            elif stage == WorkflowStage.RISK_REVIEW:
                await self._wait_for_human_decision(state, "risk_review")

            elif stage == WorkflowStage.CHANNEL_ADAPTATION:
                if state.draft_version:
                    channels = ["website", "wechat", "weibo"]
                    packages = await channel_adaptation_agent.batch_adapt(
                        state.draft_version.get("id", ""),
                        state.draft_version.get("title", ""),
                        state.draft_version.get("body", ""),
                        channels,
                    )
                    state.channel_packages = [p.to_dict() for p in packages]

            elif stage == WorkflowStage.CHANNEL_REVIEW:
                await self._wait_for_human_decision(state, "channel_review")

            elif stage == WorkflowStage.HUMAN_GATE_PUBLISH:
                await self._wait_for_human_decision(state, "publish_decision")

            elif stage == WorkflowStage.PUBLISH:
                # 发布逻辑（实际发布由外部系统完成）
                self._emit_event(AgentEvent(
                    event_type="published",
                    source_agent="orchestrator",
                    story_packet_id=state.story_packet_id,
                ))

            elif stage == WorkflowStage.POST_PUBLISH_MONITOR:
                # 发布后监测（后续实现）
                pass

        except Exception as e:
            state.error = str(e)
            self._emit_event(AgentEvent(
                event_type="agent_error",
                source_agent="orchestrator",
                payload={"error": str(e), "stage": stage.value},
            ))

    async def _wait_for_human_decision(self, state: WorkflowState, decision_type: str):
        """等待人工决策"""
        self._pending_human_decisions[state.workflow_id] = {
            "type": decision_type,
            "requested_at": datetime.utcnow().isoformat(),
        }

    async def submit_human_decision(
        self, workflow_id: str, decision_type: str, action: str, reason: str | None = None
    ) -> WorkflowState:
        """提交人工决策"""
        state = self._workflows.get(workflow_id)
        if not state:
            raise ValueError(f"Workflow {workflow_id} not found")

        decision = {
            "type": decision_type,
            "action": action,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        }
        state.human_decisions.append(decision)

        # 清除等待状态
        self._pending_human_decisions.pop(workflow_id, None)

        # 发送事件
        self._emit_event(AgentEvent(
            event_type="human_decision_made",
            source_agent="human",
            story_packet_id=state.story_packet_id,
            payload=decision,
        ))

        # 推进工作流
        return await self.advance_workflow(workflow_id)

    async def add_blocker(self, workflow_id: str, blocker: dict):
        """添加阻塞项"""
        state = self._workflows.get(workflow_id)
        if state:
            state.blockers.append(blocker)
            self._emit_event(AgentEvent(
                event_type="blocker_detected",
                source_agent="orchestrator",
                story_packet_id=state.story_packet_id,
                payload=blocker,
            ))

    async def resolve_blocker(self, workflow_id: str, blocker_id: str):
        """解决阻塞项"""
        state = self._workflows.get(workflow_id)
        if state:
            state.blockers = [b for b in state.blockers if b.get("id") != blocker_id]
            self._emit_event(AgentEvent(
                event_type="blocker_resolved",
                source_agent="orchestrator",
                story_packet_id=state.story_packet_id,
                payload={"blocker_id": blocker_id},
            ))

    def _emit_event(self, event: AgentEvent):
        """发送事件"""
        handlers = self._event_handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                pass

    def on_event(self, event_type: str, handler: Callable):
        """注册事件处理器"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    async def get_sla_status(self, workflow_id: str) -> dict:
        """获取 SLA 状态"""
        state = self._workflows.get(workflow_id)
        if not state:
            return {}

        stage = state.current_stage.value
        rules = SLA_RULES.get(stage, {"default_hours": 24})
        deadline = state.updated_at + timedelta(hours=rules["default_hours"])
        now = datetime.utcnow()

        if now > deadline:
            status = "overdue"
            minutes = int((now - deadline).total_seconds() / 60)
        elif now > deadline - timedelta(hours=1):
            status = "near"
            minutes = int((deadline - now).total_seconds() / 60)
        else:
            status = "normal"
            minutes = int((deadline - now).total_seconds() / 60)

        return {
            "workflow_id": workflow_id,
            "stage": stage,
            "status": status,
            "minutes_remaining": minutes if status != "overdue" else None,
            "minutes_overdue": minutes if status == "overdue" else None,
            "deadline": deadline.isoformat(),
        }


# 全局实例
orchestrator_agent = OrchestratorAgent()
