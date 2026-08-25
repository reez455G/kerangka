# =============================================================================
# routers/auth.py — Authentication Endpoints
#
# Endpoint:
#   POST /auth/login    Masuk dengan username + password → dapat token
#   POST /auth/refresh  Tukar refresh_token lama dengan access_token baru
#   POST /auth/logout   Logout (di sini hanya sinyal ke klien untuk buang token)
#   GET  /auth/me       Alias profil user yang aktif (sama dengan /users/me)
#
# Catatan keamanan (production):
#   - Refresh token HARUS disimpan di httpOnly cookie, bukan response body
#   - Tambahkan token blocklist (Redis) untuk invalidasi saat logout
#   - Rate limit pada /login lebih ketat (lindungi dari brute-force)
# =============================================================================

from datetime import timedelta

from fastapi import APIRouter, HTTPException, status

import crud
from auth import verify_password, create_access_token, create_refresh_token, decode_token
from config import get_settings
from dependencies import DBSession, CurrentUser
from schemas import UserLoginRequest, TokenResponse, TokenRefreshRequest, UserResponse

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["Auth"])


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/login
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login dan dapatkan JWT token",
)
async def login(body: UserLoginRequest, db: DBSession):
    """
    Flow:
      1. Cari user berdasarkan username
      2. Verifikasi password dengan bcrypt (verify_password)
      3. Buat access_token (30 menit) dan refresh_token (7 hari)
      4. Return keduanya ke klien

    Pesan error SENGAJA dibuat umum ("kredensial salah") untuk
    mencegah username enumeration attack — penyerang tidak tahu
    apakah username atau password yang salah.
    """
    user = await crud.get_user_by_username(db, body.username)

    # Gunakan short-circuit yang AMAN:
    # verify_password tetap dipanggil meski user tidak ada
    # (dummy hash) untuk mencegah timing attack
    dummy_hash = "$2b$12$invalidhashfordummycheck000000000000000000000000000"
    hashed = user.hashed_password if user else dummy_hash
    password_ok = verify_password(body.password, hashed)

    if not user or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun dinonaktifkan. Hubungi administrator.",
        )

    access_token = create_access_token(user.id, user.role)
    refresh_token = create_refresh_token(user.id, user.role)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/refresh
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Perbarui access token menggunakan refresh token",
)
async def refresh_token(body: TokenRefreshRequest, db: DBSession):
    """
    Klien mengirim refresh_token yang masih valid.
    Kita decode, verifikasi user masih aktif di DB,
    lalu buat access_token baru (dan refresh_token baru — rotation).

    Token rotation: setiap refresh menghasilkan pasangan token baru.
    Ini membatasi window serangan jika refresh_token bocor.
    """
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Refresh token tidak valid: {exc}",
        )

    import uuid
    user = await crud.get_user_by_id(db, uuid.UUID(payload.sub))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User tidak ditemukan atau dinonaktifkan",
        )

    new_access = create_access_token(user.id, user.role)
    new_refresh = create_refresh_token(user.id, user.role)  # rotasi

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/logout
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout (buang token di sisi klien)",
)
async def logout(current_user: CurrentUser):
    """
    JWT bersifat stateless — server tidak menyimpan token.
    Logout 'benar' memerlukan token blocklist di Redis:
      redis.set(f"blocklist:{jti}", "1", ex=expire_seconds)
    Lalu di get_current_user, cek: if redis.get(f"blocklist:{jti}"): raise 401

    Untuk MVP ini, kita hanya return 204 dan biarkan klien buang token.
    Implementasi Redis blocklist ada di TODO production checklist.
    """
    # TODO production: masukkan JTI ke Redis blocklist
    return None


# ─────────────────────────────────────────────────────────────────────────────
# GET /auth/me — shortcut profil sendiri
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/me",
    response_model=UserResponse,
    summary="Profil user yang sedang login",
)
async def get_me(current_user: CurrentUser):
    return current_user
