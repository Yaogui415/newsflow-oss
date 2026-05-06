"""Audit Agent：审计 Agent，负责全链路审计和 AI 使用记录。"""

import uuid
import json
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuditEntry:
    """审计日志条目"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())
    actor_id: str | None = None
    actor_type: str = "system"  # human / agent / system
    action: str = ""  # create / update / transition / approve / etc.
    object_type: str = ""  # story_packet / draft_version / etc.
    object_id: str = ""
    details: dict = field(default_factory=dict)
    previous_hash: str | None = None
    # AI 相关
    ai_model: str | None = None
    ai_prompt_hash: str | None = None
    ai_token_usage: dict | None = None
    # Override 相关
    override_ai_flag: bool = False
    override_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "action": self.action,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "details": self.details,
            "previous_hash": self.previous_hash,
            "ai_model": self.ai_model,
            "ai_prompt_hash": self.ai_prompt_hash,
            "ai_token_usage": self.ai_token_usage,
            "override_ai_flag": self.override_ai_flag,
            "override_reason": self.override_reason,
        }

    def compute_hash(self) -> str:
        """计算条目哈希"""
        content = json.dumps({
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "actor_id": self.actor_id,
            "action": self.action,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "details": self.details,
            "previous_hash": self.previous_hash,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()


@dataclass
class AIUsageLog:
    """AI 使用记录"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str = ""
    model_name: str = ""
    prompt_template_id: str = ""
    prompt_variables: dict = field(default_factory=dict)
    input_token_count: int = 0
    output_token_count: int = 0
    response_hash: str = ""
    latency_ms: int = 0
    related_object_type: str = ""
    related_object_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "model_name": self.model_name,
            "prompt_template_id": self.prompt_template_id,
            "input_token_count": self.input_token_count,
            "output_token_count": self.output_token_count,
            "total_tokens": self.input_token_count + self.output_token_count,
            "latency_ms": self.latency_ms,
            "related_object_type": self.related_object_type,
            "related_object_id": self.related_object_id,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class AIUsageReport:
    """AI 使用统计报告"""
    time_range: tuple[datetime, datetime]
    total_calls: int = 0
    total_tokens: int = 0
    by_model: dict = field(default_factory=dict)
    by_agent: dict = field(default_factory=dict)
    average_latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "time_range": {
                "start": self.time_range[0].isoformat(),
                "end": self.time_range[1].isoformat(),
            },
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "by_model": self.by_model,
            "by_agent": self.by_agent,
            "average_latency_ms": self.average_latency_ms,
        }


@dataclass
class ComplianceReport:
    """合规报告"""
    story_packet_id: str
    audit_entries_count: int = 0
    ai_usage_count: int = 0
    ai_override_count: int = 0
    chain_integrity_verified: bool = True
    ai_disclosure_text: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.utcnow())

    def to_dict(self) -> dict:
        return {
            "story_packet_id": self.story_packet_id,
            "audit_entries_count": self.audit_entries_count,
            "ai_usage_count": self.ai_usage_count,
            "ai_override_count": self.ai_override_count,
            "chain_integrity_verified": self.chain_integrity_verified,
            "ai_disclosure_text": self.ai_disclosure_text,
            "generated_at": self.generated_at.isoformat(),
        }


class AuditAgent:
    """审计 Agent"""

    def __init__(self):
        # 内存存储（生产环境应使用数据库）
        self._audit_logs: list[AuditEntry] = []
        self._ai_usage_logs: list[AIUsageLog] = []
        self._last_hash: str | None = None

    async def log_action(self, entry: AuditEntry) -> AuditEntry:
        """记录一条审计日志（只增不改）"""
        # 设置前一条日志的哈希
        entry.previous_hash = self._last_hash

        # 计算当前条目哈希
        current_hash = entry.compute_hash()
        self._last_hash = current_hash

        # 存储（不可变）
        self._audit_logs.append(entry)

        return entry

    async def log_ai_usage(self, usage: AIUsageLog) -> AIUsageLog:
        """记录一次 AI 使用"""
        self._ai_usage_logs.append(usage)
        return usage

    async def log_state_transition(
        self,
        obj_type: str,
        obj_id: str,
        from_state: str,
        to_state: str,
        actor_id: str,
        actor_type: str = "human",
    ) -> AuditEntry:
        """记录状态迁移"""
        entry = AuditEntry(
            actor_id=actor_id,
            actor_type=actor_type,
            action="transition",
            object_type=obj_type,
            object_id=obj_id,
            details={
                "from_state": from_state,
                "to_state": to_state,
            },
        )
        return await self.log_action(entry)

    async def log_create(
        self,
        obj_type: str,
        obj_id: str,
        actor_id: str,
        actor_type: str = "human",
        details: dict | None = None,
    ) -> AuditEntry:
        """记录创建操作"""
        entry = AuditEntry(
            actor_id=actor_id,
            actor_type=actor_type,
            action="create",
            object_type=obj_type,
            object_id=obj_id,
            details=details or {},
        )
        return await self.log_action(entry)

    async def log_update(
        self,
        obj_type: str,
        obj_id: str,
        actor_id: str,
        changes: dict,
        actor_type: str = "human",
    ) -> AuditEntry:
        """记录更新操作"""
        entry = AuditEntry(
            actor_id=actor_id,
            actor_type=actor_type,
            action="update",
            object_type=obj_type,
            object_id=obj_id,
            details={"changes": changes},
        )
        return await self.log_action(entry)

    async def log_approval_decision(
        self,
        approval_task_id: str,
        review_bundle_id: str,
        signer_id: str,
        action: str,
        decision_reason: str | None = None,
        override_ai_flag: bool = False,
        override_reason: str | None = None,
    ) -> AuditEntry:
        """记录审批决策"""
        entry = AuditEntry(
            actor_id=signer_id,
            actor_type="human",
            action=f"approval_{action}",
            object_type="approval_task",
            object_id=approval_task_id,
            details={
                "review_bundle_id": review_bundle_id,
                "decision": action,
                "decision_reason": decision_reason,
            },
            override_ai_flag=override_ai_flag,
            override_reason=override_reason,
        )
        return await self.log_action(entry)

    async def log_ai_operation(
        self,
        agent_name: str,
        model_name: str,
        prompt_template_id: str,
        obj_type: str,
        obj_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
    ) -> tuple[AuditEntry, AIUsageLog]:
        """记录 AI 操作（同时写审计日志和 AI 使用记录）"""
        # AI 使用记录
        usage = AIUsageLog(
            agent_name=agent_name,
            model_name=model_name,
            prompt_template_id=prompt_template_id,
            input_token_count=input_tokens,
            output_token_count=output_tokens,
            latency_ms=latency_ms,
            related_object_type=obj_type,
            related_object_id=obj_id,
        )
        await self.log_ai_usage(usage)

        # 审计日志
        entry = AuditEntry(
            actor_type="agent",
            action="ai_operation",
            object_type=obj_type,
            object_id=obj_id,
            details={
                "agent_name": agent_name,
                "operation": prompt_template_id,
            },
            ai_model=model_name,
            ai_prompt_hash=hashlib.sha256(prompt_template_id.encode()).hexdigest()[:16],
            ai_token_usage={
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
            },
        )
        entry = await self.log_action(entry)

        return entry, usage

    async def get_audit_trail(
        self, object_type: str, object_id: str
    ) -> list[AuditEntry]:
        """查询对象的完整审计链"""
        return [
            entry for entry in self._audit_logs
            if entry.object_type == object_type and entry.object_id == object_id
        ]

    async def get_ai_usage_report(
        self, time_range: tuple[datetime, datetime]
    ) -> AIUsageReport:
        """生成 AI 使用统计报告"""
        start, end = time_range
        relevant_logs = [
            log for log in self._ai_usage_logs
            if start <= log.timestamp <= end
        ]

        total_calls = len(relevant_logs)
        total_tokens = sum(log.input_token_count + log.output_token_count for log in relevant_logs)

        by_model = {}
        by_agent = {}
        total_latency = 0

        for log in relevant_logs:
            # 按模型统计
            model = log.model_name
            if model not in by_model:
                by_model[model] = {"calls": 0, "tokens": 0}
            by_model[model]["calls"] += 1
            by_model[model]["tokens"] += log.input_token_count + log.output_token_count

            # 按 Agent 统计
            agent = log.agent_name
            if agent not in by_agent:
                by_agent[agent] = {"calls": 0, "tokens": 0}
            by_agent[agent]["calls"] += 1
            by_agent[agent]["tokens"] += log.input_token_count + log.output_token_count

            total_latency += log.latency_ms

        avg_latency = total_latency / total_calls if total_calls > 0 else 0

        return AIUsageReport(
            time_range=time_range,
            total_calls=total_calls,
            total_tokens=total_tokens,
            by_model=by_model,
            by_agent=by_agent,
            average_latency_ms=avg_latency,
        )

    async def verify_chain_integrity(self, object_id: str) -> bool:
        """验证审计链完整性（哈希链校验）"""
        relevant_entries = [
            entry for entry in self._audit_logs
            if entry.object_id == object_id
        ]

        if not relevant_entries:
            return True

        # 验证哈希链
        prev_hash = None
        for entry in relevant_entries:
            if entry.previous_hash != prev_hash:
                return False
            prev_hash = entry.compute_hash()

        return True

    async def generate_compliance_report(
        self, story_packet_id: str
    ) -> ComplianceReport:
        """生成合规报告（含 AI 使用披露）"""
        # 获取相关审计日志
        audit_entries = await self.get_audit_trail("story_packet", story_packet_id)

        # 统计 AI 使用
        ai_entries = [e for e in audit_entries if e.ai_model is not None]
        override_entries = [e for e in audit_entries if e.override_ai_flag]

        # 验证链完整性
        chain_ok = await self.verify_chain_integrity(story_packet_id)

        # 生成 AI 使用披露文本
        if ai_entries:
            models_used = list(set(e.ai_model for e in ai_entries if e.ai_model))
            disclosure = f"本文写作过程中使用了 AI 辅助工具（{', '.join(models_used)}），所有内容经人工审核确认。"
        else:
            disclosure = ""

        return ComplianceReport(
            story_packet_id=story_packet_id,
            audit_entries_count=len(audit_entries),
            ai_usage_count=len(ai_entries),
            ai_override_count=len(override_entries),
            chain_integrity_verified=chain_ok,
            ai_disclosure_text=disclosure,
        )


# 全局实例
audit_agent = AuditAgent()
