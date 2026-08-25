# =============================================================================
# schemas.py — Pydantic v2 Request/Response Schemas
#
# Skema dipisah menjadi:
#   *Base    : field umum yang dibagi antar Create/Update/Response
#   *Create  : payload saat POST (semua field wajib)
#   *Update  : payload saat PUT (semua field wajib, ganti semua)
#   *Patch   : payload saat PATCH (semua field Optional, ganti sebagian)
#   *Response: apa yang dikembalikan ke klien (tidak pernah include password)
#
# Pydantic v2 menggunakan model_config, bukan class Config inner.
# from_attributes=True (dulu orm_mode=True) memungkinkan konversi dari ORM model.
# =============================================================================

import uuid
from datetime import datetime
from typing import Optional, List, Generic, TypeVar

from pydantic import (
    BaseModel, EmailStr, Field, field_validator,
    model_validator, ConfigDict,
)
from models import UserRole, PostStatus


# ─────────────────────────────────────────────────────────────────────────────
# Generic Pagination Response
# Digunakan oleh semua endpoint list: GET /users, GET /posts, dll.
# ─────────────────────────────────────────────────────────────────────────────
T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    """
    Wrapper standar untuk semua response berupa list.

    Contoh response:
    {
        "items": [...],
        "total": 42,
        "page": 1,
        "page_size": 20,
        "pages": 3
    }
    """
    items: List[T]
    total: int              # total row di database (tanpa filter pagination)
    page: int
    page_size: int
    pages: int              # ceil(total / page_size)

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# Token Schemas
# ─────────────────────────────────────────────────────────────────────────────
class TokenResponse(BaseModel):
    """Response dari POST /auth/login"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int         # detik hingga access token kedaluwarsa


class TokenRefreshRequest(BaseModel):
    """Body untuk POST /auth/refresh"""
    refresh_token: str


class TokenPayload(BaseModel):
    """Isi dari JWT payload setelah di-decode"""
    sub: str                # user ID sebagai string
    role: UserRole
    exp: int                # expiry timestamp


# ─────────────────────────────────────────────────────────────────────────────
# User Schemas
# ─────────────────────────────────────────────────────────────────────────────
class UserBase(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_]+$",    # hanya huruf, angka, underscore
        examples=["john_doe"],
    )
    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=100)
    role: UserRole = UserRole.VIEWER


class UserCreate(UserBase):
    """Body untuk POST /users (register)"""
    password: str = Field(
        ..., min_length=8, max_length=128,
        description="Min 8 karakter, harus ada angka dan huruf besar",
    )

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Validasi kekuatan password minimal."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password harus mengandung minimal 1 huruf besar")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password harus mengandung minimal 1 angka")
        return v


class UserUpdate(BaseModel):
    """Body untuk PUT /users/{id} — semua field wajib diisi"""
    full_name: str = Field(..., max_length=100)
    role: UserRole
    is_active: bool


class UserPatch(BaseModel):
    """Body untuk PATCH /users/{id} — field opsional, hanya yang dikirim yang diupdate"""
    full_name: Optional[str] = Field(None, max_length=100)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    """Shape data user yang dikembalikan ke klien"""
    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Hitung jumlah post tanpa include seluruh list post
    post_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class UserLoginRequest(BaseModel):
    """Body untuk POST /auth/login"""
    username: str
    password: str


# ─────────────────────────────────────────────────────────────────────────────
# Post Schemas
# ─────────────────────────────────────────────────────────────────────────────
class PostBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    content: str = Field(..., min_length=10)
    summary: Optional[str] = Field(None, max_length=500)
    status: PostStatus = PostStatus.DRAFT


class PostCreate(PostBase):
    """Body untuk POST /posts"""
    # slug di-generate otomatis dari title di layer CRUD, tidak perlu dikirim klien
    pass


class PostUpdate(PostBase):
    """Body untuk PUT /posts/{id} — replace semua field"""
    pass


class PostPatch(BaseModel):
    """Body untuk PATCH /posts/{id}"""
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    content: Optional[str] = Field(None, min_length=10)
    summary: Optional[str] = Field(None, max_length=500)
    status: Optional[PostStatus] = None


class PostResponse(PostBase):
    id: uuid.UUID
    slug: str
    view_count: int
    author_id: uuid.UUID
    author: Optional["UserResponse"] = None   # nested response
    comment_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# Comment Schemas
# ─────────────────────────────────────────────────────────────────────────────
class CommentBase(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)


class CommentCreate(CommentBase):
    pass


class CommentPatch(BaseModel):
    body: Optional[str] = Field(None, min_length=1, max_length=2000)


class CommentResponse(CommentBase):
    id: uuid.UUID
    post_id: uuid.UUID
    author_id: uuid.UUID
    author: Optional[UserResponse] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# Error Response (standar format error)
# ─────────────────────────────────────────────────────────────────────────────
class ErrorResponse(BaseModel):
    """Format error konsisten untuk semua HTTPException"""
    detail: str
    code: Optional[str] = None       # error code mesin, contoh: "USER_NOT_FOUND"
    field: Optional[str] = None      # field mana yang error (untuk validation error)


# ─────────────────────────────────────────────────────────────────────────────
# Filter Params (digunakan sebagai Query parameters)
# ─────────────────────────────────────────────────────────────────────────────
class UserFilterParams(BaseModel):
    """Query params untuk GET /users"""
    search: Optional[str] = Field(None, description="Cari di username atau email")
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)

    model_config = ConfigDict(extra="ignore")


class PostFilterParams(BaseModel):
    """Query params untuk GET /posts"""
    search: Optional[str] = Field(None, description="Cari di title atau content")
    status: Optional[PostStatus] = None
    author_id: Optional[uuid.UUID] = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)

    model_config = ConfigDict(extra="ignore")
