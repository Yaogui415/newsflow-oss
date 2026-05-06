"""送审快照包模型：把送审时刻的所有关键版本冻结为一组审批快照。不可修改（status 除外）。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import JSONType


class ReviewBundle(Base):
    __tablename__ = "review_bundles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    story_packet_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("story_packets.id"), nullable=True,
    )
    channel_package_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("channel_packages.id"), nullable=True,
    )
    bundle_type: Mapped[str] = mapped_column(String(20), nullable=False)
    draft_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("draft_versions.id"), nullable=True,
    )
    evidence_pack_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evidence_packs.id"), nullable=True,
    )
    claim_snapshot: Mapped[str | None] = mapped_column(JSONType, nullable=True)
    risk_report_snapshot: Mapped[str | None] = mapped_column(JSONType, nullable=True)
    redaction_report_snapshot: Mapped[str | None] = mapped_column(JSONType, nullable=True)
    bundle_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    submitted_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
    submit_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
    )
