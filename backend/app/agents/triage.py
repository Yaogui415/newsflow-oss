"""Triage Agent：分诊评估 Agent，负责对候选事件进行多维度评估。"""

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
class TriageReport:
    """分诊评估报告"""
    event_case_id: str
    news_value_score: int = 3  # 1-5
    timeliness: str = "medium"  # urgent / high / medium / low
    risk_level: str = "L0"  # L0 / L1 / L2 / L3
    reportability: str = "partial"  # sufficient / partial / insufficient
    suggested_desk: str = ""
    suggested_angles: list[str] = field(default_factory=list)
    suggested_content_types: list[str] = field(default_factory=list)
    existing_coverage: list[str] = field(default_factory=list)
    key_entities: list[str] = field(default_factory=list)
    assessment_reasoning: str = ""
    rule_overrides: list[dict] = field(default_factory=list)
    confidence: float = 0.8
    assessed_at: datetime = field(default_factory=lambda: datetime.utcnow())

    def to_dict(self) -> dict:
        return {
            "event_case_id": self.event_case_id,
            "triage_result": {
                "news_value_score": self.news_value_score,
                "timeliness": self.timeliness,
                "risk_level": self.risk_level,
                "reportability": self.reportability,
                "suggested_desk": self.suggested_desk,
                "suggested_angles": self.suggested_angles,
                "suggested_content_types": self.suggested_content_types,
                "existing_coverage": self.existing_coverage,
                "key_entities": self.key_entities,
                "assessment_reasoning": self.assessment_reasoning,
            },
            "rule_overrides": self.rule_overrides,
            "confidence": self.confidence,
            "assessed_at": self.assessed_at.isoformat(),
        }


# 分诊评估 Prompt
TRIAGE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个资深新闻编辑，负责对候选新闻事件进行分诊评估。请根据以下信息进行全面评估。

新闻原则：
- 公共利益优先于纯流量刺激，不能仅因“热搜/争议”就抬高新闻价值。
- 明确区分已证实事实、待核信息、当事人口径和社交媒体传言。
- 若来源层级偏低、单一或高度同质，应降低可报道性并提示需要补充采访/官方回应。
- 涉及指控、违法、名誉风险、未成年人、国家安全、匿名源时，风险等级必须从严。
- 对立观点尚未出现时，不得假定单方说法已成立，应在评估理由中提示“需补充回应/平衡”。
- 可读性和传播效率可以考虑，但不得以标题党、情绪化或耸动表达换取流量。

评估维度：
1. **新闻价值评分 (1-5)**：
   - 5分：重大突发、全国关注、重大政策变化
   - 4分：行业重大事件、区域重要新闻
   - 3分：一般性新闻、行业动态
   - 2分：日常新闻、例行报道
   - 1分：价值有限、可不报道

2. **时效性**：
   - urgent：2小时内需发布
   - high：12小时内需发布
   - medium：48小时内可发布
   - low：无紧迫性

3. **风险等级**：
   - L0：无风险
   - L1：低风险（需编辑审核）
   - L2：中风险（需主编审核）
   - L3：高风险（需法务+总编审核）

4. **可报道性**：
   - sufficient：信息充足可报道
   - partial：需补充采访
   - insufficient：信息不足

5. **建议栏目**：财经 / 科技 / 社会 / 医疗 / 政治 / 文化 / 体育 / 国际

6. **建议角度**：列出 2-4 个可行的报道切入点

7. **建议内容形态**：breaking / in_depth / explainer / video_script / podcast

请以 JSON 格式输出评估结果：
{{
    "news_value_score": 4,
    "timeliness": "high",
    "risk_level": "L1",
    "reportability": "sufficient",
    "suggested_desk": "财经",
    "suggested_angles": ["角度1", "角度2"],
    "suggested_content_types": ["breaking", "in_depth"],
    "key_entities": ["实体1", "实体2"],
    "assessment_reasoning": "评估理由"
}}"""),
    ("user", """请评估以下事件：

**标题**：{title}

**摘要**：{summary}

**5W1H 信息**：
{w5h1_info}

**来源数量**：{source_count}

**关键实体**：{entities}

**风险标签**：{risk_tags}
""")
])


# 风险规则配置
RISK_RULES = [
    {"condition": "involves_listed_company", "keywords": ["上市公司", "股价", "IPO", "证监会"], "min_risk": "L1"},
    {"condition": "involves_minor", "keywords": ["未成年", "儿童", "学生", "校园"], "min_risk": "L2"},
    {"condition": "involves_national_security", "keywords": ["国家安全", "军事", "机密", "国防"], "min_risk": "L3"},
    {"condition": "involves_anonymous_source", "keywords": ["知情人士", "匿名", "消息人士"], "min_risk": "L1"},
    {"condition": "involves_ongoing_litigation", "keywords": ["诉讼", "法院", "被告", "原告"], "min_risk": "L2"},
    {"condition": "involves_public_figure", "keywords": ["官员", "领导", "明星", "企业家"], "min_risk": "L1"},
]


class TriageAgent:
    """分诊评估 Agent"""

    def __init__(self, llm=None):
        self.llm = llm or ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL or None,
            temperature=0.2,
        )

    async def assess(self, event_data: dict) -> TriageReport:
        """对候选事件进行全面评估"""
        event_id = event_data.get("id", str(uuid.uuid4()))
        
        # 1. LLM 评估
        llm_result = await self._llm_assess(event_data)
        
        # 2. 规则层叠加
        rule_overrides, final_risk = self._apply_rules(event_data, llm_result.get("risk_level", "L0"))
        
        # 3. 时效性调整
        timeliness = self._assess_timeliness(event_data, llm_result.get("timeliness", "medium"))
        
        return TriageReport(
            event_case_id=event_id,
            news_value_score=llm_result.get("news_value_score", 3),
            timeliness=timeliness,
            risk_level=final_risk,
            reportability=llm_result.get("reportability", "partial"),
            suggested_desk=llm_result.get("suggested_desk", ""),
            suggested_angles=llm_result.get("suggested_angles", []),
            suggested_content_types=llm_result.get("suggested_content_types", []),
            key_entities=llm_result.get("key_entities", []),
            assessment_reasoning=llm_result.get("assessment_reasoning", ""),
            rule_overrides=rule_overrides,
            confidence=0.82,
        )

    async def _llm_assess(self, event_data: dict) -> dict:
        """使用 LLM 进行评估"""
        try:
            # 准备输入
            title = event_data.get("title", "")
            summary = event_data.get("summary", "")
            w5h1 = event_data.get("extracted_5w1h", {})
            source_count = len(event_data.get("sources", []))
            entities = w5h1.get("key_entities", []) + w5h1.get("who", [])
            risk_tags = event_data.get("risk_tags", [])
            
            w5h1_str = json.dumps(w5h1, ensure_ascii=False, indent=2) if w5h1 else "无"
            
            chain = TRIAGE_PROMPT | self.llm
            response = await chain.ainvoke({
                "title": title or "未知",
                "summary": summary or "无摘要",
                "w5h1_info": w5h1_str,
                "source_count": source_count or 1,
                "entities": ", ".join(entities) if entities else "无",
                "risk_tags": ", ".join(risk_tags) if risk_tags else "无",
            })
            
            # 解析 JSON
            content = response.content
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                return json.loads(json_match.group())
            return {}
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Triage LLM assessment failed: {e}")
            return {"news_value_score": 3, "timeliness": "medium", "risk_level": "L1", "reportability": "partial"}

    def _apply_rules(self, event_data: dict, base_risk: str) -> tuple[list[dict], str]:
        """应用规则层，返回 (规则覆盖列表, 最终风险等级)"""
        content = json.dumps(event_data, ensure_ascii=False)
        overrides = []
        risk_levels = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
        current_risk_num = risk_levels.get(base_risk, 0)
        
        for rule in RISK_RULES:
            matched = any(kw in content for kw in rule["keywords"])
            if matched:
                rule_risk = rule["min_risk"]
                rule_risk_num = risk_levels.get(rule_risk, 0)
                
                overrides.append({
                    "rule": rule["condition"],
                    "applied": True,
                    "min_risk": rule_risk,
                })
                
                if rule_risk_num > current_risk_num:
                    current_risk_num = rule_risk_num
        
        # 反向映射
        final_risk = {v: k for k, v in risk_levels.items()}.get(current_risk_num, "L0")
        return overrides, final_risk

    def _assess_timeliness(self, event_data: dict, base_timeliness: str) -> str:
        """评估时效性"""
        # 检查事件时间
        w5h1 = event_data.get("extracted_5w1h", {})
        when = w5h1.get("when", "")
        
        # 简单规则：包含"今日"、"刚刚"等词汇则提升时效性
        urgent_keywords = ["刚刚", "突发", "紧急", "速报", "最新"]
        high_keywords = ["今日", "今天", "今晨", "今晚", "今午"]
        
        content = json.dumps(event_data, ensure_ascii=False)
        
        if any(kw in content for kw in urgent_keywords):
            return "urgent"
        if any(kw in content for kw in high_keywords):
            return "high"
        
        return base_timeliness

    async def score_news_value(self, event_data: dict) -> int:
        """新闻价值评分 1-5"""
        report = await self.assess(event_data)
        return report.news_value_score

    async def assess_risk(self, event_data: dict) -> str:
        """风险等级初判"""
        report = await self.assess(event_data)
        return report.risk_level

    async def suggest_desk(self, event_data: dict) -> str:
        """建议栏目"""
        report = await self.assess(event_data)
        return report.suggested_desk

    async def suggest_angles(self, event_data: dict) -> list[str]:
        """建议报道角度"""
        report = await self.assess(event_data)
        return report.suggested_angles


# 全局实例
triage_agent = TriageAgent()
