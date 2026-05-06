"""Drafting Agent：编修 Agent，负责基于证据包生成初稿。"""

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
class StructurePlan:
    """文章结构规划"""
    content_type: str
    sections: list[dict] = field(default_factory=list)
    total_word_limit: int = 3000
    key_points: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "content_type": self.content_type,
            "sections": self.sections,
            "total_word_limit": self.total_word_limit,
            "key_points": self.key_points,
        }


@dataclass
class TitleCandidate:
    """备选标题"""
    title: str
    style: str  # objective / attractive / explanatory
    scale: str  # conservative / neutral / aggressive
    score: float = 0.8

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "style": self.style,
            "scale": self.scale,
            "score": self.score,
        }


@dataclass
class DraftOutput:
    """初稿输出"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    lead: str = ""
    body: str = ""
    body_html: str = ""
    word_count: int = 0
    claim_anchor_map: dict = field(default_factory=dict)
    title_candidates: list[TitleCandidate] = field(default_factory=list)
    structure_plan: StructurePlan | None = None
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "lead": self.lead,
            "body": self.body,
            "word_count": self.word_count,
            "claim_anchor_map": self.claim_anchor_map,
            "title_candidates": [t.to_dict() for t in self.title_candidates],
            "version": self.version,
            "created_at": self.created_at.isoformat(),
        }


# 内容形态模板配置
CONTENT_TEMPLATES = {
    "breaking": {
        "name": "快讯",
        "sections": [
            {"section": "标题", "max_length": 30},
            {"section": "导语", "max_length": 100},
            {"section": "核心事实", "max_length": 300},
            {"section": "背景", "max_length": 200},
        ],
        "total_word_limit": 800,
    },
    "in_depth": {
        "name": "深稿",
        "sections": [
            {"section": "标题", "max_length": 40},
            {"section": "导语", "max_length": 200},
            {"section": "叙事主体"},
            {"section": "关键人物/机构背景"},
            {"section": "分析与影响"},
            {"section": "各方回应"},
            {"section": "未解答问题/后续关注"},
        ],
        "total_word_limit": 5000,
    },
    "explainer": {
        "name": "解释稿",
        "sections": [
            {"section": "标题"},
            {"section": "核心问题"},
            {"section": "答案与解释"},
            {"section": "背景"},
            {"section": "影响"},
            {"section": "展望"},
        ],
        "total_word_limit": 3000,
    },
    "video_script": {
        "name": "视频脚本",
        "sections": [
            {"section": "标题/封面文案", "max_length": 20},
            {"section": "开场钩子", "max_length": 50},
            {"section": "口播段落"},
            {"section": "结尾引导", "max_length": 30},
        ],
        "total_duration_seconds": 180,
    },
    "podcast": {
        "name": "播客提纲",
        "sections": [
            {"section": "主题"},
            {"section": "开场"},
            {"section": "讨论点"},
            {"section": "总结"},
        ],
    },
}


# 初稿生成 Prompt
DRAFTING_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一名资深新闻编辑，负责基于已核验的证据包撰写新闻稿件。

核心原则：
1. **先有证据，再有文章** - 只能使用提供的证据，不能编造任何事实
2. **每个事实必须有出处** - 在正文中标注 [Claim:ID] 锚点
3. **遵循风险建议** - 敏感措辞需按建议处理
4. **未核实信息显式标记** - 用 [待核实] 标签标注
5. **公共利益优先** - 以新闻价值和公共利益驱动选材，不以情绪化、煽动性表达换取流量
6. **保持中性与可归因** - 指控、判断、批评必须交代来源或主体，避免把单方说法写成既成事实
7. **注意平衡性** - 若关键对立方/当事方回应缺失，应明确指出“截至目前暂无回应/仍待补充”
8. **结构服务理解而非煽动** - 标题、导语、段落组织应提升可读性，但不得标题党、不得夸张放大冲突

请按以下结构输出：
{{
    "title": "标题",
    "lead": "导语（一段话概括核心事实）",
    "body": "正文（按结构组织，每个事实后标注 [Claim:xxx]）",
    "claim_anchors": {{"段落位置": "claim_id"}}
}}"""),
    ("user", """请为以下报道任务撰写初稿：

**报道角度**：{angle}
**目标受众**：{audience}
**内容形态**：{content_type}
**字数限制**：{word_limit}

**证据包摘要**：
{evidence_summary}

**已核验事实卡（可使用）**：
{verified_claims}

**风险建议**：
{risk_advice}

请基于以上证据撰写初稿，确保每个事实都有来源锚点。""")
])


# 标题生成 Prompt
TITLE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一名新闻标题专家，负责为稿件生成备选标题。

请生成 3-5 个备选标题，每个标题标注：
- style: objective（客观陈述）/ attractive（吸引眼球）/ explanatory（解释性）
- scale: conservative（保守）/ neutral（中性）/ aggressive（激进）

输出格式（JSON）：
{{
    "titles": [
        {{"title": "...", "style": "objective", "scale": "neutral"}},
        ...
    ]
}}

注意：
- 传播效率可以考虑，但不能牺牲准确性、平衡性和克制语气。
- 不能使用标题党、惊悚化、审判式、情绪操控式表达。
- 涉及未证实指控时，标题必须保留归因或不确定性边界。"""),
    ("user", """请为以下稿件生成备选标题：

**导语**：{lead}

**核心事实**：{key_facts}

**内容形态**：{content_type}
""")
])


class DraftingAgent:
    """编修 Agent"""

    def __init__(self, llm=None):
        self.llm = llm or ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL or None,
            temperature=0.3,
        )

    async def plan_structure(
        self, content_type: str, evidence_summary: str
    ) -> StructurePlan:
        """根据内容形态和证据规划文章结构"""
        template = CONTENT_TEMPLATES.get(content_type, CONTENT_TEMPLATES["in_depth"])

        # 提取关键点
        key_points = []
        if evidence_summary:
            # 简单提取：按句号分割取前5个
            sentences = evidence_summary.split("。")[:5]
            key_points = [s.strip() for s in sentences if len(s.strip()) > 10]

        return StructurePlan(
            content_type=content_type,
            sections=template.get("sections", []),
            total_word_limit=template.get("total_word_limit", 3000),
            key_points=key_points,
        )

    async def generate_draft(
        self,
        angle: str,
        audience: str,
        content_type: str,
        evidence_summary: str,
        verified_claims: list[dict],
        risk_advice: str | None = None,
    ) -> DraftOutput:
        """基于证据和结构生成初稿"""
        # 获取结构规划
        structure = await self.plan_structure(content_type, evidence_summary)

        # 准备 claims 文本
        claims_text = "\n".join([
            f"- [Claim:{c.get('id', 'unknown')}] {c.get('claim_text', '')}"
            for c in verified_claims
        ])

        try:
            chain = DRAFTING_PROMPT | self.llm
            response = await chain.ainvoke({
                "angle": angle or "客观报道",
                "audience": audience or "一般读者",
                "content_type": CONTENT_TEMPLATES.get(content_type, {}).get("name", content_type),
                "word_limit": structure.total_word_limit,
                "evidence_summary": evidence_summary or "无",
                "verified_claims": claims_text or "无已核验事实",
                "risk_advice": risk_advice or "无特殊风险建议",
            })

            # 解析响应
            json_match = re.search(r"\{[\s\S]*\}", response.content)
            if json_match:
                data = json.loads(json_match.group())
                body = data.get("body", "")

                # 生成标题候选
                title_candidates = await self.generate_title_candidates(
                    data.get("lead", ""),
                    claims_text[:500],
                    content_type,
                )

                return DraftOutput(
                    title=data.get("title", ""),
                    lead=data.get("lead", ""),
                    body=body,
                    body_html=self._to_html(body),
                    word_count=len(body),
                    claim_anchor_map=data.get("claim_anchors", {}),
                    title_candidates=title_candidates,
                    structure_plan=structure,
                )

            fallback = self._parse_structured_text(response.content)
            if fallback.get("body") or fallback.get("lead") or fallback.get("title"):
                body = fallback.get("body", "")
                title_candidates = await self.generate_title_candidates(
                    fallback.get("lead", "") or body[:120],
                    claims_text[:500],
                    content_type,
                )
                return DraftOutput(
                    title=fallback.get("title", ""),
                    lead=fallback.get("lead", ""),
                    body=body,
                    body_html=self._to_html(body),
                    word_count=len(body),
                    claim_anchor_map=await self.build_claim_anchor_map(body, verified_claims),
                    title_candidates=title_candidates,
                    structure_plan=structure,
                )

            return DraftOutput(structure_plan=structure)
        except Exception as e:
            return DraftOutput(structure_plan=structure)

    def _parse_structured_text(self, content: str) -> dict:
        title_match = re.search(r"(?:标题|Title)[:：]\s*(.+)", content)
        lead_match = re.search(r"(?:导语|Lead)[:：]\s*(.+?)(?:\n(?:正文|Body)[:：]|$)", content, re.S)
        body_match = re.search(r"(?:正文|Body)[:：]\s*([\s\S]+)$", content)

        title = title_match.group(1).strip() if title_match else ""
        lead = lead_match.group(1).strip() if lead_match else ""
        body = body_match.group(1).strip() if body_match else content.strip()

        return {
            "title": title,
            "lead": lead,
            "body": body,
        }

    def _to_html(self, text: str) -> str:
        """将纯文本转换为简单 HTML"""
        paragraphs = text.split("\n\n")
        html_parts = [f"<p>{p.strip()}</p>" for p in paragraphs if p.strip()]
        return "\n".join(html_parts)

    async def generate_title_candidates(
        self, lead: str, key_facts: str, content_type: str
    ) -> list[TitleCandidate]:
        """生成备选标题"""
        try:
            chain = TITLE_PROMPT | self.llm
            response = await chain.ainvoke({
                "lead": lead,
                "key_facts": key_facts,
                "content_type": CONTENT_TEMPLATES.get(content_type, {}).get("name", content_type),
            })

            json_match = re.search(r"\{[\s\S]*\}", response.content)
            if json_match:
                data = json.loads(json_match.group())
                return [
                    TitleCandidate(
                        title=t.get("title", ""),
                        style=t.get("style", "objective"),
                        scale=t.get("scale", "neutral"),
                    )
                    for t in data.get("titles", [])
                ]
            return []
        except Exception:
            return []

    async def build_claim_anchor_map(
        self, body: str, claims: list[dict]
    ) -> dict:
        """构建正文与 Claim Card 的锚点映射"""
        anchor_map = {}

        # 查找 [Claim:xxx] 格式的锚点
        pattern = r"\[Claim:([^\]]+)\]"
        matches = re.finditer(pattern, body)

        for match in matches:
            claim_id = match.group(1)
            position = match.start()
            anchor_map[str(position)] = claim_id

        return anchor_map

    async def highlight_unverified(self, body: str, claims: list[dict]) -> str:
        """标记正文中引用了未核实 claim 的段落"""
        unverified_ids = {
            c.get("id") for c in claims
            if c.get("status") in ("unverified", "insufficient")
        }

        # 替换未核实的锚点
        def replace_unverified(match):
            claim_id = match.group(1)
            if claim_id in unverified_ids:
                return f"[待核实:{claim_id}]"
            return match.group(0)

        return re.sub(r"\[Claim:([^\]]+)\]", replace_unverified, body)

    async def rewrite_with_angle(
        self, draft: DraftOutput, new_angle: str
    ) -> DraftOutput:
        """基于新角度改写（不改变事实层）"""
        # 保持事实锚点，只调整叙述方式
        new_draft = DraftOutput(
            title=draft.title,
            lead=draft.lead,
            body=draft.body,
            claim_anchor_map=draft.claim_anchor_map,
            structure_plan=draft.structure_plan,
            version=draft.version + 1,
        )
        # 实际改写逻辑需要 LLM 调用
        return new_draft


# 全局实例
drafting_agent = DraftingAgent()
