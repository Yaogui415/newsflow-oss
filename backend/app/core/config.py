"""应用配置：使用 pydantic-settings 管理，敏感配置通过环境变量注入。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── 应用 ──
    APP_NAME: str = "NewsFlow"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # ── 数据库 ──
    DATABASE_URL: str = "sqlite+aiosqlite:///./newsflow.db"
    DATABASE_ECHO: bool = False

    # ── Redis ──
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── JWT 认证 ──
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    ALGORITHM: str = "HS256"

    # ── LLM ──
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str | None = None
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_DEFAULT_MODEL: str = "gpt-4o-mini"
    LLM_HIGH_RISK_MODEL: str = "gpt-4o"
    LLM_TEMPERATURE_DEFAULT: float = 0.3
    LLM_TEMPERATURE_VERIFICATION: float = 0.0
    LLM_DAILY_BUDGET_USD: float = 100.0
    LLM_PER_PACKET_BUDGET_USD: float = 5.0

    # ── MinIO / S3 文件存储 ──
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_PUBLIC: str = "newsflow-public"
    MINIO_BUCKET_RESTRICTED: str = "newsflow-restricted"

    # ── Elasticsearch ──
    ELASTICSEARCH_URL: str = "http://localhost:9200"

    # ── Source Vault 加密（独立密钥，不复用 SECRET_KEY） ──
    SOURCE_VAULT_ENCRYPTION_KEY: str = "change-me-source-vault-key-32bytes!"

    # ── CORS ──
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://*.netlify.app",
    ]
    CORS_ORIGIN_REGEX: str = r"https?://(localhost|127\.0\.0\.1)(:\d+)?$|https://.*\.vercel\.app$|https://.*\.netlify\.app$"


settings = Settings()
