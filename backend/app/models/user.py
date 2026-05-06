"""用户模型：支持多角色 RBAC。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_types import JSONType, ArrayType

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(200), nullable=False)
    roles: Mapped[str] = mapped_column(
        ArrayType, nullable=False, default="[]",
        comment="角色列表: reporter / desk_editor / compliance_editor / chief_editor / legal / operator / admin",
    )
    desk: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="所属栏目")
    org_id: Mapped[str | None] = mapped_column(String(36), nullable=True, comment="所属组织ID")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
    )
