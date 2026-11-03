"""Backend startup and health check tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.config import get_settings
from backend.app.db.memory import MemoryStore
from backend.app.db.store import set_store
from backend.app.main import app
from backend.app.services.gpu_manager import get_gpu_manager


@pytest.fixture(autouse=True)
def setup_memory_store():
    store = MemoryStore(limit=2, window_hours=24)
    set_store(store)
    mgr = get_gpu_manager()
    mgr.mock_mode = True
    yield
    set_store(None)


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert "gpu" in data
        assert data["gpu"]["status"] in ("stopped", "running", "starting")


@pytest.mark.asyncio
async def test_openapi_schema_loaded():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "/try-on-vton" in schema["paths"]
        assert "/tryvtry-vton/products" in schema["paths"]
        assert "/gpu/status" in schema["paths"]
        assert "/admin/login" in schema["paths"]
        assert "/admin/dashboard" in schema["paths"]
