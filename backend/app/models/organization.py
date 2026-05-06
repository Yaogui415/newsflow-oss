"""组织/团队模型：支持多团队协作。"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, comment="团队名称")
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, comment="显示名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="团队简介")
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, comment="创建者用户ID")
    invite_code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False,
        default=lambda: uuid.uuid4().hex[:8].upper(),
        comment="邀请码",
    )
    max_members: Mapped[int] = mapped_column(Integer, default=50, comment="最大成员数")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
    )
