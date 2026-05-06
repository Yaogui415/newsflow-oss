"""Relationship Investigation Agent：关系调查 Agent，负责构建事件中心图谱和检测利益冲突。"""

import uuid
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.core.config import settings


@dataclass
class GraphNode:
    """图谱节点"""
    id: str
    type: str  # person / organization / location / event / document
    name: str
    attributes: dict = field(default_factory=dict)
    source_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "attributes": self.attributes,
            "source_ids": self.source_ids,
        }


@dataclass
class GraphEdge:
    """图谱边"""
    id: str
    source_node_id: str
    target_node_id: str
    relation_type: str  # EMPLOYED_BY / SHAREHOLDER_OF / RELATED_TO / PARTICIPATED_IN / etc.
    attributes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source_node_id,
            "target": self.target_node_id,
            "relation": self.relation_type,
            "attributes": self.attributes,
        }


@dataclass
class EventGraph:
    """事件中心图谱"""
    event_case_id: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    central_event: str | None = None

    def to_dict(self) -> dict:
        return {
            "event_case_id": self.event_case_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "central_event": self.central_event,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
        }


@dataclass
class ConflictAlert:
    """利益冲突告警"""
    conflict_type: str
    severity: str  # high / medium / low
    description: str
    involved_entities: list[str]
    evidence: str

    def to_dict(self) -> dict:
        return {
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "description": self.description,
            "involved_entities": self.involved_entities,
            "evidence": self.evidence,
        }


@dataclass
class Timeline:
    """事件时间线"""
    events: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"events": self.events}


@dataclass
class InterviewSuggestion:
    """建议采访对象"""
    name: str
    role: str
    reason: str
    priority: str  # high / medium / low
    contact_hint: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "reason": self.reason,
            "priority": self.priority,
            "contact_hint": self.contact_hint,
        }


# 关系抽取 Prompt
RELATION_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个专业的调查记者，负责分析实体之间的关系。

请从以下实体和事件信息中抽取关系，以 JSON 格式输出。

关系类型：
- EMPLOYED_BY: 任职关系（人→机构）
- SHAREHOLDER_OF: 持股关系（人/机构→机构）
- RELATED_TO: 亲属/关联人关系（人→人）
- PARTICIPATED_IN: 参与事件（人/机构→事件）
- LOCATED_AT: 地点关联
- TRANSACTED_WITH: 交易关系（机构→机构）
- SUPERVISED_BY: 监管关系（机构→机构）

输出格式：
{{
    "relations": [
        {{
            "source": "实体名称",
            "target": "实体名称",
            "relation": "关系类型",
            "attributes": {{"role": "职务", "time": "时间"}}
        }}
    ],
    "potential_conflicts": [
        {{
            "type": "冲突类型",
            "description": "描述",
            "involved": ["实体1", "实体2"]
        }}
    ]
}}"""),
    ("user", """请分析以下实体和事件的关系：

实体列表：
{entities}

事件列表：
{events}

请抽取它们之间的关系，并识别潜在的利益冲突。""")
])


class RelationshipInvestigationAgent:
    """关系调查 Agent"""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL or None,
            temperature=0.2,
        )
        # 内存中的图谱存储（生产环境应使用 Neo4j）
        self._graphs: dict[str, EventGraph] = {}

    async def build_event_graph(
        self, event_case_id: str, entities: list[dict], events: list[dict]
    ) -> EventGraph:
        """为事件构建中心图谱"""
        graph = EventGraph(event_case_id=event_case_id)
        node_map = {}

        # 1. 创建实体节点
        for entity in entities:
            node_id = str(uuid.uuid4())
            node = GraphNode(
                id=node_id,
                type=entity.get("type", "unknown"),
                name=entity.get("name", ""),
                attributes=entity.get("attributes", {}),
                source_ids=entity.get("source_ids", []),
            )
            graph.nodes.append(node)
            node_map[entity.get("name", "")] = node_id

        # 2. 创建事件节点
        for event in events:
            node_id = str(uuid.uuid4())
            node = GraphNode(
                id=node_id,
                type="event",
                name=event.get("description", "")[:50],
                attributes={
                    "time": event.get("time"),
                    "location": event.get("location"),
                    "full_description": event.get("description"),
                },
                source_ids=event.get("source_ids", []),
            )
            graph.nodes.append(node)
            node_map[f"event:{event.get('description', '')[:30]}"] = node_id

            # 设置中心事件
            if not graph.central_event:
                graph.central_event = node_id

        # 3. 使用 LLM 抽取关系
        relations = await self._extract_relations(entities, events)

        # 4. 创建边
        for rel in relations.get("relations", []):
            source_name = rel.get("source", "")
            target_name = rel.get("target", "")
            source_id = node_map.get(source_name)
            target_id = node_map.get(target_name)

            if source_id and target_id:
                edge = GraphEdge(
                    id=str(uuid.uuid4()),
                    source_node_id=source_id,
                    target_node_id=target_id,
                    relation_type=rel.get("relation", "RELATED_TO"),
                    attributes=rel.get("attributes", {}),
                )
                graph.edges.append(edge)

        # 缓存图谱
        self._graphs[event_case_id] = graph
        return graph

    async def _extract_relations(
        self, entities: list[dict], events: list[dict]
    ) -> dict:
        """使用 LLM 抽取关系"""
        try:
            entities_str = json.dumps(entities, ensure_ascii=False, indent=2)
            events_str = json.dumps(events, ensure_ascii=False, indent=2)

            chain = RELATION_EXTRACTION_PROMPT | self.llm
            response = await chain.ainvoke({
                "entities": entities_str[:3000],
                "events": events_str[:2000],
            })

            import re
            json_match = re.search(r"\{[\s\S]*\}", response.content)
            if json_match:
                return json.loads(json_match.group())
            return {"relations": [], "potential_conflicts": []}
        except Exception:
            return {"relations": [], "potential_conflicts": []}

    async def detect_conflicts_of_interest(
        self, graph: EventGraph
    ) -> list[ConflictAlert]:
        """检测利益冲突"""
        conflicts = []

        # 规则1: 同一人在多个机构任职
        person_orgs = {}
        for edge in graph.edges:
            if edge.relation_type == "EMPLOYED_BY":
                person_id = edge.source_node_id
                org_id = edge.target_node_id
                person_orgs.setdefault(person_id, []).append(org_id)

        for person_id, org_ids in person_orgs.items():
            if len(org_ids) > 1:
                person_name = self._get_node_name(graph, person_id)
                org_names = [self._get_node_name(graph, oid) for oid in org_ids]
                conflicts.append(ConflictAlert(
                    conflict_type="dual_role",
                    severity="medium",
                    description=f"{person_name} 在多个机构任职",
                    involved_entities=[person_name] + org_names,
                    evidence="图谱关系分析",
                ))

        # 规则2: 交易双方存在共同关联人
        transactions = [e for e in graph.edges if e.relation_type == "TRANSACTED_WITH"]
        for tx in transactions:
            org1_people = self._get_related_people(graph, tx.source_node_id)
            org2_people = self._get_related_people(graph, tx.target_node_id)
            common = set(org1_people) & set(org2_people)
            if common:
                conflicts.append(ConflictAlert(
                    conflict_type="transaction_conflict",
                    severity="high",
                    description="交易双方存在共同关联人",
                    involved_entities=list(common),
                    evidence="图谱关系分析",
                ))

        return conflicts

    def _get_node_name(self, graph: EventGraph, node_id: str) -> str:
        """获取节点名称"""
        for node in graph.nodes:
            if node.id == node_id:
                return node.name
        return "未知"

    def _get_related_people(self, graph: EventGraph, org_id: str) -> list[str]:
        """获取与机构相关的人员"""
        people = []
        for edge in graph.edges:
            if edge.target_node_id == org_id and edge.relation_type == "EMPLOYED_BY":
                people.append(self._get_node_name(graph, edge.source_node_id))
        return people

    async def generate_timeline(self, events: list[dict]) -> Timeline:
        """生成事件时间线"""
        sorted_events = sorted(
            [e for e in events if e.get("time")],
            key=lambda x: x.get("time", "")
        )
        return Timeline(events=[
            {
                "time": e.get("time"),
                "description": e.get("description"),
                "participants": e.get("participants", []),
            }
            for e in sorted_events
        ])

    async def suggest_interview_targets(
        self, graph: EventGraph, existing_sources: list[str]
    ) -> list[InterviewSuggestion]:
        """建议采访对象"""
        suggestions = []

        # 找出图谱中的关键人物（连接度高）
        node_degrees = {}
        for edge in graph.edges:
            node_degrees[edge.source_node_id] = node_degrees.get(edge.source_node_id, 0) + 1
            node_degrees[edge.target_node_id] = node_degrees.get(edge.target_node_id, 0) + 1

        # 按连接度排序
        sorted_nodes = sorted(node_degrees.items(), key=lambda x: x[1], reverse=True)

        for node_id, degree in sorted_nodes[:5]:
            node = next((n for n in graph.nodes if n.id == node_id), None)
            if node and node.type == "person":
                # 检查是否已有该人物的来源
                if node.name not in existing_sources:
                    suggestions.append(InterviewSuggestion(
                        name=node.name,
                        role=node.attributes.get("role", "关键人物"),
                        reason=f"事件图谱中的核心人物，关联度 {degree}",
                        priority="high" if degree > 3 else "medium",
                    ))

        return suggestions


# 全局实例
relationship_investigation_agent = RelationshipInvestigationAgent()
