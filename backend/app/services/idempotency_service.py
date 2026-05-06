"""幂等键服务：支持请求去重与安全重试。"""

import json
import hashlib
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


CREATE_IDEMPOTENCY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS idempotency_records (
    scope TEXT NOT NULL,
    object_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    idem_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    response_json TEXT,
    error_message TEXT,
    attempts INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (scope, object_id, user_id, idem_key)
)
"""


class IdempotencyService:
    async def ensure_table(self, db: AsyncSession) -> None:
        await db.execute(text(CREATE_IDEMPOTENCY_TABLE_SQL))

    @staticmethod
    def _hash_payload(payload: dict) -> str:
        normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(normalized.encode()).hexdigest()

    async def begin_request(
        self,
        db: AsyncSession,
        *,
        scope: str,
        object_id: str,
        user_id: str,
        idem_key: str,
        payload: dict,
    ) -> dict:
        await self.ensure_table(db)
        now = datetime.utcnow().isoformat()
        request_hash = self._hash_payload(payload)

        existing = (
            await db.execute(
                text(
                    """
                    SELECT scope, object_id, user_id, idem_key, request_hash, status,
                           response_json, error_message, attempts, created_at, updated_at
                    FROM idempotency_records
                    WHERE scope = :scope
                      AND object_id = :object_id
                      AND user_id = :user_id
                      AND idem_key = :idem_key
                    """
                ),
                {
                    "scope": scope,
                    "object_id": object_id,
                    "user_id": user_id,
                    "idem_key": idem_key,
                },
            )
        ).mappings().first()

        if not existing:
            await db.execute(
                text(
                    """
                    INSERT INTO idempotency_records (
                        scope, object_id, user_id, idem_key, request_hash, status,
                        response_json, error_message, attempts, created_at, updated_at
                    )
                    VALUES (
                        :scope, :object_id, :user_id, :idem_key, :request_hash, 'processing',
                        NULL, NULL, 1, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "scope": scope,
                    "object_id": object_id,
                    "user_id": user_id,
                    "idem_key": idem_key,
                    "request_hash": request_hash,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            return {"state": "new", "request_hash": request_hash}

        if existing["request_hash"] != request_hash:
            return {"state": "conflict", "record": dict(existing)}

        status = existing["status"]
        if status == "succeeded":
            return {"state": "replay", "record": dict(existing)}

        if status == "processing":
            return {"state": "processing", "record": dict(existing)}

        # failed: allow retry with same key+same payload
        attempts = int(existing["attempts"] or 1) + 1
        await db.execute(
            text(
                """
                UPDATE idempotency_records
                SET status = 'processing',
                    error_message = NULL,
                    attempts = :attempts,
                    updated_at = :updated_at
                WHERE scope = :scope
                  AND object_id = :object_id
                  AND user_id = :user_id
                  AND idem_key = :idem_key
                """
            ),
            {
                "attempts": attempts,
                "updated_at": now,
                "scope": scope,
                "object_id": object_id,
                "user_id": user_id,
                "idem_key": idem_key,
            },
        )
        return {"state": "retry", "request_hash": request_hash}

    async def mark_succeeded(
        self,
        db: AsyncSession,
        *,
        scope: str,
        object_id: str,
        user_id: str,
        idem_key: str,
        response_payload: dict,
    ) -> None:
        await self.ensure_table(db)
        await db.execute(
            text(
                """
                UPDATE idempotency_records
                SET status = 'succeeded',
                    response_json = :response_json,
                    updated_at = :updated_at
                WHERE scope = :scope
                  AND object_id = :object_id
                  AND user_id = :user_id
                  AND idem_key = :idem_key
                """
            ),
            {
                "response_json": json.dumps(response_payload, ensure_ascii=False),
                "updated_at": datetime.utcnow().isoformat(),
                "scope": scope,
                "object_id": object_id,
                "user_id": user_id,
                "idem_key": idem_key,
            },
        )

    async def mark_failed(
        self,
        db: AsyncSession,
        *,
        scope: str,
        object_id: str,
        user_id: str,
        idem_key: str,
        error_message: str,
    ) -> None:
        await self.ensure_table(db)
        await db.execute(
            text(
                """
                UPDATE idempotency_records
                SET status = 'failed',
                    error_message = :error_message,
                    updated_at = :updated_at
                WHERE scope = :scope
                  AND object_id = :object_id
                  AND user_id = :user_id
                  AND idem_key = :idem_key
                """
            ),
            {
                "error_message": error_message[:500],
                "updated_at": datetime.utcnow().isoformat(),
                "scope": scope,
                "object_id": object_id,
                "user_id": user_id,
                "idem_key": idem_key,
            },
        )


idempotency_service = IdempotencyService()
