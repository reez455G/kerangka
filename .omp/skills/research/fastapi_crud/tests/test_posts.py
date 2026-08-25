# =============================================================================
# tests/test_posts.py — Tests untuk /posts dan nested /comments endpoints
# =============================================================================

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header

pytestmark = pytest.mark.anyio


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
POST_PAYLOAD = {
    "title": "Belajar FastAPI dari Nol",
    "content": "FastAPI adalah framework Python modern yang sangat cepat dan mudah dipelajari.",
    "summary": "Panduan belajar FastAPI",
    "status": "draft",
}

PUBLISHED_PAYLOAD = {**POST_PAYLOAD, "title": "FastAPI Production Tips", "status": "published"}


async def create_post(client: AsyncClient, token: str, payload: dict = None) -> dict:
    resp = await client.post(
        "/posts/",
        json=payload or POST_PAYLOAD,
        headers=auth_header(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def create_published_post(client: AsyncClient, token: str) -> dict:
    return await create_post(client, token, PUBLISHED_PAYLOAD)


# ─────────────────────────────────────────────────────────────────────────────
# Create Post Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestCreatePost:

    async def test_editor_can_create_post(self, client: AsyncClient, editor_token: str):
        resp = await client.post("/posts/", json=POST_PAYLOAD, headers=auth_header(editor_token))
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == POST_PAYLOAD["title"]
        assert data["slug"]                     # slug di-generate otomatis
        assert data["status"] == "draft"
        assert data["view_count"] == 0

    async def test_viewer_cannot_create_post(self, client: AsyncClient, viewer_token: str):
        resp = await client.post("/posts/", json=POST_PAYLOAD, headers=auth_header(viewer_token))
        assert resp.status_code == 403

    async def test_unauthenticated_cannot_create_post(self, client: AsyncClient):
        resp = await client.post("/posts/", json=POST_PAYLOAD)
        assert resp.status_code == 401

    async def test_slug_auto_generated_from_title(self, client: AsyncClient, editor_token: str):
        post = await create_post(client, editor_token)
        # Title: "Belajar FastAPI dari Nol" → slug: "belajar-fastapi-dari-nol"
        assert post["slug"] == "belajar-fastapi-dari-nol"

    async def test_duplicate_title_gets_unique_slug(self, client: AsyncClient, editor_token: str):
        post1 = await create_post(client, editor_token)
        post2 = await create_post(client, editor_token)   # title sama
        # Slug harus unik: satu dapat "-1" suffix
        assert post1["slug"] != post2["slug"]

    async def test_create_post_missing_title(self, client: AsyncClient, editor_token: str):
        resp = await client.post(
            "/posts/",
            json={"content": "Konten tanpa judul"},
            headers=auth_header(editor_token),
        )
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# List Posts Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestListPosts:

    async def test_list_posts_is_public(self, client: AsyncClient, editor_token: str):
        """List post tidak butuh autentikasi."""
        await create_post(client, editor_token)
        resp = await client.get("/posts/")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    async def test_list_posts_pagination(self, client: AsyncClient, editor_token: str):
        for i in range(5):
            await create_post(client, editor_token, {**POST_PAYLOAD, "title": f"Post {i}"})

        resp = await client.get("/posts/?page=1&page_size=3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 3
        assert data["page_size"] == 3

    async def test_list_posts_filter_by_status(self, client: AsyncClient, editor_token: str):
        await create_post(client, editor_token)                       # draft
        await create_published_post(client, editor_token)             # published

        resp = await client.get("/posts/?status=published")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(p["status"] == "published" for p in items)

    async def test_list_posts_search(self, client: AsyncClient, editor_token: str):
        await create_post(client, editor_token, {
            **POST_PAYLOAD, "title": "Tutorial Redis"
        })
        await create_post(client, editor_token, {
            **POST_PAYLOAD, "title": "Docker untuk Pemula"
        })

        resp = await client.get("/posts/?search=Redis")
        items = resp.json()["items"]
        assert any("Redis" in p["title"] for p in items)

    async def test_page_size_max_100(self, client: AsyncClient):
        resp = await client.get("/posts/?page_size=200")
        assert resp.status_code == 422   # melebihi max 100


# ─────────────────────────────────────────────────────────────────────────────
# Get Post Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestGetPost:

    async def test_get_post_by_id(self, client: AsyncClient, editor_token: str):
        post = await create_post(client, editor_token)
        resp = await client.get(f"/posts/{post['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == post["id"]

    async def test_get_post_increments_view_count(self, client: AsyncClient, editor_token: str):
        post = await create_post(client, editor_token)
        assert post["view_count"] == 0

        await client.get(f"/posts/{post['id']}")
        await client.get(f"/posts/{post['id']}")
        resp = await client.get(f"/posts/{post['id']}")
        # Setelah 3 akses, view_count harus >= 2 (masing-masing request increment)
        assert resp.json()["view_count"] >= 2

    async def test_get_post_by_slug(self, client: AsyncClient, editor_token: str):
        post = await create_post(client, editor_token)
        resp = await client.get(f"/posts/slug/{post['slug']}")
        assert resp.status_code == 200
        assert resp.json()["slug"] == post["slug"]

    async def test_get_nonexistent_post(self, client: AsyncClient):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = await client.get(f"/posts/{fake_id}")
        assert resp.status_code == 404

    async def test_get_by_invalid_slug(self, client: AsyncClient):
        resp = await client.get("/posts/slug/slug-tidak-ada")
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Update Post Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestUpdatePost:

    async def test_put_post_by_author(self, client: AsyncClient, editor_token: str):
        post = await create_post(client, editor_token)
        resp = await client.put(
            f"/posts/{post['id']}",
            json={
                "title": "Judul Baru",
                "content": "Konten yang sudah diperbarui dengan lengkap",
                "status": "published",
            },
            headers=auth_header(editor_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Judul Baru"
        assert data["status"] == "published"
        # Slug harus di-generate ulang dari judul baru
        assert data["slug"] == "judul-baru"

    async def test_put_post_by_non_author_forbidden(
        self, client: AsyncClient, editor_token: str, admin_token: str
    ):
        """Admin buat user lain, editor coba edit → 403."""
        post = await create_post(client, admin_token)   # admin yang buat
        resp = await client.put(
            f"/posts/{post['id']}",
            json={"title": "Hack", "content": "isi hack yang panjang", "status": "draft"},
            headers=auth_header(editor_token),  # editor lain coba edit
        )
        assert resp.status_code == 403

    async def test_patch_post_status_only(self, client: AsyncClient, editor_token: str):
        """PATCH hanya ubah status, field lain tidak berubah."""
        post = await create_post(client, editor_token)
        original_title = post["title"]

        resp = await client.patch(
            f"/posts/{post['id']}",
            json={"status": "published"},
            headers=auth_header(editor_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "published"
        assert data["title"] == original_title   # tidak berubah

    async def test_admin_can_edit_any_post(
        self, client: AsyncClient, editor_token: str, admin_token: str
    ):
        post = await create_post(client, editor_token)
        resp = await client.patch(
            f"/posts/{post['id']}",
            json={"status": "archived"},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"


# ─────────────────────────────────────────────────────────────────────────────
# Delete Post Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestDeletePost:

    async def test_delete_post_by_author(self, client: AsyncClient, editor_token: str):
        post = await create_post(client, editor_token)
        resp = await client.delete(
            f"/posts/{post['id']}",
            headers=auth_header(editor_token),
        )
        assert resp.status_code == 204

        # Post tidak bisa diakses lagi
        assert (await client.get(f"/posts/{post['id']}")).status_code == 404

    async def test_delete_post_by_non_author_forbidden(
        self, client: AsyncClient, editor_token: str, viewer_token: str
    ):
        post = await create_post(client, editor_token)
        resp = await client.delete(
            f"/posts/{post['id']}",
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 403

    async def test_delete_nonexistent_post(self, client: AsyncClient, admin_token: str):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = await client.delete(f"/posts/{fake_id}", headers=auth_header(admin_token))
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Comment Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestComments:

    async def _make_published_post(self, client, editor_token):
        return await create_published_post(client, editor_token)

    async def test_add_comment_to_published_post(
        self, client: AsyncClient, editor_token: str, viewer_token: str
    ):
        post = await self._make_published_post(client, editor_token)
        resp = await client.post(
            f"/posts/{post['id']}/comments",
            json={"body": "Artikel yang sangat bermanfaat!"},
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["body"] == "Artikel yang sangat bermanfaat!"
        assert data["post_id"] == post["id"]

    async def test_cannot_comment_on_draft(
        self, client: AsyncClient, editor_token: str, viewer_token: str
    ):
        """Hanya post PUBLISHED yang bisa di-comment."""
        draft = await create_post(client, editor_token)   # status: draft
        resp = await client.post(
            f"/posts/{draft['id']}/comments",
            json={"body": "Komentar di draft"},
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 422

    async def test_list_comments(
        self, client: AsyncClient, editor_token: str, viewer_token: str
    ):
        post = await self._make_published_post(client, editor_token)
        # Buat 3 komentar
        for i in range(3):
            await client.post(
                f"/posts/{post['id']}/comments",
                json={"body": f"Komentar {i}"},
                headers=auth_header(viewer_token),
            )

        resp = await client.get(f"/posts/{post['id']}/comments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    async def test_edit_own_comment(
        self, client: AsyncClient, editor_token: str, viewer_token: str
    ):
        post = await self._make_published_post(client, editor_token)
        comment_resp = await client.post(
            f"/posts/{post['id']}/comments",
            json={"body": "Komentar awal"},
            headers=auth_header(viewer_token),
        )
        comment_id = comment_resp.json()["id"]

        resp = await client.patch(
            f"/posts/{post['id']}/comments/{comment_id}",
            json={"body": "Komentar yang sudah diedit"},
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 200
        assert resp.json()["body"] == "Komentar yang sudah diedit"

    async def test_cannot_edit_others_comment(
        self, client: AsyncClient, editor_token: str, viewer_token: str, admin_token: str
    ):
        post = await self._make_published_post(client, editor_token)
        comment_resp = await client.post(
            f"/posts/{post['id']}/comments",
            json={"body": "Komentar viewer"},
            headers=auth_header(viewer_token),
        )
        comment_id = comment_resp.json()["id"]

        # Editor coba edit komentar viewer → 403
        resp = await client.patch(
            f"/posts/{post['id']}/comments/{comment_id}",
            json={"body": "Edit oleh orang lain"},
            headers=auth_header(editor_token),
        )
        assert resp.status_code == 403

    async def test_admin_can_delete_any_comment(
        self, client: AsyncClient, editor_token: str, viewer_token: str, admin_token: str
    ):
        post = await self._make_published_post(client, editor_token)
        comment_resp = await client.post(
            f"/posts/{post['id']}/comments",
            json={"body": "Komentar untuk dihapus"},
            headers=auth_header(viewer_token),
        )
        comment_id = comment_resp.json()["id"]

        resp = await client.delete(
            f"/posts/{post['id']}/comments/{comment_id}",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 204

    async def test_comment_pagination(
        self, client: AsyncClient, editor_token: str, viewer_token: str
    ):
        post = await self._make_published_post(client, editor_token)
        for i in range(5):
            await client.post(
                f"/posts/{post['id']}/comments",
                json={"body": f"Komentar panjang {i} dengan isi yang cukup"},
                headers=auth_header(viewer_token),
            )

        resp = await client.get(f"/posts/{post['id']}/comments?page=1&page_size=3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 3
        assert data["total"] == 5
        assert data["pages"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────────
class TestHealth:

    async def test_health_endpoint(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
