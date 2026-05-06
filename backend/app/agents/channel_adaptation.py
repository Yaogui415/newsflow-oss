"""Channel Adaptation Agent：渠道适配 Agent，负责将主稿适配为不同平台版本。"""

import uuid
import json
import re
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.core.config import settings


# 渠道规则配置
CHANNEL_RULES = {
    "website": {
        "name": "网站长稿",
        "max_title_length": 60,
        "require_seo_title": True,
        "style": "formal",
        "max_body_length": None,
    },
    "app_breaking": {
        "name": "App快讯",
        "max_title_length": 30,
        "max_body_length": 200,
        "push_title_max_length": 25,
        "style": "concise",
    },
    "wechat": {
        "name": "微信公众号",
        "max_title_length": 30,
        "recommended_body_length": (2000, 4000),
        "require_subtitles": True,
        "max_paragraph_length": 150,
        "style": "readable",
    },
    "weibo": {
        "name": "微博",
        "max_length": 140,
        "require_hashtags": True,
        "max_hashtags": 3,
        "style": "concise",
    },
    "xiaohongshu": {
        "name": "小红书",
        "max_title_length": 20,
        "max_body_length": 1000,
        "require_hook_opening": True,
        "require_bullet_points": True,
        "style": "casual",
    },
    "video_script": {
        "name": "视频脚本",
        "max_duration_seconds": 180,
        "require_subtitle_text": True,
        "require_scene_markers": True,
        "style": "conversational",
    },
    "push_title": {
        "name": "推送标题",
        "max_length": 25,
        "prohibit_clickbait": True,
        "require_core_fact": True,
    },
    "podcast": {
        "name": "播客提纲",
        "style": "conversational",
    },
}

# 漂移阈值
DRIFT_THRESHOLDS = {
    "default": 0.30,
    "high_risk_content": 0.15,
    "breaking_news": 0.20,
}


@dataclass
class DriftReport:
    """语义漂移报告"""
    drift_score: float = 0.0
    fact_changes: list[dict] = field(default_factory=list)
    tone_shift: str | None = None
    exceeds_threshold: bool = False
    threshold_used: float = 0.30

    def to_dict(self) -> dict:
        return {
            "drift_score": self.drift_score,
            "fact_changes": self.fact_changes,
            "tone_shift": self.tone_shift,
            "exceeds_threshold": self.exceeds_threshold,
            "threshold_used": self.threshold_used,
        }


@dataclass
class PlatformComplianceResult:
    """平台规范检查结果"""
    compliant: bool = True
    violations: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "compliant": self.compliant,
            "violations": self.violations,
            "warnings": self.warnings,
        }


@dataclass
class ChannelOutput:
    """渠道适配输出"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    channel_type: str = ""
    source_draft_id: str = ""
    title: str = ""
    content: dict = field(default_factory=dict)
    drift_score: float = 0.0
    drift_report: DriftReport | None = None
    compliance_result: PlatformComplianceResult | None = None
    status: str = "draft"
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "channel_type": self.channel_type,
            "source_draft_id": self.source_draft_id,
            "title": self.title,
            "content": self.content,
            "drift_score": self.drift_score,
            "drift_report": self.drift_report.to_dict() if self.drift_report else None,
            "compliance_result": self.compliance_result.to_dict() if self.compliance_result else None,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


# 渠道适配 Prompt
CHANNEL_ADAPT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一名资深内容运营，负责将新闻稿件适配为不同平台的版本。

核心原则：
1. **事实内核一致** - 不能改变、添加或删除任何事实
2. **风格转换** - 根据平台特点调整表达方式
3. **长度适配** - 严格遵守平台长度限制
4. **格式规范** - 符合平台特有格式要求
5. **新闻原则不降级** - 平台化改写不能牺牲准确性、中性、平衡性和必要归因
6. **流量服务分发，不凌驾事实** - 可以提高可读性，但不得使用标题党、耸动词、审判式表达或情绪操控
7. **高风险内容从严** - 涉及指控、争议、匿名源、未成年人、法律风险时，优先保守表达并保留不确定性边界

请输出 JSON 格式：
{{
    "title": "适配后的标题",
    "content": {{
        "body": "正文内容",
        "hashtags": ["话题标签"],  // 如需要
        "push_title": "推送标题",  // 如需要
        "subtitles": ["小标题"],   // 如需要
        "scene_markers": ["画面提示"]  // 视频脚本需要
    }}
}}"""),
    ("user", """请将以下稿件适配为 {channel_name} 格式：

**原稿标题**：{original_title}

**原稿内容**：
{original_content}

**平台规则**：
- 标题最大长度：{max_title_length}
- 正文最大长度：{max_body_length}
- 风格要求：{style}
- 特殊要求：{special_requirements}

请进行适配。""")
])


class DriftDetector:
    """语义漂移检测器"""

    def __init__(self):
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL or None,
        )

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """计算余弦相似度"""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

    async def compute_drift_score(
        self, source_content: str, channel_content: str
    ) -> float:
        """计算语义漂移分数 (0-1)，0=完全一致，1=完全不同"""
        try:
            source_embedding = await self.embeddings.aembed_query(source_content[:2000])
            channel_embedding = await self.embeddings.aembed_query(channel_content[:2000])
            similarity = self._cosine_similarity(source_embedding, channel_embedding)
            return 1.0 - similarity
        except Exception:
            return 0.5  # 默认中等漂移

    async def detect_fact_changes(
        self, source_content: str, channel_content: str
    ) -> list[dict]:
        """检测事实层变化"""
        changes = []

        # 提取数字
        source_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", source_content))
        channel_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", channel_content))

        # 检测数字变化
        added_numbers = channel_numbers - source_numbers
        removed_numbers = source_numbers - channel_numbers

        if added_numbers:
            changes.append({
                "type": "number_added",
                "description": f"渠道版本新增了数字：{added_numbers}",
                "severity": "high",
            })

        if removed_numbers:
            changes.append({
                "type": "number_removed",
                "description": f"渠道版本删除了数字：{removed_numbers}",
                "severity": "medium",
            })

        return changes

    async def detect_tone_shift(
        self, source_content: str, channel_content: str
    ) -> str | None:
        """检测语气偏移"""
        # 简化检测：检查情绪词变化
        emotional_words = ["震惊", "惊人", "突然", "紧急", "重磅", "独家"]
        source_emotional = sum(1 for w in emotional_words if w in source_content)
        channel_emotional = sum(1 for w in emotional_words if w in channel_content)

        if channel_emotional > source_emotional + 2:
            return "more_emotional"
        elif channel_emotional < source_emotional - 2:
            return "more_neutral"
        return None


class ChannelAdaptationAgent:
    """渠道适配 Agent"""

    def __init__(self, llm=None):
        self.llm = llm or ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL or None,
            temperature=0.3,
        )
        self.drift_detector = DriftDetector()

    async def adapt_to_channel(
        self,
        source_draft_id: str,
        original_title: str,
        original_content: str,
        channel_type: str,
        risk_level: str = "L0",
    ) -> ChannelOutput:
        """将主稿适配为特定渠道版本"""
        rules = CHANNEL_RULES.get(channel_type, CHANNEL_RULES["website"])

        # 准备特殊要求
        special_requirements = []
        if rules.get("require_hashtags"):
            special_requirements.append("需要添加话题标签")
        if rules.get("require_subtitles"):
            special_requirements.append("需要添加小标题分段")
        if rules.get("require_hook_opening"):
            special_requirements.append("开头需要有吸引力的钩子")

        try:
            chain = CHANNEL_ADAPT_PROMPT | self.llm
            response = await chain.ainvoke({
                "channel_name": rules.get("name", channel_type),
                "original_title": original_title,
                "original_content": original_content[:4000],
                "max_title_length": rules.get("max_title_length", "无限制"),
                "max_body_length": rules.get("max_body_length") or rules.get("max_length", "无限制"),
                "style": rules.get("style", "formal"),
                "special_requirements": "、".join(special_requirements) or "无",
            })

            # 解析响应
            json_match = re.search(r"\{[\s\S]*\}", response.content)
            if json_match:
                data = json.loads(json_match.group())
                channel_content = data.get("content", {})
                body = channel_content.get("body", "")

                # 漂移检测
                drift_score = await self.drift_detector.compute_drift_score(
                    original_content, body
                )
                fact_changes = await self.drift_detector.detect_fact_changes(
                    original_content, body
                )
                tone_shift = await self.drift_detector.detect_tone_shift(
                    original_content, body
                )

                # 确定阈值
                if risk_level in ("L2", "L3"):
                    threshold = DRIFT_THRESHOLDS["high_risk_content"]
                else:
                    threshold = DRIFT_THRESHOLDS["default"]

                drift_report = DriftReport(
                    drift_score=drift_score,
                    fact_changes=fact_changes,
                    tone_shift=tone_shift,
                    exceeds_threshold=drift_score > threshold,
                    threshold_used=threshold,
                )

                # 平台规范检查
                compliance = await self.check_platform_compliance(
                    data.get("title", ""), body, channel_type
                )

                # 确定状态
                status = "draft"
                if drift_report.exceeds_threshold:
                    status = "review_pending"

                return ChannelOutput(
                    channel_type=channel_type,
                    source_draft_id=source_draft_id,
                    title=data.get("title", original_title),
                    content=channel_content,
                    drift_score=drift_score,
                    drift_report=drift_report,
                    compliance_result=compliance,
                    status=status,
                )

            return ChannelOutput(channel_type=channel_type, source_draft_id=source_draft_id)
        except Exception as e:
            return ChannelOutput(channel_type=channel_type, source_draft_id=source_draft_id)

    async def batch_adapt(
        self,
        source_draft_id: str,
        original_title: str,
        original_content: str,
        channels: list[str],
        risk_level: str = "L0",
    ) -> list[ChannelOutput]:
        """批量适配多个渠道"""
        results = []
        for channel in channels:
            output = await self.adapt_to_channel(
                source_draft_id, original_title, original_content, channel, risk_level
            )
            results.append(output)
        return results

    async def check_platform_compliance(
        self, title: str, body: str, channel_type: str
    ) -> PlatformComplianceResult:
        """检查平台规范合规性"""
        rules = CHANNEL_RULES.get(channel_type, {})
        violations = []
        warnings = []

        # 标题长度检查
        max_title = rules.get("max_title_length")
        if max_title and len(title) > max_title:
            violations.append({
                "rule": "title_length",
                "message": f"标题长度 {len(title)} 超过限制 {max_title}",
            })

        # 正文长度检查
        max_body = rules.get("max_body_length") or rules.get("max_length")
        if max_body and len(body) > max_body:
            violations.append({
                "rule": "body_length",
                "message": f"正文长度 {len(body)} 超过限制 {max_body}",
            })

        # 标题党检查
        if rules.get("prohibit_clickbait"):
            clickbait_words = ["震惊", "速看", "不转不是", "99%的人"]
            for word in clickbait_words:
                if word in title:
                    violations.append({
                        "rule": "clickbait",
                        "message": f"标题包含疑似标题党词汇：{word}",
                    })

        # 话题标签检查
        if rules.get("require_hashtags"):
            if "#" not in body:
                warnings.append({
                    "rule": "hashtags",
                    "message": "缺少话题标签",
                })

        return PlatformComplianceResult(
            compliant=len(violations) == 0,
            violations=violations,
            warnings=warnings,
        )

    async def check_drift(
        self, channel_content: str, source_content: str, risk_level: str = "L0"
    ) -> DriftReport:
        """检查渠道版本的语义漂移"""
        drift_score = await self.drift_detector.compute_drift_score(
            source_content, channel_content
        )
        fact_changes = await self.drift_detector.detect_fact_changes(
            source_content, channel_content
        )
        tone_shift = await self.drift_detector.detect_tone_shift(
            source_content, channel_content
        )

        if risk_level in ("L2", "L3"):
            threshold = DRIFT_THRESHOLDS["high_risk_content"]
        else:
            threshold = DRIFT_THRESHOLDS["default"]

        return DriftReport(
            drift_score=drift_score,
            fact_changes=fact_changes,
            tone_shift=tone_shift,
            exceeds_threshold=drift_score > threshold,
            threshold_used=threshold,
        )


# 全局实例
channel_adaptation_agent = ChannelAdaptationAgent()
