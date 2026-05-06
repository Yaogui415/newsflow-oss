"""事实卡模型：把稿子里的事实拆解成单条 claim，记录证据矩阵。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import JSONType


class ClaimCard(Base):
    __tablename__ = "claim_cards"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    story_packet_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("story_packets.id"), nullable=False, index=True,
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(4), nullable=False, default="L0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unverified")
    supporting_evidence: Mapped[str] = mapped_column(JSONType, default="[]")
    contradicting_evidence: Mapped[str] = mapped_column(JSONType, default="[]")
    missing_evidence: Mapped[str] = mapped_column(JSONType, default="[]")
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    manual_accept_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_anchor_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
    )
