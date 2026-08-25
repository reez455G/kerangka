# =============================================================================
# crud.py — Database Operations (Create, Read, Update, Delete)
#
# Layer ini berisi semua query database. Handler (routers) hanya memanggil
# fungsi di sini — tidak boleh ada logika query di handler.
#
# Prinsip:
#   - Semua fungsi menerima AsyncSession
#   - Return ORM object atau None (bukan raise exception — itu tugas handler)
#   - Filter/pagination diterapkan di level SQL (bukan Python) untuk efisiensi
#   - Slug di-generate otomatis dan dijamin unik
# =============================================================================

import uuid
import math
import re
import logging
from typing import Optional, Tuple, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, update as sql_update, delete as sql_delete
from sqlalchemy.orm import selectinload

from models import User, Post, Comment, PostStatus, UserRole
from schemas import (
    UserCreate, UserUpdate, UserPatch,
    PostCreate, PostUpdate, PostPatch,
    CommentCreate, CommentPatch,
    PaginatedResponse, UserResponse, PostResponse, CommentResponse,
)
from auth import hash_password

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _slugify(text: str) -> str:
    """Konversi teks ke slug: 'Hello World!' → 'hello-world'."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)     # hapus karakter non-word
    text = re.sub(r"[\s_]+", "-", text)       # ganti spasi/underscore dengan -
    text = re.sub(r"-+", "-", text)           # hapus duplikat -
    return text


async def _unique_slug(db: AsyncSession, base_slug: str) -> str:
    """Pastikan slug unik dengan menambahkan suffix jika perlu."""
    slug = base_slug
    counter = 1
    while True:
        existing = await db.scalar(
            select(Post.id).where(Post.slug == slug)
        )
        if existing is None:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


def _paginate(total: int, page: int, page_size: int) -> dict:
    """Hitung metadata pagination."""
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, math.ceil(total / page_size)),
    }


# =============================================================================
# USER CRUD
# =============================================================================

async def create_user(db: AsyncSession, data: UserCreate) -> User:
    """
    Buat user baru.
    Password di-hash sebelum disimpan — plain password tidak pernah menyentuh DB.
    """
    user = User(
        username=data.username,
        email=data.email,
        full_name=data.full_name,
        role=data.role,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    await db.flush()        # flush agar id ter-generate tanpa commit dulu
    await db.refresh(user)
    logger.info("User dibuat: %s (id=%s)", user.username, user.id)
    return user


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    """Ambil user by primary key. Return None jika tidak ada atau sudah dihapus."""
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_deleted == False)
    )
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """Digunakan saat login untuk lookup berdasarkan username."""
    result = await db.execute(
        select(User).where(User.username == username, User.is_deleted == False)
    )
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Cek duplikat email saat registrasi."""
    result = await db.execute(
        select(User).where(User.email == email, User.is_deleted == False)
    )
    return result.scalar_one_or_none()


async def list_users(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    role: Optional[UserRole] = None,
    is_active: Optional[bool] = None,
) -> PaginatedResponse[UserResponse]:
    """
    Daftar user dengan pagination + filtering.

    Query dibangun secara kondisional:
    - `search` mencari di username DAN email (OR)
    - `role` dan `is_active` sebagai filter exact match
    """
    base_query = select(User).where(User.is_deleted == False)

    if search:
        pattern = f"%{search}%"
        base_query = base_query.where(
            or_(
                User.username.ilike(pattern),
                User.email.ilike(pattern),
            )
        )
    if role is not None:
        base_query = base_query.where(User.role == role)
    if is_active is not None:
        base_query = base_query.where(User.is_active == is_active)

    # Hitung total SEBELUM limit/offset
    count_query = select(func.count()).select_from(base_query.subquery())
    total = await db.scalar(count_query) or 0

    # Ambil data dengan pagination
    paginated = base_query.order_by(User.created_at.desc())
    paginated = paginated.limit(page_size).offset((page - 1) * page_size)
    result = await db.execute(paginated)
    users = result.scalars().all()

    # Hitung post_count per user dalam 1 query (subquery agregat)
    if users:
        user_ids = [u.id for u in users]
        count_result = await db.execute(
            select(Post.author_id, func.count(Post.id).label("cnt"))
            .where(Post.author_id.in_(user_ids), Post.is_deleted == False)
            .group_by(Post.author_id)
        )
        post_counts = {row.author_id: row.cnt for row in count_result}
    else:
        post_counts = {}

    items = []
    for u in users:
        ur = UserResponse.model_validate(u)
        ur.post_count = post_counts.get(u.id, 0)
        items.append(ur)

    return PaginatedResponse(
        items=items,
        **_paginate(total, page, page_size),
    )


async def update_user(
    db: AsyncSession, user: User, data: UserUpdate
) -> User:
    """PUT: ganti semua field yang bisa diupdate."""
    user.full_name = data.full_name
    user.role = data.role
    user.is_active = data.is_active
    await db.flush()
    await db.refresh(user)
    return user


async def patch_user(
    db: AsyncSession, user: User, data: UserPatch
) -> User:
    """
    PATCH: hanya update field yang dikirim (tidak None).
    model_dump(exclude_unset=True) mengembalikan dict hanya field yang
    secara eksplisit dikirim klien — berbeda dengan field yang di-set ke None.
    """
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    await db.flush()
    await db.refresh(user)
    return user


async def soft_delete_user(db: AsyncSession, user: User) -> None:
    """
    Soft delete: set is_deleted=True, bukan DELETE FROM.
    Data tetap ada di DB untuk audit trail.
    """
    user.is_deleted = True
    user.is_active = False
    await db.flush()
    logger.info("User soft-deleted: id=%s", user.id)


# =============================================================================
# POST CRUD
# =============================================================================

async def create_post(
    db: AsyncSession, data: PostCreate, author_id: uuid.UUID
) -> Post:
    """Buat post baru. Slug di-generate otomatis dari title."""
    base_slug = _slugify(data.title)
    slug = await _unique_slug(db, base_slug)

    post = Post(
        title=data.title,
        slug=slug,
        content=data.content,
        summary=data.summary,
        status=data.status,
        author_id=author_id,
    )
    db.add(post)
    await db.flush()
    await db.refresh(post)
    logger.info("Post dibuat: %r (id=%s)", post.slug, post.id)
    return post


async def get_post_by_id(db: AsyncSession, post_id: uuid.UUID) -> Optional[Post]:
    result = await db.execute(
        select(Post)
        .options(selectinload(Post.author))   # eager load author
        .where(Post.id == post_id, Post.is_deleted == False)
    )
    return result.scalar_one_or_none()


async def get_post_by_slug(db: AsyncSession, slug: str) -> Optional[Post]:
    result = await db.execute(
        select(Post)
        .options(selectinload(Post.author))
        .where(Post.slug == slug, Post.is_deleted == False)
    )
    return result.scalar_one_or_none()


async def increment_view_count(db: AsyncSession, post_id: uuid.UUID) -> None:
    """Tambah view_count +1 menggunakan SQL UPDATE (atomic, aman dari race condition)."""
    await db.execute(
        sql_update(Post)
        .where(Post.id == post_id)
        .values(view_count=Post.view_count + 1)
    )


async def list_posts(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    status: Optional[PostStatus] = None,
    author_id: Optional[uuid.UUID] = None,
) -> PaginatedResponse[PostResponse]:
    """Daftar post dengan pagination, search full-text sederhana, dan filter."""
    base_query = (
        select(Post)
        .options(selectinload(Post.author))
        .where(Post.is_deleted == False)
    )

    if search:
        pattern = f"%{search}%"
        base_query = base_query.where(
            or_(Post.title.ilike(pattern), Post.content.ilike(pattern))
        )
    if status:
        base_query = base_query.where(Post.status == status)
    if author_id:
        base_query = base_query.where(Post.author_id == author_id)

    total = await db.scalar(
        select(func.count()).select_from(base_query.subquery())
    ) or 0

    result = await db.execute(
        base_query.order_by(Post.created_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    posts = result.scalars().all()

    # Hitung comment_count secara batch
    if posts:
        post_ids = [p.id for p in posts]
        cnt_result = await db.execute(
            select(Comment.post_id, func.count(Comment.id).label("cnt"))
            .where(Comment.post_id.in_(post_ids), Comment.is_deleted == False)
            .group_by(Comment.post_id)
        )
        comment_counts = {row.post_id: row.cnt for row in cnt_result}
    else:
        comment_counts = {}

    items = []
    for p in posts:
        pr = PostResponse.model_validate(p)
        pr.comment_count = comment_counts.get(p.id, 0)
        items.append(pr)

    return PaginatedResponse(items=items, **_paginate(total, page, page_size))


async def update_post(db: AsyncSession, post: Post, data: PostUpdate) -> Post:
    """PUT: ganti semua field post."""
    # Re-slug jika title berubah
    if post.title != data.title:
        base_slug = _slugify(data.title)
        post.slug = await _unique_slug(db, base_slug)
    post.title = data.title
    post.content = data.content
    post.summary = data.summary
    post.status = data.status
    await db.flush()
    await db.refresh(post)
    return post


async def patch_post(db: AsyncSession, post: Post, data: PostPatch) -> Post:
    """PATCH: update sebagian field post."""
    update_data = data.model_dump(exclude_unset=True)
    if "title" in update_data and update_data["title"] != post.title:
        update_data["slug"] = await _unique_slug(db, _slugify(update_data["title"]))
    for field, value in update_data.items():
        setattr(post, field, value)
    await db.flush()
    await db.refresh(post)
    return post


async def soft_delete_post(db: AsyncSession, post: Post) -> None:
    post.is_deleted = True
    await db.flush()


# =============================================================================
# COMMENT CRUD
# =============================================================================

async def create_comment(
    db: AsyncSession, data: CommentCreate,
    post_id: uuid.UUID, author_id: uuid.UUID,
) -> Comment:
    comment = Comment(body=data.body, post_id=post_id, author_id=author_id)
    db.add(comment)
    await db.flush()
    await db.refresh(comment)
    return comment


async def get_comment_by_id(
    db: AsyncSession, comment_id: uuid.UUID
) -> Optional[Comment]:
    result = await db.execute(
        select(Comment)
        .options(selectinload(Comment.author))
        .where(Comment.id == comment_id, Comment.is_deleted == False)
    )
    return result.scalar_one_or_none()


async def list_comments_for_post(
    db: AsyncSession, post_id: uuid.UUID, page: int = 1, page_size: int = 20
) -> PaginatedResponse[CommentResponse]:
    base_query = (
        select(Comment)
        .options(selectinload(Comment.author))
        .where(Comment.post_id == post_id, Comment.is_deleted == False)
    )
    total = await db.scalar(
        select(func.count()).select_from(base_query.subquery())
    ) or 0
    result = await db.execute(
        base_query.order_by(Comment.created_at.asc())
        .limit(page_size).offset((page - 1) * page_size)
    )
    items = [CommentResponse.model_validate(c) for c in result.scalars()]
    return PaginatedResponse(items=items, **_paginate(total, page, page_size))


async def patch_comment(
    db: AsyncSession, comment: Comment, data: CommentPatch
) -> Comment:
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(comment, field, value)
    await db.flush()
    await db.refresh(comment)
    return comment


async def soft_delete_comment(db: AsyncSession, comment: Comment) -> None:
    comment.is_deleted = True
    await db.flush()
