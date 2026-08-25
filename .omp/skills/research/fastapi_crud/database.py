# =============================================================================
# database.py — Setup SQLAlchemy Async Engine + Session
#
# SQLAlchemy 2.0 dengan async engine memungkinkan query database berjalan
# secara non-blocking. Setiap request mendapatkan session-nya sendiri melalui
# dependency injection, lalu di-commit atau di-rollback otomatis di akhir.
# =============================================================================

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from config import get_settings

settings = get_settings()

# ── Engine ────────────────────────────────────────────────────────────────────
# echo=True mencetak SQL ke stdout — aktifkan hanya saat DEBUG
# pool_size: jumlah koneksi persistent di pool
# max_overflow: koneksi tambahan saat pool penuh (total = pool_size + max_overflow)
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,          # test koneksi sebelum dipakai (hindari stale conn)
)

# ── Session Factory ───────────────────────────────────────────────────────────
# async_sessionmaker menggantikan sessionmaker untuk async engine
# expire_on_commit=False: objek tetap bisa diakses setelah commit tanpa lazy-load
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,     # manual flush agar lebih predictable
    autocommit=False,
)

# ── Base Model ────────────────────────────────────────────────────────────────
# Semua ORM model inherit dari Base ini.
# DeclarativeBase (SQLAlchemy 2.0) menggantikan declarative_base() lama.
class Base(DeclarativeBase):
    pass


# ── Utility: buat semua tabel ─────────────────────────────────────────────────
async def create_tables() -> None:
    """Buat semua tabel dari metadata ORM. Dipakai saat testing / dev."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables() -> None:
    """Hapus semua tabel. HANYA untuk testing."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
