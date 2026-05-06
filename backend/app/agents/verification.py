"""Verification Agent：核验 Agent，负责交叉核验和生成证据矩阵。"""

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
class VerificationResult:
    """核验结果"""
    claim_id: str
    status: str  # supported / contradicted / insufficient / unverified
    supporting_evidence: list[dict] = field(default_factory=list)
    contradicting_evidence: list[dict] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    confidence_score: float = 0.5
    verification_method: str = ""
    pending_human_check: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "status": self.status,
            "supporting_evidence": self.supporting_evidence,
            "contradicting_evidence": self.contradicting_evidence,
            "missing_evidence": self.missing_evidence,
            "confidence_score": self.confidence_score,
            "verification_method": self.verification_method,
            "pending_human_check": self.pending_human_check,
        }


@dataclass
class EvidenceMatrix:
    """证据矩阵"""
    story_packet_id: str
    claims: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    pending_checks: list[dict] = field(default_factory=list)
    high_risk_alerts: list[dict] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.utcnow())

    def to_dict(self) -> dict:
        return {
            "story_packet_id": self.story_packet_id,
            "claims": self.claims,
            "summary": self.summary,
            "pending_checks": self.pending_checks,
            "high_risk_alerts": self.high_risk_alerts,
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass
class Contradiction:
    """逻辑矛盾"""
    claim1_id: str
    claim2_id: str
    description: str
    severity: str  # high / medium / low

    def to_dict(self) -> dict:
        return {
            "claim1_id": self.claim1_id,
            "claim2_id": self.claim2_id,
            "description": self.description,
            "severity": self.severity,
        }


# Claim 拆解 Prompt
DECOMPOSE_CLAIMS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个专业的事实核查员，负责将复合陈述拆解为原子级可验证断言。

请将以下文本拆解为独立的、可验证的事实断言（claims）。

要求：
1. 每条 claim 应该是一个简单、独立的陈述
2. 复合句应拆分为多条 claim
3. 隐含的断言也要显式列出（如"比去年增长50%"隐含"今年数据已知"和"去年数据已知"）
4. 为每条 claim 标注风险等级：
   - L0: 常规信息，无风险
   - L1: 涉及具体人物/机构，需要确认
   - L2: 涉及敏感话题/指控，需要主编审核
   - L3: 涉及法律风险/重大指控，需要法务审核
5. 只保留可核查的事实，不要把情绪词、观点、营销话术、标题党表达当作事实断言
6. 若文本包含单方指控、匿名源或社交媒体传言，应拆出“谁提出了何种说法”，不要把说法直接当作既成事实

输出格式（JSON）：
{{
    "claims": [
        {{
            "claim_text": "断言内容",
            "risk_level": "L0/L1/L2/L3",
            "verifiable": true,
            "suggested_verification": "建议的核验方法"
        }}
    ]
}}"""),
    ("user", "请拆解以下文本中的事实断言：\n\n{text}")
])


# 交叉核验 Prompt
CROSS_VERIFY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个专业的事实核查员，负责评估一条断言的可信度。

请分析以下断言和相关证据，判断该断言的核验状态。

核验原则：
- 优先采用官方/监管/原始文件/主流媒体/现场一手材料；社交媒体与匿名源默认权重更低。
- 明确区分“事实已被证实”与“有人声称/指控/推测”。
- 若存在关键当事方回应缺失、证据仅单边来源、或证据链不闭合，应倾向 insufficient 而不是 supported。
- 对可能引发名誉、法律、公共安全风险的断言，必须更严格，宁缺毋滥。

核验状态：
- supported: 有充分证据支持
- contradicted: 存在矛盾证据
- insufficient: 证据不足
- unverified: 尚无相关证据

输出格式（JSON）：
{{
    "status": "supported/contradicted/insufficient/unverified",
    "confidence_score": 0.0-1.0,
    "supporting_evidence": ["支持证据描述"],
    "contradicting_evidence": ["矛盾证据描述"],
    "missing_evidence": ["缺失但应有的证据"],
    "verification_method": "核验方法描述",
    "reasoning": "判断理由"
}}"""),
    ("user", """请核验以下断言：

断言：{claim_text}

相关证据：
{evidence}

请评估该断言的可信度。""")
])


# 来源可信度权重
SOURCE_CREDIBILITY_WEIGHTS = {
    "official_announcement": 0.95,
    "court_filing": 0.90,
    "regulatory_document": 0.90,
    "mainstream_media": 0.75,
    "industry_report": 0.70,
    "social_media_verified": 0.50,
    "social_media": 0.30,
    "anonymous": 0.15,
}


class VerificationAgent:
    """核验 Agent"""

    def __init__(self, llm=None):
        self.llm = llm or ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL or None,
            temperature=0.1,
        )

    async def decompose_claims(self, text: str) -> list[dict]:
        """将文本拆解为原子 claim"""
        if not text or len(text) < 10:
            return []

        try:
            chain = DECOMPOSE_CLAIMS_PROMPT | self.llm
            response = await chain.ainvoke({"text": text[:4000]})

            json_match = re.search(r"\{[\s\S]*\}", response.content)
            if json_match:
                data = json.loads(json_match.group())
                claims = data.get("claims", [])
                # 为每条 claim 添加 ID
                for claim in claims:
                    claim["id"] = str(uuid.uuid4())
                return claims
            return []
        except Exception:
            return []

    async def verify_claim(
        self, claim: dict, evidence_items: list[dict]
    ) -> VerificationResult:
        """对单条 claim 做交叉核验"""
        claim_id = claim.get("id", str(uuid.uuid4()))
        claim_text = claim.get("claim_text", "")

        if not claim_text:
            return VerificationResult(claim_id=claim_id, status="unverified")

        try:
            # 准备证据文本
            evidence_text = "\n".join([
                f"- [{e.get('source_type', '未知来源')}/{e.get('credibility', e.get('credibility_tier', '未标注分级'))}] {e.get('content', '')[:200]}"
                for e in evidence_items[:10]
            ])

            chain = CROSS_VERIFY_PROMPT | self.llm
            response = await chain.ainvoke({
                "claim_text": claim_text,
                "evidence": evidence_text or "无相关证据",
            })

            json_match = re.search(r"\{[\s\S]*\}", response.content)
            if json_match:
                data = json.loads(json_match.group())
                return VerificationResult(
                    claim_id=claim_id,
                    status=data.get("status", "unverified"),
                    supporting_evidence=data.get("supporting_evidence", []),
                    contradicting_evidence=data.get("contradicting_evidence", []),
                    missing_evidence=data.get("missing_evidence", []),
                    confidence_score=data.get("confidence_score", 0.5),
                    verification_method=data.get("verification_method", "LLM交叉核验"),
                )

            return VerificationResult(claim_id=claim_id, status="unverified")
        except Exception:
            return VerificationResult(claim_id=claim_id, status="unverified")

    async def build_evidence_matrix(
        self, story_packet_id: str, claims: list[dict], evidence_items: list[dict]
    ) -> EvidenceMatrix:
        """生成完整证据矩阵"""
        matrix = EvidenceMatrix(story_packet_id=story_packet_id)
        
        supported_count = 0
        contradicted_count = 0
        insufficient_count = 0
        unverified_count = 0

        for claim in claims:
            # 核验每条 claim
            result = await self.verify_claim(claim, evidence_items)

            # 更新统计
            if result.status == "supported":
                supported_count += 1
            elif result.status == "contradicted":
                contradicted_count += 1
            elif result.status == "insufficient":
                insufficient_count += 1
            else:
                unverified_count += 1

            # 添加到矩阵
            matrix.claims.append({
                "claim_id": result.claim_id,
                "claim_text": claim.get("claim_text", ""),
                "risk_level": claim.get("risk_level", "L0"),
                "verification": result.to_dict(),
            })

            # 高风险告警
            risk_level = claim.get("risk_level", "L0")
            if risk_level in ("L2", "L3") and result.status in ("contradicted", "insufficient"):
                matrix.high_risk_alerts.append({
                    "claim_id": result.claim_id,
                    "claim_text": claim.get("claim_text", ""),
                    "risk_level": risk_level,
                    "status": result.status,
                    "alert": f"高风险断言({risk_level})核验状态为{result.status}，需人工确认",
                })

            # 待核清单
            if result.pending_human_check:
                for check in result.pending_human_check:
                    matrix.pending_checks.append({
                        "claim_id": result.claim_id,
                        "check_item": check,
                    })

        # 汇总
        total = len(claims)
        matrix.summary = {
            "total_claims": total,
            "supported": supported_count,
            "contradicted": contradicted_count,
            "insufficient": insufficient_count,
            "unverified": unverified_count,
            "support_rate": supported_count / total if total > 0 else 0,
            "high_risk_unresolved": len(matrix.high_risk_alerts),
        }

        return matrix

    async def detect_logical_contradictions(
        self, claims: list[dict]
    ) -> list[Contradiction]:
        """检测 claim 之间的逻辑矛盾"""
        contradictions = []

        # 简单的数值矛盾检测
        for i, claim1 in enumerate(claims):
            for claim2 in claims[i + 1:]:
                text1 = claim1.get("claim_text", "")
                text2 = claim2.get("claim_text", "")

                # 检测同一主题的不同数值
                if self._extract_numbers(text1) and self._extract_numbers(text2):
                    # 简化检测：如果两条 claim 都包含数字且主题相似，标记为潜在矛盾
                    if self._topics_similar(text1, text2):
                        nums1 = self._extract_numbers(text1)
                        nums2 = self._extract_numbers(text2)
                        if nums1 != nums2:
                            contradictions.append(Contradiction(
                                claim1_id=claim1.get("id", ""),
                                claim2_id=claim2.get("id", ""),
                                description=f"数值不一致：{nums1} vs {nums2}",
                                severity="medium",
                            ))

        return contradictions

    def _extract_numbers(self, text: str) -> list[str]:
        """提取文本中的数字"""
        return re.findall(r"\d+(?:\.\d+)?%?", text)

    def _topics_similar(self, text1: str, text2: str) -> bool:
        """简单判断两段文本是否讨论相似主题"""
        # 提取关键词重叠
        words1 = set(re.findall(r"[\u4e00-\u9fa5]+", text1))
        words2 = set(re.findall(r"[\u4e00-\u9fa5]+", text2))
        overlap = len(words1 & words2)
        return overlap >= 2

    async def generate_pending_checklist(
        self, matrix: EvidenceMatrix
    ) -> list[dict]:
        """生成待人工核实清单"""
        checklist = []

        # 从高风险告警生成
        for alert in matrix.high_risk_alerts:
            checklist.append({
                "priority": "high",
                "claim_id": alert["claim_id"],
                "claim_text": alert["claim_text"],
                "check_type": "high_risk_verification",
                "reason": alert["alert"],
            })

        # 从证据不足的 claim 生成
        for claim in matrix.claims:
            if claim["verification"]["status"] == "insufficient":
                checklist.append({
                    "priority": "medium",
                    "claim_id": claim["claim_id"],
                    "claim_text": claim["claim_text"],
                    "check_type": "evidence_supplement",
                    "reason": "证据不足，需补充来源",
                    "missing": claim["verification"].get("missing_evidence", []),
                })

        return checklist

    def calculate_confidence(
        self, source_types: list[str], consistency: float, recency_days: int
    ) -> float:
        """计算综合置信度"""
        # 来源可信度
        if source_types:
            source_score = max(
                SOURCE_CREDIBILITY_WEIGHTS.get(st, 0.5) for st in source_types
            )
        else:
            source_score = 0.3

        # 一致性加成
        consistency_factor = 1.0 + (consistency * 0.2)

        # 时效性衰减
        if recency_days <= 1:
            recency_factor = 1.0
        elif recency_days <= 7:
            recency_factor = 0.95
        elif recency_days <= 30:
            recency_factor = 0.85
        else:
            recency_factor = 0.70

        return min(source_score * consistency_factor * recency_factor, 1.0)


# 全局实例
verification_agent = VerificationAgent()
