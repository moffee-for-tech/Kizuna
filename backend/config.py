import logging
import sys

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"  # "development" | "production"

    # OpenRouter — compatible with OpenAI API
    OPENROUTER_API_KEY: str = ""
    LLM_MODEL: str = "google/gemini-3.5-flash"

    # Composio
    COMPOSIO_API_KEY: str = ""

    # Auth
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 168  # 7 days — users stay logged in for a week

    # Cookie security
    COOKIE_DOMAIN: str = ""  # e.g. ".yourdomain.com" for prod
    COOKIE_SECURE: bool = False  # True in production (HTTPS only)
    COOKIE_SAMESITE: str = "lax"  # "lax" for same-site, "none" for cross-site (requires Secure)

    # Database
    DATABASE_URL: str = "sqlite:///./data/triton.db"

    # Uploads
    UPLOAD_DIR: str = "./data/uploads"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 30

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Frontend URL (for OAuth callbacks)
    FRONTEND_URL: str = "http://localhost:3000"

    class Config:
        env_file = (".env", "../.env")
        env_file_encoding = "utf-8"


settings = Settings()


def _validate_settings():
    logger = logging.getLogger("triton.config")
    warnings = []
    errors = []
    if not settings.OPENROUTER_API_KEY:
        warnings.append("OPENROUTER_API_KEY is required — get one at https://openrouter.ai")
    if not settings.JWT_SECRET:
        errors.append("JWT_SECRET is required — generate with: openssl rand -hex 32")
    elif len(settings.JWT_SECRET) < 32:
        errors.append("JWT_SECRET should be at least 32 characters")
    if settings.ENVIRONMENT == "production" and settings.DATABASE_URL.startswith("sqlite"):
        errors.append("SQLite is not supported in production — use PostgreSQL (DATABASE_URL=postgresql://...)")
    for w in warnings:
        logger.warning(f"Config warning: {w}")
    if errors:
        for e in errors:
            logger.error(f"Config error: {e}")
        raise SystemExit(
            "Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
        )


_validate_settings()

VALID_DEPARTMENTS = ["admin", "sales", "operations", "finance", "executive"]
