"""Tests for Admin Authentication and Security."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core.security import hash_password, verify_password, create_admin_token
from backend.app.db.memory import MemoryStore
from backend.app.db.store import set_store
from backend.app.main import app


@pytest.fixture(autouse=True)
def setup_store():
    store = MemoryStore()
    set_store(store)
    yield
    set_store(None)


def test_password_hashing():
    pw = "super_secure_admin_pass_123"
    hashed = hash_password(pw)
    assert hashed.startswith("pbkdf2$310000$")
    assert verify_password(pw, hashed) is True
    assert verify_password("wrong_pass", hashed) is False


@pytest.mark.asyncio
async def test_admin_login_success_and_token_generation():
    store = MemoryStore()
    hashed = hash_password("secretpass123")
    await store.create_admin("admin_user", hashed, role="owner")
    set_store(store)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid pass
        bad_res = await client.post("/admin/login", json={"username": "admin_user", "password": "wrong"})
        assert bad_res.status_code == 401

        # Valid pass
        ok_res = await client.post("/admin/login", json={"username": "admin_user", "password": "secretpass123"})
        assert ok_res.status_code == 200
        data = ok_res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["username"] == "admin_user"


@pytest.mark.asyncio
async def test_protected_routes_require_authorization():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Missing header
        res1 = await client.get("/admin/dashboard")
        assert res1.status_code == 401

        # Invalid token
        res2 = await client.get("/admin/dashboard", headers={"Authorization": "Bearer invalid.token.value"})
        assert res2.status_code == 401

        # Valid token
        token = create_admin_token("test_admin", role="admin")
        res3 = await client.get("/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
        assert res3.status_code == 200
        assert "metrics" in res3.json()
