# =============================================================================
# tests/conftest.py — Shared Fixtures untuk Semua Test
#
# Strategi testing:
#   - Test DB TERPISAH dari DB development (DATABASE_TEST_URL)
#   - Tabel di-buat ulang setiap sesi test (drop + create)
#   - Setiap test mendapat DB session sendiri yang di-ROLLBACK di akhir
#     → test tidak saling mempengaruhi (isolasi sempurna)
#   - FastAPI dependency `get_db` di-override dengan session test
#   - AsyncClient (httpx) digunakan sebagai HTTP client (bukan TestClient sinkron)
#
# Flow per-test:
#   1. session_fixture: buat AsyncSession, BEGIN transaction
#   2. client_fixture: override get_db → pakai session test
#   3. Test berjalan dengan client HTTP
#   4. Teardown: ROLLBACK session → DB bersih untuk test berikutnya
# =============================================================================

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)

# Set DATABASE_URL ke test DB sebelum import apapun dari app
import os
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://crud_user:crud_pass@localhost:5433/crud_test_db"
)

from config import get_settings
from database import Base, drop_tables, create_tables
from dependencies import get_db
from main import app

settings = get_settings()

# ── Test Engine (test DB, port 5433) ─────────────────────────────────────────
test_engine = create_async_engine(
    settings.DATABASE_TEST_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ── pytest-asyncio mode ───────────────────────────────────────────────────────
# Konfigurasi ini bisa juga di pytest.ini: asyncio_mode = auto
pytest_plugins = ("anyio",)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: Buat tabel SEKALI per test session
# ─────────────────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """
    scope="session": fixture ini hanya dijalankan sekali untuk semua test.
    Buat tabel di awal, hapus di akhir.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)    # bersihkan dulu
        await conn.run_sync(Base.metadata.create_all)  # buat ulang
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: DB Session per-test dengan ROLLBACK otomatis
# ─────────────────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Setiap test mendapat session tersendiri.
    ROLLBACK di akhir memastikan data test tidak bocor ke test lain.

    Teknik: kita pakai SAVEPOINT agar ROLLBACK tidak menutup koneksi
    (koneksi pool di-reuse untuk efisiensi).
    """
    async with test_engine.connect() as conn:
        await conn.begin()     # outer transaction
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()   # hapus semua perubahan test ini


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: HTTP Client dengan dependency override
# ─────────────────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    AsyncClient dari httpx — bisa memanggil endpoint FastAPI tanpa server nyata.
    ASGITransport meneruskan request langsung ke ASGI app.

    Kunci: kita override `get_db` dependency dengan session test.
    Ini memastikan handler memakai DB yang sama dengan test kita.
    """
    async def override_get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    # Bersihkan override setelah test
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Helper Fixtures: User & Token
# ─────────────────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def admin_token(client: AsyncClient) -> str:
    """
    Buat user admin, login, return access_token.
    Digunakan di test yang butuh autentikasi Admin.
    """
    await client.post("/users/", json={
        "username": "testadmin",
        "email": "admin@test.com",
        "password": "AdminPass1",
        "role": "admin",
    })
    resp = await client.post("/auth/login", json={
        "username": "testadmin",
        "password": "AdminPass1",
    })
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def editor_token(client: AsyncClient) -> str:
    """Buat user editor, login, return access_token."""
    await client.post("/users/", json={
        "username": "testeditor",
        "email": "editor@test.com",
        "password": "EditorPass1",
        "role": "editor",
    })
    resp = await client.post("/auth/login", json={
        "username": "testeditor",
        "password": "EditorPass1",
    })
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def viewer_token(client: AsyncClient) -> str:
    """Buat user viewer (role default), login, return access_token."""
    await client.post("/users/", json={
        "username": "testviewer",
        "email": "viewer@test.com",
        "password": "ViewerPass1",
    })
    resp = await client.post("/auth/login", json={
        "username": "testviewer",
        "password": "ViewerPass1",
    })
    return resp.json()["access_token"]


def auth_header(token: str) -> dict:
    """Helper: buat dict Authorization header."""
    return {"Authorization": f"Bearer {token}"}
