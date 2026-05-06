"""风险/脱敏报告模型：独立报告对象，挂在 Story Packet 或 Channel Package 下。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import JSONType


class RiskReport(Base):
    __tablename__ = "risk_reports"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    story_packet_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("story_packets.id"), nullable=True, index=True,
    )
    channel_package_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("channel_packages.id"), nullable=True,
    )
    report_type: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    findings: Mapped[str] = mapped_column(JSONType, nullable=False, default="[]")
    severity_summary: Mapped[str | None] = mapped_column(JSONType, nullable=True)
    recommendations: Mapped[str | None] = mapped_column(JSONType, nullable=True)
    generated_by: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
    )
