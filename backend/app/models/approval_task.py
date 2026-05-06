"""签发任务模型：承载"谁在什么时候需要审批什么"的待办。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import JSONType


class ApprovalTask(Base):
    __tablename__ = "approval_tasks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    review_bundle_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("review_bundles.id"), nullable=False, index=True,
    )
    approval_stage: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    policy_rule: Mapped[str | None] = mapped_column(JSONType, nullable=True)
    signer_slots: Mapped[str] = mapped_column(JSONType, nullable=False, default="[]")
    execution_mode: Mapped[str] = mapped_column(String(15), nullable=False, default="sequential")
    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
    )
