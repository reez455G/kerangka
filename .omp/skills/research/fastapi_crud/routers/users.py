# =============================================================================
# routers/users.py — User Endpoints
#
# Endpoint:
#   POST   /users/           Registrasi user baru
#   GET    /users/           List semua user (pagination + filter) [ADMIN only]
#   GET    /users/me         Profil user yang sedang login
#   GET    /users/{id}       Detail user by ID
#   PUT    /users/{id}       Ganti semua field user [ADMIN]
#   PATCH  /users/{id}       Update sebagian field user [ADMIN or SELF]
#   DELETE /users/{id}       Soft-delete user [ADMIN]
#
# HTTP status code conventions:
#   201 Created    → resource baru berhasil dibuat
#   200 OK         → berhasil dengan data
#   204 No Content → berhasil tanpa data (DELETE)
#   404 Not Found  → resource tidak ada
#   409 Conflict   → duplikat (username/email sudah dipakai)
#   403 Forbidden  → tidak punya izin
# =============================================================================

import uuid
from typing import Annotated, Optional
from fastapi import APIRouter, HTTPException, status, Query

import crud
from dependencies import DBSession, CurrentUser, AdminUser, Pagination
from schemas import (
    UserCreate, UserUpdate, UserPatch,
    UserResponse, PaginatedResponse,
)
from models import UserRole

router = APIRouter(prefix="/users", tags=["Users"])


# ─────────────────────────────────────────────────────────────────────────────
# POST /users — Registrasi
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrasi user baru",
)
async def register_user(body: UserCreate, db: DBSession):
    """
    Endpoint publik — tidak perlu token.
    Cek duplikat username dan email sebelum buat user.
    """
    if await crud.get_user_by_username(db, body.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{body.username}' sudah digunakan",
        )
    if await crud.get_user_by_email(db, body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{body.email}' sudah digunakan",
        )

    user = await crud.create_user(db, body)
    return user


# ─────────────────────────────────────────────────────────────────────────────
# GET /users/me — Profil sendiri
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/me",
    response_model=UserResponse,
    summary="Profil user yang sedang login",
)
async def get_my_profile(current_user: CurrentUser):
    """
    '/me' harus didaftarkan SEBELUM '/{user_id}' agar FastAPI tidak
    mengira 'me' adalah UUID dan mencoba parse sebagai UUID.
    """
    return current_user


# ─────────────────────────────────────────────────────────────────────────────
# GET /users — Daftar semua user
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/",
    response_model=PaginatedResponse[UserResponse],
    summary="Daftar user (Admin only)",
)
async def list_users(
    _: AdminUser,           # underscore → dependency dijalankan, return value diabaikan
    db: DBSession,
    pagination: Pagination,
    search: Optional[str] = Query(None, description="Cari username atau email"),
    role: Optional[UserRole] = Query(None),
    is_active: Optional[bool] = Query(None),
):
    return await crud.list_users(
        db,
        page=pagination.page,
        page_size=pagination.page_size,
        search=search,
        role=role,
        is_active=is_active,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /users/{user_id} — Detail user
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Detail user by ID",
)
async def get_user(
    user_id: uuid.UUID,
    db: DBSession,
    _: CurrentUser,     # harus login, tapi semua role boleh
):
    user = await crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User dengan id '{user_id}' tidak ditemukan",
        )
    return user


# ─────────────────────────────────────────────────────────────────────────────
# PUT /users/{user_id} — Replace user (Admin only)
# ─────────────────────────────────────────────────────────────────────────────
@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="Ganti semua field user (Admin only)",
)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: DBSession,
    _: AdminUser,
):
    """
    PUT mengganti SEMUA field — klien harus mengirim semua field.
    Gunakan PATCH jika hanya ingin update sebagian.
    """
    user = await crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return await crud.update_user(db, user, body)


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /users/{user_id} — Partial update
# ─────────────────────────────────────────────────────────────────────────────
@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update sebagian field user",
)
async def patch_user(
    user_id: uuid.UUID,
    body: UserPatch,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Admin bisa edit siapa saja.
    User biasa hanya boleh edit profil sendiri.
    """
    user = await crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")

    # Authorization: hanya ADMIN atau user itu sendiri
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Anda tidak punya izin mengubah user lain",
        )

    # User biasa tidak boleh mengubah role-nya sendiri
    if current_user.role != UserRole.ADMIN and body.role is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hanya Admin yang boleh mengubah role",
        )

    return await crud.patch_user(db, user, body)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /users/{user_id} — Soft delete (Admin only)
# ─────────────────────────────────────────────────────────────────────────────
@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus user (soft delete, Admin only)",
)
async def delete_user(
    user_id: uuid.UUID,
    db: DBSession,
    current_user: AdminUser,
):
    """
    Admin tidak bisa menghapus akunnya sendiri
    (untuk mencegah sistem tanpa admin).
    """
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin tidak bisa menghapus akun sendiri",
        )

    user = await crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")

    await crud.soft_delete_user(db, user)
    # 204 → return None, FastAPI tidak akan encode response body
