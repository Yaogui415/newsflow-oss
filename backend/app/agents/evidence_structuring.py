"""Evidence Structuring Agent：证据结构化 Agent，负责从原始材料抽取结构化证据。"""

import uuid
import json
import re
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.core.config import settings


@dataclass
class CitationAnchor:
    """来源指针"""
    source_id: str
    source_type: str  # text / pdf / audio / image
    location: dict = field(default_factory=dict)  # paragraph_index, page_number, timestamp, etc.
    excerpt: str = ""

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "location": self.location,
            "excerpt": self.excerpt[:200] if self.excerpt else "",
        }


@dataclass
class ExtractionResult:
    """单源抽取结果"""
    source_id: str
    quotes: list[dict] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    data_points: list[dict] = field(default_factory=list)
    citation_anchors: list[CitationAnchor] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "quotes": self.quotes,
            "claims": self.claims,
            "entities": self.entities,
            "events": self.events,
            "data_points": self.data_points,
            "citation_anchors": [a.to_dict() for a in self.citation_anchors],
        }


@dataclass
class MergedEvidence:
    """跨源合并后的证据"""
    quotes: list[dict] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    data_points: list[dict] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    citation_map: dict = field(default_factory=dict)


# 结构化抽取 Prompt
EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个专业的新闻事实核查员，负责从文本中抽取结构化证据信息。

请从以下文本中抽取以下类型的信息，以 JSON 格式输出：

1. **quotes（引语）**：直接或间接引述
   - text: 引述内容
   - speaker: 发言人
   - context: 引述背景
   - is_direct: 是否直接引述

2. **claims（事实断言）**：可验证的陈述
   - claim_text: 断言内容
   - confidence: 初始可信度 (0-1)
   - risk_level: 风险等级 (L0/L1/L2/L3)

3. **entities（实体）**：人物、机构、地点
   - name: 名称
   - type: 类型 (person/organization/location/product)
   - attributes: 属性字典

4. **events（事件）**：具体发生的行为
   - description: 事件描述
   - time: 发生时间
   - location: 发生地点
   - participants: 参与者列表

5. **data_points（数据点）**：数字、金额、比例
   - value: 数值
   - unit: 单位
   - context: 上下文

输出格式：
{{
    "quotes": [...],
    "claims": [...],
    "entities": [...],
    "events": [...],
    "data_points": [...]
}}

注意：
- 只抽取文本中明确提到的信息
- 为每条 claim 评估风险等级（涉及敏感话题/人物/法律问题的为高风险）
- 保持信息的原始表述，不要推断或添加"""),
    ("user", "请分析以下文本（来源ID: {source_id}）：\n\n{text}")
])


# 来源可信度配置
SOURCE_CREDIBILITY = {
    "official_announcement": 0.95,
    "court_filing": 0.90,
    "regulatory_document": 0.90,
    "mainstream_media": 0.75,
    "industry_report": 0.70,
    "social_media_verified": 0.50,
    "social_media": 0.30,
    "anonymous": 0.15,
    "upload": 0.60,
    "rss": 0.65,
    "reporter_tip": 0.70,
}


class EvidenceStructuringAgent:
    """证据结构化 Agent"""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL or None,
            temperature=0.1,
        )

    async def extract_from_source(
        self, source_id: str, content: str, source_type: str = "text"
    ) -> ExtractionResult:
        """从单个来源抽取结构化信息"""
        if not content or len(content) < 20:
            return ExtractionResult(source_id=source_id)

        try:
            # 截断过长文本
            text_truncated = content[:6000]

            chain = EXTRACTION_PROMPT | self.llm
            response = await chain.ainvoke({
                "source_id": source_id,
                "text": text_truncated,
            })

            # 解析 JSON
            json_match = re.search(r"\{[\s\S]*\}", response.content)
            if not json_match:
                return ExtractionResult(source_id=source_id)

            data = json.loads(json_match.group())

            # 为每条信息添加来源指针
            citation_anchors = []
            for i, claim in enumerate(data.get("claims", [])):
                anchor = CitationAnchor(
                    source_id=source_id,
                    source_type=source_type,
                    location={"index": i},
                    excerpt=claim.get("claim_text", "")[:100],
                )
                citation_anchors.append(anchor)
                claim["citation_anchor_id"] = f"{source_id}:claim:{i}"

            return ExtractionResult(
                source_id=source_id,
                quotes=data.get("quotes", []),
                claims=data.get("claims", []),
                entities=data.get("entities", []),
                events=data.get("events", []),
                data_points=data.get("data_points", []),
                citation_anchors=citation_anchors,
            )
        except Exception as e:
            return ExtractionResult(source_id=source_id)

    async def merge_extractions(self, results: list[ExtractionResult]) -> MergedEvidence:
        """跨源合并：实体消歧、事件关联、时间线排序"""
        merged = MergedEvidence()
        entity_map = {}  # name -> merged entity
        citation_map = {}

        for result in results:
            # 合并引语
            merged.quotes.extend(result.quotes)

            # 合并 claims
            for claim in result.claims:
                claim["source_ids"] = [result.source_id]
                merged.claims.append(claim)

            # 实体消歧与合并
            for entity in result.entities:
                name = entity.get("name", "").strip()
                if not name:
                    continue

                if name in entity_map:
                    # 合并属性
                    existing = entity_map[name]
                    existing["source_ids"].append(result.source_id)
                    if entity.get("attributes"):
                        existing.setdefault("attributes", {}).update(entity["attributes"])
                else:
                    entity["source_ids"] = [result.source_id]
                    entity_map[name] = entity

            # 合并事件
            for event in result.events:
                event["source_ids"] = [result.source_id]
                merged.events.append(event)

            # 合并数据点
            for dp in result.data_points:
                dp["source_id"] = result.source_id
                merged.data_points.append(dp)

            # 合并来源指针
            for anchor in result.citation_anchors:
                citation_map[f"{anchor.source_id}:{anchor.excerpt[:50]}"] = anchor.to_dict()

        merged.entities = list(entity_map.values())
        merged.citation_map = citation_map

        # 生成时间线
        merged.timeline = self._build_timeline(merged.events)

        return merged

    def _build_timeline(self, events: list[dict]) -> list[dict]:
        """构建时间线"""
        timeline = []
        for event in events:
            time_str = event.get("time")
            if time_str:
                timeline.append({
                    "time": time_str,
                    "description": event.get("description"),
                    "participants": event.get("participants", []),
                })
        # 简单排序（实际应解析时间做精确排序）
        timeline.sort(key=lambda x: x.get("time", ""))
        return timeline

    async def build_evidence_pack(
        self, story_packet_id: str, merged: MergedEvidence
    ) -> dict:
        """生成 Evidence Pack 数据结构"""
        return {
            "story_packet_id": story_packet_id,
            "version": 1,
            "sources": [
                {
                    "source_id": sid,
                    "credibility": SOURCE_CREDIBILITY.get("upload", 0.6),
                }
                for sid in set(
                    sid for claim in merged.claims for sid in claim.get("source_ids", [])
                )
            ],
            "quotes": merged.quotes,
            "claims": merged.claims,
            "entities": merged.entities,
            "events": merged.events,
            "data_points": merged.data_points,
            "timeline": merged.timeline,
            "citation_anchors": merged.citation_map,
            "completeness_score": self._calculate_completeness(merged),
            "created_at": datetime.utcnow().isoformat(),
        }

    def _calculate_completeness(self, merged: MergedEvidence) -> float:
        """计算证据完整度评分"""
        scores = []
        if merged.quotes:
            scores.append(1.0)
        if merged.claims:
            scores.append(1.0)
        if merged.entities:
            scores.append(1.0)
        if merged.events:
            scores.append(1.0)
        if merged.timeline:
            scores.append(1.0)
        return sum(scores) / 5.0 if scores else 0.0

    async def generate_initial_claim_cards(self, merged: MergedEvidence) -> list[dict]:
        """从合并的证据中生成初始 Claim Cards"""
        claim_cards = []
        for i, claim in enumerate(merged.claims):
            card = {
                "id": str(uuid.uuid4()),
                "claim_text": claim.get("claim_text", ""),
                "risk_level": claim.get("risk_level", "L0"),
                "status": "unverified",
                "supporting_evidence": [],
                "contradicting_evidence": [],
                "missing_evidence": [],
                "confidence_score": claim.get("confidence", 0.5),
                "citation_anchor_id": claim.get("citation_anchor_id"),
                "source_ids": claim.get("source_ids", []),
            }
            claim_cards.append(card)
        return claim_cards


# 全局实例
evidence_structuring_agent = EvidenceStructuringAgent()
