"""报道任务包模型：承载一次具体报道任务的全生命周期。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import JSONType


class StoryPacket(Base):
    __tablename__ = "story_packets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    event_case_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("event_cases.id"), nullable=True, index=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    angle_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="created")
    risk_level: Mapped[str] = mapped_column(String(4), nullable=False, default="L0")
    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
    desk: Mapped[str | None] = mapped_column(String(50), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    publish_plan: Mapped[str | None] = mapped_column(JSONType, nullable=True)
    blockers: Mapped[str] = mapped_column(JSONType, default="[]")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
    )
