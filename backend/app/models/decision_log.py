"""签发记录模型：记录真实发生的签发或退回决策。只允许 INSERT，不允许 UPDATE/DELETE。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import JSONType


class DecisionLog(Base):
    __tablename__ = "decision_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    approval_task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("approval_tasks.id"), nullable=False, index=True,
    )
    review_bundle_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("review_bundles.id"), nullable=False, index=True,
    )
    signer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False,
    )
    signer_role: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_ai_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    attachments: Mapped[str] = mapped_column(JSONType, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(),
    )
