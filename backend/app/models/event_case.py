"""事件案卷模型：承载同一事件的持续背景、时间线、人物机构、历史稿件、风险等级。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import JSONType


class EventCase(Base):
    __tablename__ = "event_cases"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="candidate",
    )
    risk_level: Mapped[str] = mapped_column(
        String(4), nullable=False, default="L0",
    )
    desk: Mapped[str | None] = mapped_column(String(50), nullable=True)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tags: Mapped[str] = mapped_column(JSONType, default="[]")
    timeline_data: Mapped[str] = mapped_column(JSONType, default="[]")
    entity_graph_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
    merged_into_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("event_cases.id"), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EventSourceItem(Base):
    """事件关联来源。"""
    __tablename__ = "event_source_items"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    event_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("event_cases.id"), nullable=False, index=True,
    )
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_5w1h: Mapped[str | None] = mapped_column(JSONType, nullable=True)
    file_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_tags: Mapped[str] = mapped_column(JSONType, default="[]")
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
    )
