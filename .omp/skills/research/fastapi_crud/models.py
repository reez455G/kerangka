# =============================================================================
# models.py — ORM Models: User ─< Post ─< Comment
#
# Relasi yang diimplementasikan:
#   User  1──* Post     (satu user bisa punya banyak post)
#   Post  1──* Comment  (satu post bisa punya banyak comment)
#   User  1──* Comment  (satu user bisa tulis banyak comment)
#
# Semua model pakai:
#   - UUID sebagai primary key (lebih aman dari auto-increment integer)
#   - created_at / updated_at otomatis
#   - soft-delete via is_deleted flag (data tidak benar-benar dihapus)
# =============================================================================

import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import (
    String, Text, Boolean, DateTime, ForeignKey,
    Index, func, Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from database import Base


# ─────────────────────────────────────────────────────────────────────────────
# Helper: UUID default menggunakan uuid4
# ─────────────────────────────────────────────────────────────────────────────
def uuid_pk() -> uuid.UUID:
    return uuid.uuid4()


# ─────────────────────────────────────────────────────────────────────────────
# Enum: Role user
# ─────────────────────────────────────────────────────────────────────────────
class UserRole(str, enum.Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


# ─────────────────────────────────────────────────────────────────────────────
# Model: User
# ─────────────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    # Primary key — UUID disimpan sebagai PostgreSQL native UUID type
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_pk
    )
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole), default=UserRole.VIEWER, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamps — server_default menghindari masalah timezone client
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relasi ────────────────────────────────────────────────────────────────
    # back_populates: dua sisi relasi harus cocok
    # cascade="all, delete-orphan": hapus post ketika user dihapus
    # lazy="selectin": otomatis load relasi dengan SELECT IN (bukan JOIN)
    posts: Mapped[List["Post"]] = relationship(
        "Post", back_populates="author",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    comments: Mapped[List["Comment"]] = relationship(
        "Comment", back_populates="author",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # ── Index komposit ────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_users_email_active", "email", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# Enum: Status Post
# ─────────────────────────────────────────────────────────────────────────────
class PostStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


# ─────────────────────────────────────────────────────────────────────────────
# Model: Post
# ─────────────────────────────────────────────────────────────────────────────
class Post(Base):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_pk
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(300), unique=True, nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[PostStatus] = mapped_column(
        SAEnum(PostStatus), default=PostStatus.DRAFT, nullable=False
    )
    view_count: Mapped[int] = mapped_column(default=0, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Foreign key ke User
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relasi ────────────────────────────────────────────────────────────────
    author: Mapped["User"] = relationship("User", back_populates="posts")
    comments: Mapped[List["Comment"]] = relationship(
        "Comment", back_populates="post",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_posts_author_status", "author_id", "status"),
        Index("ix_posts_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Post id={self.id} slug={self.slug!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# Model: Comment
# ─────────────────────────────────────────────────────────────────────────────
class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_pk
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relasi ────────────────────────────────────────────────────────────────
    post: Mapped["Post"] = relationship("Post", back_populates="comments")
    author: Mapped["User"] = relationship("User", back_populates="comments")

    def __repr__(self) -> str:
        return f"<Comment id={self.id} post_id={self.post_id}>"
