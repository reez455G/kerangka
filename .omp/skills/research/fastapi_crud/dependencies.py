# =============================================================================
# dependencies.py — Dependency Injection (DI)
#
# FastAPI DI sistem: fungsi yang di-"inject" ke handler via parameter
# `Depends(func)`. Ini memungkinkan:
#   - Isolasi logic (session DB, auth, rate limit) dari handler
#   - Reuse antar endpoint tanpa duplikasi
#   - Mudah di-mock saat testing (override dependencies)
#
# Hierarki DI yang dibangun di sini:
#   get_db          → yield AsyncSession
#   get_current_user → get_db → decode token → query User
#   require_admin   → get_current_user → cek role
#   require_editor  → get_current_user → cek role
# =============================================================================

import uuid
import logging
from typing import Annotated, AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import AsyncSessionLocal
from models import User, UserRole
from auth import decode_token
from schemas import TokenPayload

logger = logging.getLogger(__name__)

# HTTPBearer mengekstrak token dari header "Authorization: Bearer <token>"
bearer_scheme = HTTPBearer(auto_error=False)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Database Session Dependency
# ─────────────────────────────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield satu AsyncSession per request.

    Pola 'async with' memastikan:
      - Session selalu ditutup meski ada exception
      - Transaction di-rollback otomatis jika terjadi error

    Di testing, dependency ini di-override dengan session ke test DB.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()   # commit jika handler selesai tanpa error
        except Exception:
            await session.rollback()
            raise


# Type alias untuk digunakan di parameter handler
DBSession = Annotated[AsyncSession, Depends(get_db)]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Authenticated User Dependency
# ─────────────────────────────────────────────────────────────────────────────
async def get_current_user(
    db: DBSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ] = None,
) -> User:
    """
    Ekstrak user dari JWT.
    - Ambil token dari Authorization header
    - Decode & validasi JWT
    - Query User dari DB (memastikan user masih exist dan aktif)
    """
    # Jika tidak ada token sama sekali
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tidak ditemukan",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload: TokenPayload = decode_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Query user dari database
    user_id = uuid.UUID(payload.sub)
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_deleted == False)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User tidak ditemukan atau sudah dihapus",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun dinonaktifkan",
        )

    return user


# Type alias — digunakan di hampir semua protected endpoint
CurrentUser = Annotated[User, Depends(get_current_user)]


# ─────────────────────────────────────────────────────────────────────────────
# 3. Role-based Authorization Dependencies
# ─────────────────────────────────────────────────────────────────────────────
async def require_admin(current_user: CurrentUser) -> User:
    """Hanya ADMIN yang boleh akses endpoint ini."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses hanya untuk Admin",
        )
    return current_user


async def require_editor(current_user: CurrentUser) -> User:
    """ADMIN dan EDITOR boleh akses endpoint ini."""
    if current_user.role not in (UserRole.ADMIN, UserRole.EDITOR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses hanya untuk Editor atau Admin",
        )
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]
EditorUser = Annotated[User, Depends(require_editor)]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Pagination Params
# ─────────────────────────────────────────────────────────────────────────────
class PaginationParams:
    """
    Dependency untuk query pagination.
    Dipakai sebagai: params: Annotated[PaginationParams, Depends()]
    FastAPI otomatis membaca ?page=1&page_size=20 dari URL.
    """
    def __init__(
        self,
        page: int = 1,
        page_size: int = 20,
    ):
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="page harus >= 1",
            )
        if page_size < 1 or page_size > 100:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="page_size harus antara 1 dan 100",
            )
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size   # SQL OFFSET


Pagination = Annotated[PaginationParams, Depends()]
