# =============================================================================
# tests/test_users.py — Tests untuk /users dan /auth endpoints
#
# Setiap test function mendapat:
#   - `client`: AsyncClient yang terhubung ke test DB
#   - `admin_token` / `editor_token` / `viewer_token`: JWT token siap pakai
#
# Jalankan: pytest tests/test_users.py -v
# =============================================================================

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header

pytestmark = pytest.mark.anyio   # semua test di file ini adalah async


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────
USER_PAYLOAD = {
    "username": "johndoe",
    "email": "john@example.com",
    "password": "StrongPass1",
    "full_name": "John Doe",
}


async def create_user(client: AsyncClient, payload: dict = None) -> dict:
    """Helper: buat user dan return response JSON."""
    resp = await client.post("/users/", json=payload or USER_PAYLOAD)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Auth Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestAuth:

    async def test_login_success(self, client: AsyncClient):
        await create_user(client)
        resp = await client.post("/auth/login", json={
            "username": "johndoe", "password": "StrongPass1"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    async def test_login_wrong_password(self, client: AsyncClient):
        await create_user(client)
        resp = await client.post("/auth/login", json={
            "username": "johndoe", "password": "WrongPass9"
        })
        assert resp.status_code == 401
        assert "salah" in resp.json()["detail"].lower()

    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Username tidak ada → 401, bukan 404 (mencegah enumeration)."""
        resp = await client.post("/auth/login", json={
            "username": "nobody", "password": "AnyPass1"
        })
        assert resp.status_code == 401

    async def test_refresh_token(self, client: AsyncClient):
        await create_user(client)
        login = await client.post("/auth/login", json={
            "username": "johndoe", "password": "StrongPass1"
        })
        refresh_token = login.json()["refresh_token"]

        resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        # Token baru harus berbeda (rotation)
        assert data["access_token"] != login.json()["access_token"]

    async def test_refresh_with_invalid_token(self, client: AsyncClient):
        resp = await client.post("/auth/refresh", json={"refresh_token": "not.a.token"})
        assert resp.status_code == 401

    async def test_refresh_with_access_token_fails(self, client: AsyncClient):
        """Access token tidak bisa dipakai sebagai refresh token."""
        await create_user(client)
        login = await client.post("/auth/login", json={
            "username": "johndoe", "password": "StrongPass1"
        })
        access_token = login.json()["access_token"]

        resp = await client.post("/auth/refresh", json={"refresh_token": access_token})
        assert resp.status_code == 401

    async def test_get_me(self, client: AsyncClient):
        await create_user(client)
        login = await client.post("/auth/login", json={
            "username": "johndoe", "password": "StrongPass1"
        })
        token = login.json()["access_token"]

        resp = await client.get("/auth/me", headers=auth_header(token))
        assert resp.status_code == 200
        assert resp.json()["username"] == "johndoe"

    async def test_logout(self, client: AsyncClient, viewer_token: str):
        resp = await client.post("/auth/logout", headers=auth_header(viewer_token))
        assert resp.status_code == 204


# ─────────────────────────────────────────────────────────────────────────────
# Registration Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestUserRegistration:

    async def test_register_success(self, client: AsyncClient):
        resp = await client.post("/users/", json=USER_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "johndoe"
        assert data["email"] == "john@example.com"
        assert "hashed_password" not in data   # TIDAK pernah bocor ke response
        assert "id" in data
        assert "created_at" in data

    async def test_register_duplicate_username(self, client: AsyncClient):
        await create_user(client)
        resp = await client.post("/users/", json={**USER_PAYLOAD, "email": "other@x.com"})
        assert resp.status_code == 409
        assert "johndoe" in resp.json()["detail"]

    async def test_register_duplicate_email(self, client: AsyncClient):
        await create_user(client)
        resp = await client.post("/users/", json={**USER_PAYLOAD, "username": "other"})
        assert resp.status_code == 409

    async def test_register_weak_password_no_uppercase(self, client: AsyncClient):
        resp = await client.post("/users/", json={**USER_PAYLOAD, "password": "weakpass1"})
        assert resp.status_code == 422   # validation error

    async def test_register_weak_password_no_digit(self, client: AsyncClient):
        resp = await client.post("/users/", json={**USER_PAYLOAD, "password": "WeakPassWord"})
        assert resp.status_code == 422

    async def test_register_invalid_email(self, client: AsyncClient):
        resp = await client.post("/users/", json={**USER_PAYLOAD, "email": "notanemail"})
        assert resp.status_code == 422

    async def test_register_username_with_special_chars(self, client: AsyncClient):
        resp = await client.post("/users/", json={**USER_PAYLOAD, "username": "john-doe!"})
        assert resp.status_code == 422   # hanya huruf, angka, underscore


# ─────────────────────────────────────────────────────────────────────────────
# List Users Tests (Admin only)
# ─────────────────────────────────────────────────────────────────────────────
class TestListUsers:

    async def test_list_users_requires_admin(self, client: AsyncClient, viewer_token: str):
        resp = await client.get("/users/", headers=auth_header(viewer_token))
        assert resp.status_code == 403

    async def test_list_users_as_admin(self, client: AsyncClient, admin_token: str):
        resp = await client.get("/users/", headers=auth_header(admin_token))
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data

    async def test_list_users_pagination(self, client: AsyncClient, admin_token: str):
        # Buat beberapa user tambahan
        for i in range(3):
            await client.post("/users/", json={
                "username": f"user{i}", "email": f"user{i}@x.com",
                "password": "TestPass1",
            })
        resp = await client.get(
            "/users/?page=1&page_size=2",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    async def test_list_users_search(self, client: AsyncClient, admin_token: str):
        await create_user(client)
        resp = await client.get(
            "/users/?search=johndoe",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        assert any(u["username"] == "johndoe" for u in resp.json()["items"])

    async def test_list_without_token_unauthorized(self, client: AsyncClient):
        resp = await client.get("/users/")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Get User Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestGetUser:

    async def test_get_user_by_id(self, client: AsyncClient, viewer_token: str):
        user = await create_user(client)
        resp = await client.get(f"/users/{user['id']}", headers=auth_header(viewer_token))
        assert resp.status_code == 200
        assert resp.json()["id"] == user["id"]

    async def test_get_user_not_found(self, client: AsyncClient, viewer_token: str):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = await client.get(f"/users/{fake_id}", headers=auth_header(viewer_token))
        assert resp.status_code == 404

    async def test_get_my_profile(self, client: AsyncClient, viewer_token: str):
        resp = await client.get("/users/me", headers=auth_header(viewer_token))
        assert resp.status_code == 200
        assert resp.json()["username"] == "testviewer"


# ─────────────────────────────────────────────────────────────────────────────
# Update User Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestUpdateUser:

    async def test_put_user_as_admin(self, client: AsyncClient, admin_token: str):
        user = await create_user(client)
        resp = await client.put(
            f"/users/{user['id']}",
            json={"full_name": "John Updated", "role": "editor", "is_active": True},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "John Updated"
        assert resp.json()["role"] == "editor"

    async def test_put_user_as_non_admin_forbidden(
        self, client: AsyncClient, admin_token: str, viewer_token: str
    ):
        user = await create_user(client)
        resp = await client.put(
            f"/users/{user['id']}",
            json={"full_name": "Hacker", "role": "admin", "is_active": True},
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 403

    async def test_patch_own_profile(self, client: AsyncClient, viewer_token: str):
        """User bisa PATCH profil sendiri (tapi tidak bisa ubah role)."""
        me = await client.get("/users/me", headers=auth_header(viewer_token))
        user_id = me.json()["id"]

        resp = await client.patch(
            f"/users/{user_id}",
            json={"full_name": "Updated Name"},
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Updated Name"

    async def test_patch_cannot_change_own_role(self, client: AsyncClient, viewer_token: str):
        me = await client.get("/users/me", headers=auth_header(viewer_token))
        user_id = me.json()["id"]

        resp = await client.patch(
            f"/users/{user_id}",
            json={"role": "admin"},   # viewer coba jadi admin
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 403

    async def test_patch_other_user_forbidden(
        self, client: AsyncClient, viewer_token: str
    ):
        other = await create_user(client)
        resp = await client.patch(
            f"/users/{other['id']}",
            json={"full_name": "Hacked"},
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Delete User Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestDeleteUser:

    async def test_delete_user_as_admin(self, client: AsyncClient, admin_token: str):
        user = await create_user(client)
        resp = await client.delete(
            f"/users/{user['id']}",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 204

        # User sudah tidak bisa ditemukan
        resp2 = await client.get(
            f"/users/{user['id']}",
            headers=auth_header(admin_token),
        )
        assert resp2.status_code == 404

    async def test_admin_cannot_delete_self(self, client: AsyncClient, admin_token: str):
        me = await client.get("/users/me", headers=auth_header(admin_token))
        admin_id = me.json()["id"]
        resp = await client.delete(
            f"/users/{admin_id}",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 400   # tidak boleh hapus diri sendiri

    async def test_delete_as_non_admin_forbidden(
        self, client: AsyncClient, viewer_token: str
    ):
        user = await create_user(client)
        resp = await client.delete(
            f"/users/{user['id']}",
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 403
