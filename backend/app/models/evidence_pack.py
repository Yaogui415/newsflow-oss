"""证据包模型：把所有来源、原始材料、抽取结果整理成结构化证据集合。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import JSONType


class EvidencePack(Base):
    __tablename__ = "evidence_packs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    story_packet_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("story_packets.id"), nullable=False, index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sources: Mapped[str] = mapped_column(JSONType, nullable=False, default="[]")
    citation_anchors: Mapped[str] = mapped_column(JSONType, default="[]")
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    snapshot_of_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evidence_packs.id"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
