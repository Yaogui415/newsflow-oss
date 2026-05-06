"""渠道发布包模型：承载不同平台版本的内容。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import JSONType


class ChannelPackage(Base):
    __tablename__ = "channel_packages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    story_packet_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("story_packets.id"), nullable=False, index=True,
    )
    source_draft_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("draft_versions.id"), nullable=False,
    )
    channel_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    content: Mapped[str] = mapped_column(JSONType, nullable=False, default="{}")
    drift_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    drift_threshold: Mapped[float] = mapped_column(Float, default=0.30)
    platform_rules_check: Mapped[str | None] = mapped_column(JSONType, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
    )
