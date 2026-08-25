# =============================================================================
# auth.py — JWT Authentication + Password Hashing
#
# Flow:
#   1. User POST /auth/login dengan username+password
#   2. Kita verifikasi password dengan bcrypt (passlib)
#   3. Jika valid, kita buat access_token (pendek, 30 menit) dan
#      refresh_token (panjang, 7 hari)
#   4. Setiap request protected harus kirim "Authorization: Bearer <token>"
#   5. Kita decode token, validasi expiry, ambil user dari DB
#   6. Untuk perpanjang sesi: POST /auth/refresh dengan refresh_token
#
# Kenapa dua token?
#   - access_token pendek → jika bocor, window serangan kecil
#   - refresh_token panjang → user tidak perlu login ulang setiap 30 menit
#     Tapi refresh_token disimpan di httpOnly cookie di production (bukan response body)
# =============================================================================

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from config import get_settings
from schemas import TokenPayload
from models import UserRole

settings = get_settings()

# ── Password Context ──────────────────────────────────────────────────────────
# bcrypt: fungsi hash satu arah dengan salt otomatis.
# deprecated="auto" otomatis upgrade hash lama ke scheme terbaru.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Hash password dengan bcrypt. Hasilnya disimpan di DB."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifikasi password input vs hash di DB.
    Menggunakan constant-time comparison untuk mencegah timing attack.
    """
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT Token Creation ────────────────────────────────────────────────────────
def _create_token(
    subject: str,              # biasanya user_id sebagai string
    role: UserRole,
    expires_delta: timedelta,
    token_type: str = "access",
) -> str:
    """
    Buat JWT dengan payload: sub, role, type, exp.
    'sub' (subject) adalah standar JWT claim untuk mengidentifikasi principal.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role.value,
        "type": token_type,
        "iat": now,                          # issued at
        "exp": now + expires_delta,          # expiry
        "jti": str(uuid.uuid4()),            # JWT ID — untuk invalidasi token (bisa disimpan di Redis)
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: uuid.UUID, role: UserRole) -> str:
    """Access token: pendek (30 menit default)."""
    return _create_token(
        subject=str(user_id),
        role=role,
        expires_delta=timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access",
    )


def create_refresh_token(user_id: uuid.UUID, role: UserRole) -> str:
    """Refresh token: panjang (7 hari default)."""
    return _create_token(
        subject=str(user_id),
        role=role,
        expires_delta=timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh",
    )


# ── JWT Token Decoding ────────────────────────────────────────────────────────
def decode_token(token: str, expected_type: str = "access") -> TokenPayload:
    """
    Decode dan validasi JWT.
    Raise ValueError jika token invalid, expired, atau tipe salah.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise ValueError(f"Token tidak valid: {exc}") from exc

    # Validasi tipe token (access vs refresh)
    if payload.get("type") != expected_type:
        raise ValueError(f"Token bukan tipe '{expected_type}'")

    # Parse exp sebagai integer (UNIX timestamp)
    exp = payload.get("exp")
    if exp is None:
        raise ValueError("Token tidak memiliki expiry")

    return TokenPayload(
        sub=payload["sub"],
        role=UserRole(payload["role"]),
        exp=int(exp),
    )
