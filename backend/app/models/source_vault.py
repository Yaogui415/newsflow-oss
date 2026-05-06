"""来源保密库模型：高度敏感身份信息隔离存储。真实身份和联系方式使用应用层加密（AES-256）。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import JSONType


class SourceVault(Base):
    __tablename__ = "source_vault"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    alias_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    real_identity_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    contact_info_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    protection_level: Mapped[str] = mapped_column(String(20), nullable=False)
    related_event_ids: Mapped[str] = mapped_column(JSONType, default="[]")
    access_log: Mapped[str] = mapped_column(JSONType, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
