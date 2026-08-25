# =============================================================================
# routers/posts.py — Post & Comment Endpoints
#
# Post endpoints:
#   POST   /posts/                  Buat post baru
#   GET    /posts/                  Daftar post (pagination + filter)
#   GET    /posts/{id}              Detail post (+ increment view_count)
#   GET    /posts/slug/{slug}       Detail post by slug (SEO-friendly URL)
#   PUT    /posts/{id}              Ganti semua field post
#   PATCH  /posts/{id}              Update sebagian field post
#   DELETE /posts/{id}              Soft-delete post
#
# Comment endpoints (nested di bawah post):
#   POST   /posts/{id}/comments     Tambah komentar ke post
#   GET    /posts/{id}/comments     Daftar komentar (pagination)
#   PATCH  /posts/{id}/comments/{comment_id}  Edit komentar
#   DELETE /posts/{id}/comments/{comment_id}  Hapus komentar
# =============================================================================

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Query

import crud
from dependencies import DBSession, CurrentUser, EditorUser, Pagination
from models import PostStatus, UserRole
from schemas import (
    PostCreate, PostUpdate, PostPatch, PostResponse,
    CommentCreate, CommentPatch, CommentResponse,
    PaginatedResponse,
)

router = APIRouter(prefix="/posts", tags=["Posts"])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
async def _get_post_or_404(db, post_id: uuid.UUID):
    post = await crud.get_post_by_id(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail=f"Post '{post_id}' tidak ditemukan")
    return post


def _assert_post_owner_or_admin(post, current_user):
    """Penulis post atau Admin yang boleh edit/hapus."""
    if current_user.role != UserRole.ADMIN and post.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hanya penulis atau Admin yang boleh mengubah post ini",
        )


# ─────────────────────────────────────────────────────────────────────────────
# POST /posts — Buat post baru
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Buat post baru",
)
async def create_post(
    body: PostCreate,
    db: DBSession,
    current_user: EditorUser,      # minimal role EDITOR
):
    """
    Slug di-generate otomatis dari title (unik dijamin oleh crud.create_post).
    Status default: DRAFT — harus eksplisit di-set PUBLISHED.
    """
    post = await crud.create_post(db, body, author_id=current_user.id)
    return post


# ─────────────────────────────────────────────────────────────────────────────
# GET /posts — List dengan pagination & filter
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/",
    response_model=PaginatedResponse[PostResponse],
    summary="Daftar post (publik)",
)
async def list_posts(
    db: DBSession,
    pagination: Pagination,
    search: Optional[str] = Query(None, description="Cari di title atau content"),
    status_filter: Optional[PostStatus] = Query(None, alias="status"),
    author_id: Optional[uuid.UUID] = Query(None),
):
    """
    Endpoint PUBLIK — tidak perlu token.
    Non-admin hanya melihat post PUBLISHED secara default.
    Admin bisa melihat semua status melalui query param ?status=draft.
    """
    return await crud.list_posts(
        db,
        page=pagination.page,
        page_size=pagination.page_size,
        search=search,
        status=status_filter,
        author_id=author_id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /posts/slug/{slug} — harus SEBELUM /{post_id}
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/slug/{slug}",
    response_model=PostResponse,
    summary="Detail post by slug (SEO URL)",
)
async def get_post_by_slug(slug: str, db: DBSession):
    """
    Slug lebih SEO-friendly daripada UUID.
    Contoh: GET /posts/slug/cara-belajar-python-efektif

    Router ini harus didaftarkan SEBELUM /{post_id} agar FastAPI
    tidak mengira 'slug/...' adalah UUID.
    """
    post = await crud.get_post_by_slug(db, slug)
    if not post:
        raise HTTPException(status_code=404, detail=f"Post dengan slug '{slug}' tidak ditemukan")
    await crud.increment_view_count(db, post.id)
    return post


# ─────────────────────────────────────────────────────────────────────────────
# GET /posts/{post_id} — Detail post by ID
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/{post_id}",
    response_model=PostResponse,
    summary="Detail post by ID",
)
async def get_post(post_id: uuid.UUID, db: DBSession):
    post = await _get_post_or_404(db, post_id)
    # Increment view count secara atomic (UPDATE ... SET view_count = view_count + 1)
    await crud.increment_view_count(db, post.id)
    return post


# ─────────────────────────────────────────────────────────────────────────────
# PUT /posts/{post_id} — Replace semua field
# ─────────────────────────────────────────────────────────────────────────────
@router.put(
    "/{post_id}",
    response_model=PostResponse,
    summary="Ganti semua field post (penulis atau Admin)",
)
async def update_post(
    post_id: uuid.UUID,
    body: PostUpdate,
    db: DBSession,
    current_user: CurrentUser,
):
    post = await _get_post_or_404(db, post_id)
    _assert_post_owner_or_admin(post, current_user)
    return await crud.update_post(db, post, body)


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /posts/{post_id} — Update sebagian field
# ─────────────────────────────────────────────────────────────────────────────
@router.patch(
    "/{post_id}",
    response_model=PostResponse,
    summary="Update sebagian field post",
)
async def patch_post(
    post_id: uuid.UUID,
    body: PostPatch,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Contoh: hanya ubah status post dari DRAFT ke PUBLISHED:
      PATCH /posts/{id}
      {"status": "published"}
    """
    post = await _get_post_or_404(db, post_id)
    _assert_post_owner_or_admin(post, current_user)
    return await crud.patch_post(db, post, body)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /posts/{post_id} — Soft delete
# ─────────────────────────────────────────────────────────────────────────────
@router.delete(
    "/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus post (soft delete)",
)
async def delete_post(
    post_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    post = await _get_post_or_404(db, post_id)
    _assert_post_owner_or_admin(post, current_user)
    await crud.soft_delete_post(db, post)


# ─────────────────────────────────────────────────────────────────────────────
# ── COMMENT ENDPOINTS (nested) ───────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

async def _get_comment_or_404(db, comment_id: uuid.UUID):
    comment = await crud.get_comment_by_id(db, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail=f"Comment '{comment_id}' tidak ditemukan")
    return comment


# POST /posts/{post_id}/comments
@router.post(
    "/{post_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tambah komentar ke post",
)
async def create_comment(
    post_id: uuid.UUID,
    body: CommentCreate,
    db: DBSession,
    current_user: CurrentUser,   # semua user yang login bisa komentar
):
    post = await _get_post_or_404(db, post_id)
    # Hanya post PUBLISHED yang bisa di-comment
    if post.status != PostStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Komentar hanya bisa ditambahkan ke post yang sudah PUBLISHED",
        )
    return await crud.create_comment(db, body, post_id=post.id, author_id=current_user.id)


# GET /posts/{post_id}/comments
@router.get(
    "/{post_id}/comments",
    response_model=PaginatedResponse[CommentResponse],
    summary="Daftar komentar sebuah post",
)
async def list_comments(
    post_id: uuid.UUID,
    db: DBSession,
    pagination: Pagination,
):
    await _get_post_or_404(db, post_id)   # validasi post exist
    return await crud.list_comments_for_post(
        db, post_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )


# PATCH /posts/{post_id}/comments/{comment_id}
@router.patch(
    "/{post_id}/comments/{comment_id}",
    response_model=CommentResponse,
    summary="Edit komentar (penulis komentar atau Admin)",
)
async def patch_comment(
    post_id: uuid.UUID,
    comment_id: uuid.UUID,
    body: CommentPatch,
    db: DBSession,
    current_user: CurrentUser,
):
    await _get_post_or_404(db, post_id)
    comment = await _get_comment_or_404(db, comment_id)

    # Verifikasi comment milik post yang benar
    if comment.post_id != post_id:
        raise HTTPException(status_code=404, detail="Komentar tidak ditemukan di post ini")

    # Hanya penulis comment atau Admin
    if current_user.role != UserRole.ADMIN and comment.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hanya penulis komentar atau Admin yang boleh mengedit",
        )
    return await crud.patch_comment(db, comment, body)


# DELETE /posts/{post_id}/comments/{comment_id}
@router.delete(
    "/{post_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus komentar",
)
async def delete_comment(
    post_id: uuid.UUID,
    comment_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    await _get_post_or_404(db, post_id)
    comment = await _get_comment_or_404(db, comment_id)

    if comment.post_id != post_id:
        raise HTTPException(status_code=404, detail="Komentar tidak ditemukan di post ini")

    if current_user.role != UserRole.ADMIN and comment.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Tidak punya izin menghapus komentar ini")

    await crud.soft_delete_comment(db, comment)
