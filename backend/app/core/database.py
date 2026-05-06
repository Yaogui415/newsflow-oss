"""数据库引擎与会话管理。"""

import logging
import ssl as _ssl_mod
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)


def _resolve_db_url(raw_url: str) -> tuple[str, bool]:
    """将 Neon/Supabase 给出的 postgresql:// 自动转为 asyncpg 驱动格式。
    返回 (url, need_ssl)。"""
    need_ssl = False
    if raw_url.startswith("postgresql://"):
        raw_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql+asyncpg://", 1)

    if "asyncpg" in raw_url:
        parsed = urlparse(raw_url)
        qs = parse_qs(parsed.query)
        if "sslmode" in qs:
            need_ssl = qs["sslmode"][0] in ("require", "verify-ca", "verify-full")
            del qs["sslmode"]
            flat_qs = {k: v[0] for k, v in qs.items()}
            new_query = urlencode(flat_qs)
            raw_url = urlunparse(parsed._replace(query=new_query))
    return raw_url, need_ssl


_db_url, _need_ssl = _resolve_db_url(settings.DATABASE_URL)
_is_sqlite = _db_url.startswith("sqlite")

_engine_kwargs: dict = {
    "echo": settings.DATABASE_ECHO,
}
if not _is_sqlite:
    _engine_kwargs.update(pool_size=5, max_overflow=5, pool_pre_ping=True, pool_timeout=10)
    _connect_args: dict = {"timeout": 5}
    if _need_ssl:
        ssl_ctx = _ssl_mod.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = _ssl_mod.CERT_NONE
        _connect_args["ssl"] = ssl_ctx
    _engine_kwargs["connect_args"] = _connect_args

engine = create_async_engine(_db_url, **_engine_kwargs)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""
    pass


_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS org_id VARCHAR(36)",
    "ALTER TABLE story_packets ALTER COLUMN event_case_id DROP NOT NULL",
    "UPDATE story_packets SET status = 'channel_packaging' WHERE status = 'channel_adapting'",
    "UPDATE story_packets SET status = 'published' WHERE status = 'publishing'",
]

_MIGRATIONS_SQLITE = [
    ("users", "org_id", "ALTER TABLE users ADD COLUMN org_id VARCHAR(36)"),
]


async def init_db():
    """在应用启动时自动创建所有表，并执行增量迁移。"""
    try:
        import app.models  # noqa: F401  确保所有模型被导入
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized successfully.")
    except Exception as exc:
        logger.warning("init_db failed (will retry on first request): %s", exc)

    # 增量列迁移
    try:
        async with engine.begin() as conn:
            if _is_sqlite:
                for table, col, sql in _MIGRATIONS_SQLITE:
                    try:
                        from sqlalchemy import text
                        result = await conn.execute(text(f"PRAGMA table_info({table})"))
                        columns = [r[1] for r in result.fetchall()]
                        if col not in columns:
                            await conn.execute(text(sql))
                            logger.info("Migration: added column %s.%s", table, col)
                    except Exception as e:
                        logger.warning("SQLite migration skipped: %s", e)
            else:
                from sqlalchemy import text
                for sql in _MIGRATIONS:
                    try:
                        await conn.execute(text(sql))
                    except Exception as e:
                        logger.warning("Migration skipped: %s", e)
                logger.info("Column migrations completed.")
    except Exception as exc:
        logger.warning("Migrations failed: %s", exc)


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库会话。"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
