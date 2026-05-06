"""统一事件审计服务：审批与工作流事件统一写入/查询。"""

import json
import uuid
import hashlib
import base64
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


CREATE_AUDIT_LOGS_SQL = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    actor_id TEXT,
    actor_type TEXT NOT NULL,
    action TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    details TEXT,
    previous_hash TEXT,
    ai_model TEXT,
    ai_prompt_hash TEXT,
    ai_token_usage TEXT,
    override_ai_flag INTEGER DEFAULT 0,
    override_reason TEXT,
    created_at TEXT NOT NULL
)
"""


class EventAuditService:
    @staticmethod
    def encode_cursor(created_at: str, event_id: str) -> str:
        raw = f"{created_at}|{event_id}"
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")

    @staticmethod
    def decode_cursor(cursor: str | None) -> tuple[str, str] | None:
        if not cursor:
            return None
        try:
            raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
            created_at, event_id = raw.split("|", 1)
            return created_at, event_id
        except Exception:
            return None

    async def ensure_table(self, db: AsyncSession) -> None:
        await db.execute(text(CREATE_AUDIT_LOGS_SQL))

    async def _get_last_hash(self, db: AsyncSession) -> str | None:
        row = (
            await db.execute(
                text(
                    """
                    SELECT id, actor_id, actor_type, action, object_type, object_id, details, previous_hash, created_at
                    FROM audit_logs
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                )
            )
        ).mappings().first()
        if not row:
            return None

        details = row["details"]
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except Exception:
                details = {}

        content = json.dumps(
            {
                "id": row["id"],
                "timestamp": row["created_at"],
                "actor_id": row["actor_id"],
                "action": row["action"],
                "object_type": row["object_type"],
                "object_id": row["object_id"],
                "details": details,
                "previous_hash": row["previous_hash"],
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(content.encode()).hexdigest()

    async def append_event(
        self,
        db: AsyncSession,
        *,
        actor_id: str | None,
        actor_type: str,
        action: str,
        object_type: str,
        object_id: str,
        details: dict | None = None,
        override_ai_flag: bool = False,
        override_reason: str | None = None,
    ) -> str:
        await self.ensure_table(db)
        event_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        previous_hash = await self._get_last_hash(db)

        await db.execute(
            text(
                """
                INSERT INTO audit_logs (
                    id, actor_id, actor_type, action, object_type, object_id,
                    details, previous_hash, override_ai_flag, override_reason, created_at
                )
                VALUES (
                    :id, :actor_id, :actor_type, :action, :object_type, :object_id,
                    :details, :previous_hash, :override_ai_flag, :override_reason, :created_at
                )
                """
            ),
            {
                "id": event_id,
                "actor_id": actor_id,
                "actor_type": actor_type,
                "action": action,
                "object_type": object_type,
                "object_id": object_id,
                "details": json.dumps(details or {}, ensure_ascii=False),
                "previous_hash": previous_hash,
                "override_ai_flag": 1 if override_ai_flag else 0,
                "override_reason": override_reason,
                "created_at": created_at,
            },
        )
        return event_id

    async def list_events(
        self,
        db: AsyncSession,
        *,
        object_type: str | None = None,
        object_id: str | None = None,
        action: str | None = None,
        actor_type: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict:
        await self.ensure_table(db)

        clauses = []
        page_limit = max(1, min(limit, 200))
        fetch_limit = page_limit + 1
        params: dict = {"limit": fetch_limit}

        if object_type:
            clauses.append("object_type = :object_type")
            params["object_type"] = object_type
        if object_id:
            clauses.append("object_id = :object_id")
            params["object_id"] = object_id
        if action:
            clauses.append("action = :action")
            params["action"] = action
        if actor_type:
            clauses.append("actor_type = :actor_type")
            params["actor_type"] = actor_type

        cursor_decoded = self.decode_cursor(cursor)
        if cursor_decoded:
            cursor_created_at, cursor_id = cursor_decoded
            clauses.append("(created_at < :cursor_created_at OR (created_at = :cursor_created_at AND id < :cursor_id))")
            params["cursor_created_at"] = cursor_created_at
            params["cursor_id"] = cursor_id

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        rows = list((
            await db.execute(
                text(
                    f"""
                    SELECT id, actor_id, actor_type, action, object_type, object_id,
                           details, previous_hash, override_ai_flag, override_reason, created_at
                    FROM audit_logs
                    {where}
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            )
        ).mappings().all())

        has_more = len(rows) > page_limit
        page_rows = rows[:page_limit]

        result = []
        for row in page_rows:
            details = row["details"]
            if isinstance(details, str):
                try:
                    details = json.loads(details)
                except Exception:
                    details = {}

            result.append(
                {
                    "id": row["id"],
                    "actor_id": row["actor_id"],
                    "actor_type": row["actor_type"],
                    "action": row["action"],
                    "object_type": row["object_type"],
                    "object_id": row["object_id"],
                    "details": details,
                    "previous_hash": row["previous_hash"],
                    "override_ai_flag": bool(row["override_ai_flag"]),
                    "override_reason": row["override_reason"],
                    "created_at": row["created_at"],
                }
            )

        next_cursor = None
        if has_more and result:
            last = result[-1]
            next_cursor = self.encode_cursor(last["created_at"], last["id"])

        return {
            "items": result,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "limit": page_limit,
        }


event_audit_service = EventAuditService()
