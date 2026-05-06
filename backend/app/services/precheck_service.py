"""送审预检规则引擎：校验稿件是否满足送审条件。"""

import json
from dataclasses import dataclass, field

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_packet import StoryPacket
from app.models.evidence_pack import EvidencePack
from app.models.claim_card import ClaimCard
from app.models.draft_version import DraftVersion
from app.models.risk_report import RiskReport


@dataclass
class PrecheckItem:
    """预检项"""
    check: str
    detail: str


@dataclass
class PrecheckResult:
    """预检结果"""
    passed: bool
    blocking_items: list[PrecheckItem] = field(default_factory=list)
    warning_items: list[PrecheckItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "blocking_items": [
                {"check": i.check, "detail": i.detail}
                for i in self.blocking_items
            ],
            "warning_items": [
                {"check": i.check, "detail": i.detail}
                for i in self.warning_items
            ],
        }


class PrecheckService:
    """送审预检服务"""

    async def check_owner_assigned(
        self, packet: StoryPacket, db: AsyncSession
    ) -> PrecheckItem | None:
        """检查：owner 已指定"""
        if not packet.owner_id:
            return PrecheckItem("owner_not_assigned", "稿件未指定负责人")
        return None

    async def check_evidence_pack_exists(
        self, packet: StoryPacket, db: AsyncSession
    ) -> PrecheckItem | None:
        """检查：证据包已绑定"""
        count = await db.scalar(
            select(func.count(EvidencePack.id))
            .where(EvidencePack.story_packet_id == packet.id)
        )
        if not count or count == 0:
            return PrecheckItem("evidence_pack_missing", "未绑定证据包")
        return None

    async def check_risk_report_exists(
        self, packet: StoryPacket, db: AsyncSession
    ) -> PrecheckItem | None:
        """检查：风险报告已生成"""
        count = await db.scalar(
            select(func.count(RiskReport.id))
            .where(RiskReport.story_packet_id == packet.id)
            .where(RiskReport.report_type == "risk")
        )
        if not count or count == 0:
            return PrecheckItem("risk_report_missing", "未生成风险报告")
        return None

    async def check_draft_exists(
        self, packet: StoryPacket, db: AsyncSession
    ) -> PrecheckItem | None:
        """检查：Draft 已生成"""
        count = await db.scalar(
            select(func.count(DraftVersion.id))
            .where(DraftVersion.story_packet_id == packet.id)
        )
        if not count or count == 0:
            return PrecheckItem("draft_missing", "未生成草稿")
        return None

    async def check_claim_anchors(
        self, packet: StoryPacket, db: AsyncSession
    ) -> PrecheckItem | None:
        """检查：Claim 锚点已建立（高风险句已映射 Claim Card）"""
        # 获取最新草稿
        result = await db.execute(
            select(DraftVersion)
            .where(DraftVersion.story_packet_id == packet.id)
            .order_by(DraftVersion.version.desc())
            .limit(1)
        )
        draft = result.scalar_one_or_none()
        if not draft:
            return None  # 由 check_draft_exists 处理
        
        # 获取所有 claim cards
        result = await db.execute(
            select(ClaimCard)
            .where(ClaimCard.story_packet_id == packet.id)
            .where(ClaimCard.risk_level.in_(["L2", "L3"]))
        )
        high_risk_claims = result.scalars().all()
        
        unanchored = [c for c in high_risk_claims if not c.draft_anchor_ref]
        if unanchored:
            return PrecheckItem(
                "claim_anchors_missing",
                f"{len(unanchored)} 个高风险事实卡未建立正文锚点"
            )
        return None

    async def check_high_risk_claims_resolved(
        self, packet: StoryPacket, db: AsyncSession
    ) -> PrecheckItem | None:
        """检查：高风险 claim 已处理（L2/L3 稿件）"""
        if packet.risk_level not in ["L2", "L3"]:
            return None
        
        result = await db.execute(
            select(ClaimCard)
            .where(ClaimCard.story_packet_id == packet.id)
            .where(ClaimCard.risk_level.in_(["L2", "L3"]))
            .where(ClaimCard.status == "insufficient")
        )
        insufficient_claims = result.scalars().all()
        
        if insufficient_claims:
            return PrecheckItem(
                "high_risk_claim_unresolved",
                f"{len(insufficient_claims)} 个高风险事实卡状态为 insufficient"
            )
        return None

    async def check_redaction_complete(
        self, packet: StoryPacket, db: AsyncSession
    ) -> PrecheckItem | None:
        """检查：脱敏已完成（警告级别）"""
        result = await db.execute(
            select(RiskReport)
            .where(RiskReport.story_packet_id == packet.id)
            .where(RiskReport.report_type == "redaction")
            .order_by(RiskReport.version.desc())
            .limit(1)
        )
        report = result.scalar_one_or_none()
        
        if not report:
            return PrecheckItem("redaction_report_missing", "未生成脱敏报告")
        
        # 检查是否有未处理的脱敏项
        findings = report.findings
        if isinstance(findings, str):
            findings = json.loads(findings)
        
        unprocessed = [f for f in findings if not f.get("processed", False)]
        if unprocessed:
            return PrecheckItem(
                "redaction_incomplete",
                f"{len(unprocessed)} 项脱敏建议未确认"
            )
        return None

    async def check_submit_note(
        self, submit_note: str | None
    ) -> PrecheckItem | None:
        """检查：送审说明已填写"""
        if not submit_note or not submit_note.strip():
            return PrecheckItem("submit_note_missing", "未填写送审说明")
        return None

    async def run_precheck(
        self,
        packet: StoryPacket,
        db: AsyncSession,
        submit_note: str | None = None,
        stage: str = "editorial_review"
    ) -> PrecheckResult:
        """
        执行完整预检
        
        Args:
            packet: 报道任务包
            db: 数据库会话
            submit_note: 送审说明
            stage: 审批阶段
        
        Returns:
            PrecheckResult 预检结果
        """
        blocking_items: list[PrecheckItem] = []
        warning_items: list[PrecheckItem] = []

        # 阻断级别检查
        checks = [
            self.check_owner_assigned(packet, db),
            self.check_evidence_pack_exists(packet, db),
            self.check_draft_exists(packet, db),
        ]
        
        # 根据阶段添加额外检查
        if stage in ["editorial_review", "risk_review", "final_signoff"]:
            checks.append(self.check_risk_report_exists(packet, db))
            checks.append(self.check_claim_anchors(packet, db))
            checks.append(self.check_high_risk_claims_resolved(packet, db))
        
        # 送审说明检查
        note_check = await self.check_submit_note(submit_note)
        if note_check:
            blocking_items.append(note_check)

        # 执行所有检查
        for check_coro in checks:
            result = await check_coro
            if result:
                blocking_items.append(result)

        # 警告级别检查
        redaction_check = await self.check_redaction_complete(packet, db)
        if redaction_check:
            warning_items.append(redaction_check)

        return PrecheckResult(
            passed=len(blocking_items) == 0,
            blocking_items=blocking_items,
            warning_items=warning_items,
        )


precheck_service = PrecheckService()
