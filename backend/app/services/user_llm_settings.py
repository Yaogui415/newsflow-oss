"""用户级 LLM Key 设置服务。"""

import base64
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_llm_settings (
    user_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'openai',
    api_key_cipher TEXT,
    daily_budget_usd REAL,
    model_preference TEXT,
    updated_at TEXT NOT NULL
)
"""


class UserLLMSettingsService:
    async def ensure_table(self, db: AsyncSession) -> None:
        await db.execute(text(CREATE_TABLE_SQL))

    @staticmethod
    def _encode_api_key(api_key: str) -> str:
        return base64.b64encode(api_key.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _decode_api_key(cipher: str | None) -> str | None:
        if not cipher:
            return None
        try:
            return base64.b64decode(cipher.encode("utf-8")).decode("utf-8")
        except Exception:
            return None

    @staticmethod
    def _mask_api_key(api_key: str | None) -> str | None:
        if not api_key:
            return None
        if len(api_key) <= 8:
            return "*" * len(api_key)
        return f"{api_key[:4]}{'*' * (len(api_key) - 8)}{api_key[-4:]}"

    async def get_user_setting(self, db: AsyncSession, user_id: str, include_raw_key: bool = False) -> dict:
        await self.ensure_table(db)
        row = (
            await db.execute(
                text(
                    """
                    SELECT user_id, provider, api_key_cipher, daily_budget_usd, model_preference, updated_at
                    FROM user_llm_settings
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            )
        ).mappings().first()

        if not row:
            return {
                "user_id": user_id,
                "provider": "openai",
                "has_api_key": False,
                "api_key_masked": None,
                "daily_budget_usd": None,
                "model_preference": None,
                "updated_at": None,
                "api_key": None,
            }

        raw_key = self._decode_api_key(row["api_key_cipher"])
        return {
            "user_id": row["user_id"],
            "provider": row["provider"],
            "has_api_key": bool(raw_key),
            "api_key_masked": self._mask_api_key(raw_key),
            "daily_budget_usd": row["daily_budget_usd"],
            "model_preference": row["model_preference"],
            "updated_at": row["updated_at"],
            "api_key": raw_key if include_raw_key else None,
        }

    async def upsert_user_setting(
        self,
        db: AsyncSession,
        user_id: str,
        api_key: str,
        daily_budget_usd: float | None = None,
        model_preference: str | None = None,
        provider: str = "openai",
    ) -> dict:
        await self.ensure_table(db)
        now_iso = datetime.utcnow().isoformat()
        await db.execute(
            text(
                """
                INSERT INTO user_llm_settings (
                    user_id, provider, api_key_cipher, daily_budget_usd, model_preference, updated_at
                )
                VALUES (:user_id, :provider, :api_key_cipher, :daily_budget_usd, :model_preference, :updated_at)
                ON CONFLICT(user_id) DO UPDATE SET
                    provider = excluded.provider,
                    api_key_cipher = excluded.api_key_cipher,
                    daily_budget_usd = excluded.daily_budget_usd,
                    model_preference = excluded.model_preference,
                    updated_at = excluded.updated_at
                """
            ),
            {
                "user_id": user_id,
                "provider": provider,
                "api_key_cipher": self._encode_api_key(api_key),
                "daily_budget_usd": daily_budget_usd,
                "model_preference": model_preference,
                "updated_at": now_iso,
            },
        )
        return await self.get_user_setting(db, user_id=user_id)

    async def clear_user_setting(self, db: AsyncSession, user_id: str) -> None:
        await self.ensure_table(db)
        await db.execute(
            text("DELETE FROM user_llm_settings WHERE user_id = :user_id"),
            {"user_id": user_id},
        )


user_llm_settings_service = UserLLMSettingsService()
