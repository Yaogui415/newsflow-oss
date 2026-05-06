"""Post Publish Monitor Agent：发布后监测 Agent，负责持续监测和勘误流程。"""

import uuid
import json
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Any
from enum import Enum

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.core.config import settings


class ImpactSeverity(str, Enum):
    """影响严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ImpactType(str, Enum):
    """影响类型"""
    FACTUAL_UPDATE = "factual_update"
    CONTRADICTION = "contradiction"
    NEW_ANGLE = "new_angle"
    CORRECTION = "correction"


class SuggestedAction(str, Enum):
    """建议操作"""
    SUPPLEMENT = "supplement"
    UPDATE = "update"
    CORRECTION = "correction"
    REOPEN = "reopen"
    NEW_PACKET = "new_packet"


@dataclass
class ImpactAssessment:
    """新信息影响评估"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    new_source_id: str = ""
    story_packet_id: str = ""
    event_case_id: str = ""
    affected_claims: list[dict] = field(default_factory=list)
    affected_paragraphs: list[dict] = field(default_factory=list)
    affected_channels: list[dict] = field(default_factory=list)
    impact_type: ImpactType = ImpactType.FACTUAL_UPDATE
    severity: ImpactSeverity = ImpactSeverity.LOW
    urgency: str = "monitor"
    suggested_action: SuggestedAction = SuggestedAction.SUPPLEMENT
    reasoning: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "new_source_id": self.new_source_id,
            "story_packet_id": self.story_packet_id,
            "event_case_id": self.event_case_id,
            "affected_claims": self.affected_claims,
            "affected_paragraphs": self.affected_paragraphs,
            "affected_channels": self.affected_channels,
            "impact_type": self.impact_type.value,
            "severity": self.severity.value,
            "urgency": self.urgency,
            "suggested_action": self.suggested_action.value,
            "reasoning": self.reasoning,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class UpdateSuggestion:
    """更新建议"""
    assessment_id: str = ""
    action_type: SuggestedAction = SuggestedAction.SUPPLEMENT
    urgency: str = "monitor"
    affected_scope: str = ""
    description: str = ""
    template: str = ""

    def to_dict(self) -> dict:
        return {
            "assessment_id": self.assessment_id,
            "action_type": self.action_type.value,
            "urgency": self.urgency,
            "affected_scope": self.affected_scope,
            "description": self.description,
            "template": self.template,
        }


@dataclass
class CorrectionTicket:
    """勘误工单"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    story_packet_id: str = ""
    trigger_reason: str = ""
    trigger_source: str = ""
    impact_scope: str = ""
    proposed_fix: str = ""
    owner_id: str | None = None
    status: str = "pending"
    confirmed_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "story_packet_id": self.story_packet_id,
            "trigger_reason": self.trigger_reason,
            "trigger_source": self.trigger_source,
            "impact_scope": self.impact_scope,
            "proposed_fix": self.proposed_fix,
            "owner_id": self.owner_id,
            "status": self.status,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class NewsroomMemory:
    """编辑部记忆体"""
    event_case_id: str = ""
    story_packets: list[str] = field(default_factory=list)
    published_contents: list[dict] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    feedback_items: list[dict] = field(default_factory=list)
    confirmed_facts: list[dict] = field(default_factory=list)
    debunked_claims: list[dict] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    process_notes: list[dict] = field(default_factory=list)
    review_feedback: list[dict] = field(default_factory=list)
    key_entities: list[str] = field(default_factory=list)
    key_topics: list[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=lambda: datetime.utcnow())

    def to_dict(self) -> dict:
        return {
            "event_case_id": self.event_case_id,
            "story_packets": self.story_packets,
            "corrections": self.corrections,
            "confirmed_facts_count": len(self.confirmed_facts),
            "debunked_claims_count": len(self.debunked_claims),
            "unresolved_questions": self.unresolved_questions,
            "key_entities": self.key_entities,
            "key_topics": self.key_topics,
            "last_updated": self.last_updated.isoformat(),
        }


# 勘误声明模板
CORRECTION_TEMPLATES = {
    "factual_error": {
        "prefix": "【更正】",
        "template": '本文{publish_date}发布的版本中，关于{error_scope}的表述有误。原文称"{original_text}"，实际应为"{corrected_text}"。特此更正。更正时间：{correction_date}。',
    },
    "missing_context": {
        "prefix": "【补充】",
        "template": "本文{publish_date}发布后，{new_info_source}。现补充相关信息：{supplementary_text}。补充时间：{correction_date}。",
    },
    "retraction": {
        "prefix": "【撤回说明】",
        "template": "本文{publish_date}发布的内容因{retraction_reason}，现予以撤回。撤回时间：{correction_date}。",
    },
}


# 影响评估 Prompt
IMPACT_ASSESSMENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一名资深新闻编辑，负责评估新信息对已发布内容的影响。

请分析新信息与已发布内容的关系，判断：
1. 影响类型：factual_update（事实更新）/ contradiction（矛盾）/ new_angle（新角度）/ correction（需更正）
2. 严重程度：low / medium / high / critical
3. 紧急程度：immediate / within_24h / within_week / monitor
4. 建议操作：supplement（补充）/ update（更新）/ correction（勘误）/ reopen（重开）/ new_packet（新稿）

输出 JSON 格式：
{{
    "impact_type": "...",
    "severity": "...",
    "urgency": "...",
    "suggested_action": "...",
    "affected_claims": ["受影响的事实断言"],
    "reasoning": "分析理由"
}}"""),
    ("user", """已发布内容摘要：
{published_summary}

已发布的核心事实：
{published_claims}

新信息：
{new_information}

请评估影响。""")
])


class PostPublishMonitor:
    """发布后监测服务"""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL or None,
            temperature=0.2,
        )
        self._monitoring_tasks: dict[str, dict] = {}
        self._correction_tickets: dict[str, CorrectionTicket] = {}
        self._memories: dict[str, NewsroomMemory] = {}

    async def start_monitoring(
        self, story_packet_id: str, event_case_id: str, keywords: list[str], risk_level: str = "L0"
    ) -> dict:
        """Story Packet 发布后自动启动监测"""
        # 根据风险等级确定监测时长
        duration_days = 30
        if risk_level in ("L2", "L3"):
            duration_days = 90

        task = {
            "story_packet_id": story_packet_id,
            "event_case_id": event_case_id,
            "keywords": keywords,
            "risk_level": risk_level,
            "duration_days": duration_days,
            "started_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(days=duration_days)).isoformat(),
            "status": "active",
        }
        self._monitoring_tasks[story_packet_id] = task
        return task

    async def stop_monitoring(self, story_packet_id: str):
        """停止监测"""
        if story_packet_id in self._monitoring_tasks:
            self._monitoring_tasks[story_packet_id]["status"] = "stopped"

    async def assess_new_information(
        self,
        story_packet_id: str,
        new_source_id: str,
        new_content: str,
        published_summary: str,
        published_claims: list[str],
    ) -> ImpactAssessment:
        """评估新信息对已发布内容的影响"""
        try:
            chain = IMPACT_ASSESSMENT_PROMPT | self.llm
            response = await chain.ainvoke({
                "published_summary": published_summary,
                "published_claims": "\n".join(f"- {c}" for c in published_claims),
                "new_information": new_content,
            })

            import re
            json_match = re.search(r"\{[\s\S]*\}", response.content)
            if json_match:
                data = json.loads(json_match.group())

                impact_type = ImpactType(data.get("impact_type", "factual_update"))
                severity = ImpactSeverity(data.get("severity", "low"))
                suggested_action = SuggestedAction(data.get("suggested_action", "supplement"))

                return ImpactAssessment(
                    new_source_id=new_source_id,
                    story_packet_id=story_packet_id,
                    event_case_id=self._monitoring_tasks.get(story_packet_id, {}).get("event_case_id", ""),
                    affected_claims=[{"claim": c} for c in data.get("affected_claims", [])],
                    impact_type=impact_type,
                    severity=severity,
                    urgency=data.get("urgency", "monitor"),
                    suggested_action=suggested_action,
                    reasoning=data.get("reasoning", ""),
                )

            return ImpactAssessment(
                new_source_id=new_source_id,
                story_packet_id=story_packet_id,
            )
        except Exception as e:
            return ImpactAssessment(
                new_source_id=new_source_id,
                story_packet_id=story_packet_id,
                reasoning=f"评估失败: {str(e)}",
            )

    async def generate_update_suggestion(
        self, assessment: ImpactAssessment
    ) -> UpdateSuggestion:
        """基于影响评估生成更新建议"""
        action_descriptions = {
            SuggestedAction.SUPPLEMENT: "建议在已发布内容中补充新信息",
            SuggestedAction.UPDATE: "建议更新部分内容",
            SuggestedAction.CORRECTION: "建议发布勘误声明",
            SuggestedAction.REOPEN: "建议重开 Story Packet 进行重大修改",
            SuggestedAction.NEW_PACKET: "建议创建新的 Story Packet 跟进报道",
        }

        template = ""
        if assessment.suggested_action == SuggestedAction.CORRECTION:
            template = CORRECTION_TEMPLATES["factual_error"]["template"]
        elif assessment.suggested_action == SuggestedAction.SUPPLEMENT:
            template = CORRECTION_TEMPLATES["missing_context"]["template"]

        return UpdateSuggestion(
            assessment_id=assessment.id,
            action_type=assessment.suggested_action,
            urgency=assessment.urgency,
            affected_scope=f"{len(assessment.affected_claims)} 个事实断言可能受影响",
            description=action_descriptions.get(assessment.suggested_action, ""),
            template=template,
        )

    async def create_correction_ticket(
        self,
        story_packet_id: str,
        trigger_reason: str,
        trigger_source: str,
        impact_scope: str,
        proposed_fix: str,
        owner_id: str | None = None,
    ) -> CorrectionTicket:
        """创建勘误工单"""
        ticket = CorrectionTicket(
            story_packet_id=story_packet_id,
            trigger_reason=trigger_reason,
            trigger_source=trigger_source,
            impact_scope=impact_scope,
            proposed_fix=proposed_fix,
            owner_id=owner_id,
        )
        self._correction_tickets[ticket.id] = ticket
        return ticket

    async def confirm_correction(self, ticket_id: str) -> CorrectionTicket | None:
        """确认勘误"""
        ticket = self._correction_tickets.get(ticket_id)
        if ticket:
            ticket.status = "confirmed"
            ticket.confirmed_at = datetime.utcnow()
        return ticket

    async def resolve_correction(self, ticket_id: str) -> CorrectionTicket | None:
        """完成勘误"""
        ticket = self._correction_tickets.get(ticket_id)
        if ticket:
            ticket.status = "resolved"
            ticket.resolved_at = datetime.utcnow()
        return ticket

    async def generate_correction_statement(
        self,
        correction_type: str,
        publish_date: str,
        error_scope: str = "",
        original_text: str = "",
        corrected_text: str = "",
        new_info_source: str = "",
        supplementary_text: str = "",
        retraction_reason: str = "",
    ) -> str:
        """生成勘误声明"""
        template_config = CORRECTION_TEMPLATES.get(correction_type, CORRECTION_TEMPLATES["factual_error"])
        correction_date = datetime.utcnow().strftime("%Y-%m-%d")

        statement = template_config["prefix"] + template_config["template"].format(
            publish_date=publish_date,
            error_scope=error_scope,
            original_text=original_text,
            corrected_text=corrected_text,
            new_info_source=new_info_source,
            supplementary_text=supplementary_text,
            retraction_reason=retraction_reason,
            correction_date=correction_date,
        )
        return statement

    async def write_to_memory(
        self,
        event_case_id: str,
        story_packet_id: str,
        content_type: str,
        content: dict,
    ):
        """回写到编辑部记忆体"""
        if event_case_id not in self._memories:
            self._memories[event_case_id] = NewsroomMemory(event_case_id=event_case_id)

        memory = self._memories[event_case_id]
        memory.last_updated = datetime.utcnow()

        if story_packet_id and story_packet_id not in memory.story_packets:
            memory.story_packets.append(story_packet_id)

        if content_type == "published_content":
            memory.published_contents.append(content)
        elif content_type == "correction":
            memory.corrections.append(content.get("ticket_id", ""))
        elif content_type == "feedback":
            memory.feedback_items.append(content)
        elif content_type == "confirmed_fact":
            memory.confirmed_facts.append(content)
        elif content_type == "debunked_claim":
            memory.debunked_claims.append(content)
        elif content_type == "process_note":
            memory.process_notes.append(content)
        elif content_type == "review_feedback":
            memory.review_feedback.append(content)

    async def get_memory(self, event_case_id: str) -> NewsroomMemory | None:
        """获取编辑部记忆"""
        return self._memories.get(event_case_id)

    async def search_by_entity(self, entity_name: str) -> list[NewsroomMemory]:
        """按实体检索相关编辑部记忆"""
        results = []
        for memory in self._memories.values():
            if entity_name.lower() in [e.lower() for e in memory.key_entities]:
                results.append(memory)
        return results

    async def search_by_topic(self, topic: str) -> list[NewsroomMemory]:
        """按主题检索"""
        results = []
        for memory in self._memories.values():
            if topic.lower() in [t.lower() for t in memory.key_topics]:
                results.append(memory)
        return results

    async def add_entity_to_memory(self, event_case_id: str, entity: str):
        """添加关键实体到记忆"""
        if event_case_id in self._memories:
            if entity not in self._memories[event_case_id].key_entities:
                self._memories[event_case_id].key_entities.append(entity)

    async def add_topic_to_memory(self, event_case_id: str, topic: str):
        """添加关键主题到记忆"""
        if event_case_id in self._memories:
            if topic not in self._memories[event_case_id].key_topics:
                self._memories[event_case_id].key_topics.append(topic)


# 全局实例
post_publish_monitor = PostPublishMonitor()
