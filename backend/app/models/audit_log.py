"""审计日志模型：只允许 INSERT，不允许 UPDATE/DELETE。Append-only 设计。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import JSONType


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    object_type: Mapped[str] = mapped_column(String(50), nullable=False)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    details: Mapped[str | None] = mapped_column(JSONType, nullable=True)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    ai_model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ai_token_usage: Mapped[str | None] = mapped_column(JSONType, nullable=True)

    override_ai_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(), index=True,
    )
