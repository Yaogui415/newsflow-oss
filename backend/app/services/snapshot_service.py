"""版本快照服务：生成 Review Bundle 和冻结版本。"""

import uuid
import json
import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review_bundle import ReviewBundle
from app.models.draft_version import DraftVersion
from app.models.evidence_pack import EvidencePack
from app.models.claim_card import ClaimCard
from app.models.risk_report import RiskReport
from app.models.story_packet import StoryPacket
from app.models.channel_package import ChannelPackage


class SnapshotService:
    """版本快照服务"""

    @staticmethod
    def compute_bundle_hash(data: dict) -> str:
        """计算内容哈希，确保不可篡改"""
        content = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()

    async def freeze_draft_version(
        self, story_packet_id: str, db: AsyncSession
    ) -> DraftVersion | None:
        """冻结最新草稿版本"""
        result = await db.execute(
            select(DraftVersion)
            .where(DraftVersion.story_packet_id == story_packet_id)
            .where(DraftVersion.is_frozen == False)
            .order_by(DraftVersion.version.desc())
            .limit(1)
        )
        draft = result.scalar_one_or_none()
        if draft:
            draft.is_frozen = True
        return draft

    async def create_evidence_snapshot(
        self, story_packet_id: str, db: AsyncSession
    ) -> EvidencePack | None:
        """创建证据包快照"""
        result = await db.execute(
            select(EvidencePack)
            .where(EvidencePack.story_packet_id == story_packet_id)
            .where(EvidencePack.is_snapshot == False)
            .order_by(EvidencePack.version.desc())
            .limit(1)
        )
        evidence = result.scalar_one_or_none()
        if not evidence:
            return None

        # 创建快照副本
        snapshot = EvidencePack(
            id=str(uuid.uuid4()),
            story_packet_id=story_packet_id,
            version=evidence.version,
            sources=evidence.sources,
            citation_anchors=evidence.citation_anchors,
            completeness_score=evidence.completeness_score,
            is_snapshot=True,
            snapshot_of_id=evidence.id,
            created_by=evidence.created_by,
        )
        db.add(snapshot)
        return snapshot

    async def snapshot_claims(
        self, story_packet_id: str, db: AsyncSession
    ) -> list[dict]:
        """快照当前事实卡状态"""
        result = await db.execute(
            select(ClaimCard)
            .where(ClaimCard.story_packet_id == story_packet_id)
        )
        claims = result.scalars().all()
        return [
            {
                "id": c.id,
                "claim_text": c.claim_text,
                "status": c.status,
                "risk_level": c.risk_level,
                "confidence_score": c.confidence_score,
                "verified_by": c.verified_by,
            }
            for c in claims
        ]

    async def snapshot_risk_report(
        self, story_packet_id: str, db: AsyncSession
    ) -> dict | None:
        """快照最新风险报告"""
        result = await db.execute(
            select(RiskReport)
            .where(RiskReport.story_packet_id == story_packet_id)
            .where(RiskReport.report_type == "risk")
            .order_by(RiskReport.version.desc())
            .limit(1)
        )
        report = result.scalar_one_or_none()
        if not report:
            return None
        
        findings = report.findings
        if isinstance(findings, str):
            findings = json.loads(findings)
        
        return {
            "id": report.id,
            "version": report.version,
            "findings": findings,
            "severity_summary": json.loads(report.severity_summary) if report.severity_summary else None,
            "generated_by": report.generated_by,
        }

    async def snapshot_redaction_report(
        self, story_packet_id: str, db: AsyncSession
    ) -> dict | None:
        """快照最新脱敏报告"""
        result = await db.execute(
            select(RiskReport)
            .where(RiskReport.story_packet_id == story_packet_id)
            .where(RiskReport.report_type == "redaction")
            .order_by(RiskReport.version.desc())
            .limit(1)
        )
        report = result.scalar_one_or_none()
        if not report:
            return None
        
        findings = report.findings
        if isinstance(findings, str):
            findings = json.loads(findings)
        
        return {
            "id": report.id,
            "version": report.version,
            "findings": findings,
            "generated_by": report.generated_by,
        }

    async def create_review_bundle(
        self,
        story_packet_id: str,
        bundle_type: str,
        submitted_by: str,
        submit_note: str,
        db: AsyncSession,
        channel_package_id: str | None = None,
    ) -> ReviewBundle:
        """
        创建送审快照包
        
        流程:
        1. 冻结当前 Draft Version
        2. 创建 Evidence Pack 快照
        3. 快照 Claim Card 状态
        4. 快照 Risk/Redaction Report
        5. 计算 bundle_hash
        6. 生成 Review Bundle
        """
        # 1. 冻结草稿
        draft = await self.freeze_draft_version(story_packet_id, db)
        
        # 2. 创建证据快照
        evidence_snapshot = await self.create_evidence_snapshot(story_packet_id, db)
        
        # 3. 快照事实卡
        claim_snapshot = await self.snapshot_claims(story_packet_id, db)
        
        # 4. 快照报告
        risk_snapshot = await self.snapshot_risk_report(story_packet_id, db)
        redaction_snapshot = await self.snapshot_redaction_report(story_packet_id, db)
        
        # 5. 计算哈希
        hash_data = {
            "draft_id": draft.id if draft else None,
            "evidence_id": evidence_snapshot.id if evidence_snapshot else None,
            "claims": claim_snapshot,
            "risk_report": risk_snapshot,
            "redaction_report": redaction_snapshot,
            "timestamp": datetime.utcnow().isoformat(),
        }
        bundle_hash = self.compute_bundle_hash(hash_data)
        
        # 6. 创建 Review Bundle
        bundle = ReviewBundle(
            id=str(uuid.uuid4()),
            story_packet_id=story_packet_id,
            channel_package_id=channel_package_id,
            bundle_type=bundle_type,
            draft_version_id=draft.id if draft else None,
            evidence_pack_id=evidence_snapshot.id if evidence_snapshot else None,
            claim_snapshot=json.dumps(claim_snapshot, ensure_ascii=False),
            risk_report_snapshot=json.dumps(risk_snapshot, ensure_ascii=False) if risk_snapshot else None,
            redaction_report_snapshot=json.dumps(redaction_snapshot, ensure_ascii=False) if redaction_snapshot else None,
            bundle_hash=bundle_hash,
            status="active",
            submitted_by=submitted_by,
            submit_note=submit_note,
        )
        db.add(bundle)
        await db.flush()
        
        return bundle

    async def supersede_old_bundles(
        self, story_packet_id: str, db: AsyncSession, exclude_id: str | None = None
    ):
        """将旧的活跃 bundle 标记为 superseded"""
        result = await db.execute(
            select(ReviewBundle)
            .where(ReviewBundle.story_packet_id == story_packet_id)
            .where(ReviewBundle.status == "active")
        )
        bundles = result.scalars().all()
        for bundle in bundles:
            if bundle.id != exclude_id:
                bundle.status = "superseded"

    async def cancel_related_approval_tasks(
        self, bundle_id: str, db: AsyncSession
    ):
        """取消关联的审批任务"""
        from app.models.approval_task import ApprovalTask
        result = await db.execute(
            select(ApprovalTask)
            .where(ApprovalTask.review_bundle_id == bundle_id)
            .where(ApprovalTask.status.in_(["pending", "in_review"]))
        )
        tasks = result.scalars().all()
        for task in tasks:
            task.status = "cancelled"


snapshot_service = SnapshotService()
