# =============================================================================
# config.py — Konfigurasi terpusat dengan Pydantic Settings
#
# Pydantic Settings membaca nilai dari environment variable atau .env file.
# Seluruh konfigurasi aplikasi (DB URL, JWT secret, dll.) hidup di satu tempat
# sehingga mudah diganti saat testing tanpa mengubah kode.
# =============================================================================

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    # Format: postgresql+asyncpg://user:pass@host:port/dbname
    # asyncpg adalah async driver; SQLAlchemy 2.0 mendukungnya via create_async_engine
    DATABASE_URL: str = (
        "postgresql+asyncpg://crud_user:crud_pass@localhost:5432/crud_db"
    )
    DATABASE_TEST_URL: str = (
        "postgresql+asyncpg://crud_user:crud_pass@localhost:5433/crud_test_db"
    )

    # ── JWT ───────────────────────────────────────────────────────────────────
    # SECRET_KEY harus string acak ≥32 karakter di production
    # Generate: python -c "import secrets; print(secrets.token_hex(32))"
    JWT_SECRET_KEY: str = "change-me-in-production-use-secrets-token-hex-32"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    # "10/minute" artinya max 10 request per IP per menit
    RATE_LIMIT_DEFAULT: str = "60/minute"
    RATE_LIMIT_AUTH: str = "10/minute"   # endpoint login lebih ketat

    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "CRUD API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Pagination ────────────────────────────────────────────────────────────
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Baca dari file .env jika ada (opsional)
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache           # singleton — dibuat sekali, di-cache selamanya
def get_settings() -> Settings:
    return Settings()
