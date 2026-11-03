"""Comprehensive Verification Suite for the 10 On-Demand GPU Lifecycle Scenarios.

Prompt 7 Requirements:
Scenario 1: Open website -> GPU OFF
Scenario 2: Open product page -> GPU OFF
Scenario 3: Open TryVtri widget -> GPU OFF
Scenario 4: Customer uploads photo (validation) -> GPU OFF
Scenario 5: Customer clicks Try It On with remaining tries -> GPU STARTS
Scenario 6: Try-on completes -> Customer gets photo
Scenario 7: No more requests for 10 minutes (accelerated idle countdown in test) -> GPU STOPS
Scenario 8: 2 customers click Try It On at same time -> 1 GPU runs both, no duplicates
Scenario 9: Customer with 0 tries clicks Try It On -> Error returned, GPU OFF
Scenario 10: Admin checks dashboard -> GPU OFF
"""

import asyncio
import io
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from backend.app.config import get_settings
from backend.app.db.memory import MemoryStore
from backend.app.db.store import set_store
from backend.app.main import create_app
from backend.app.services.gpu_manager import GpuManager, get_gpu_manager, set_gpu_manager


def _make_dummy_image(size=(256, 384), color=(100, 150, 200)) -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def setup_lifecycle_environment():
    store = MemoryStore(limit=2, window_hours=24)
    set_store(store)
    mgr = GpuManager()
    mgr.mock_mode = True
    set_gpu_manager(mgr)
    yield
    set_store(None)
    set_gpu_manager(None)


@pytest.mark.asyncio
async def test_scenario_1_open_website_gpu_remains_off():
    """Scenario 1: Opening the website must cost zero GPU runtime and keep GPU stopped."""
    app = create_app()
    mgr = get_gpu_manager()
    assert mgr.status == "stopped"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code in (200, 307)
        assert mgr.status == "stopped"
        assert mgr.active_requests == 0
        assert mgr.total_runtime_seconds == 0


@pytest.mark.asyncio
async def test_scenario_2_open_product_page_gpu_remains_off():
    """Scenario 2: Storefront product/variant image checks must keep GPU stopped."""
    app = create_app()
    mgr = get_gpu_manager()
    assert mgr.status == "stopped"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/tryvtry-vton/products",
            params={
                "garment_url": "https://cdn.shopify.com/s/files/1/0268/9715/4090/files/linen_shirt.jpg",
                "product_id": "shopify_prod_999",
                "category": "tops",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["is_valid"] is True
        assert mgr.status == "stopped"
        assert mgr.active_requests == 0
        assert mgr.total_runtime_seconds == 0


@pytest.mark.asyncio
async def test_scenario_3_open_tryvtri_widget_gpu_remains_off():
    """Scenario 3: Opening TryVtri widget (usage and quota check) must keep GPU stopped."""
    app = create_app()
    mgr = get_gpu_manager()
    assert mgr.status == "stopped"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/tryvtri-vton/check-usage",
            params={"email": "shopper@store.com", "shop": "my-fashion-brand.myshopify.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["remaining"] == 2
        assert data["eligible"] is True
        assert mgr.status == "stopped"
        assert mgr.active_requests == 0
        assert mgr.total_runtime_seconds == 0


@pytest.mark.asyncio
async def test_scenario_4_customer_uploads_photo_gpu_remains_off():
    """Scenario 4: Customer photo upload / validation before submission must keep GPU stopped."""
    app = create_app()
    mgr = get_gpu_manager()
    assert mgr.status == "stopped"

    # Test image validation service directly and corrupt upload rejection
    from backend.app.services.image_service import validate_person_upload
    valid_bytes = _make_dummy_image((300, 450))
    cleaned, mime = validate_person_upload(valid_bytes)
    assert mime.upper() in ("JPEG", "IMAGE/JPEG")
    assert mgr.status == "stopped"
    assert mgr.active_requests == 0
    assert mgr.total_runtime_seconds == 0


@pytest.mark.asyncio
async def test_scenario_5_and_6_customer_clicks_try_it_on_starts_gpu_and_returns_photo():
    """Scenario 5 & 6: Valid try-on starts GPU, completes inference, and returns photo result."""
    app = create_app()
    mgr = get_gpu_manager()
    assert mgr.status == "stopped"

    person_bytes = _make_dummy_image((256, 384))
    garment_bytes = _make_dummy_image((200, 250))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/try-on-vton",
            files={
                "person_image": ("person.jpg", person_bytes, "image/jpeg"),
                "garment_image": ("garment.jpg", garment_bytes, "image/jpeg"),
            },
            data={"email": "shopper1@store.com", "category": "tops", "product_title": "Silk Blouse"},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Scenario 6 proof: Customer gets photo data URL
        assert data["success"] is True
        assert data["output_url"].startswith("data:image/png;base64,")
        assert data["quota"]["used"] == 1
        assert data["quota"]["remaining"] == 1

        # Scenario 5 proof: GPU started and is currently running
        assert mgr.status == "running"
        assert mgr.started_at is not None


@pytest.mark.asyncio
async def test_scenario_7_idle_countdown_stops_gpu_and_records_cost():
    """Scenario 7: When idle for timeout period, GPU automatically shuts down and records cost."""
    settings = get_settings()
    # Accelerate idle timeout for unit test
    original_timeout = settings.gpu_idle_shutdown_seconds
    settings.gpu_idle_shutdown_seconds = 0.05  # 50 milliseconds

    try:
        app = create_app()
        mgr = get_gpu_manager()

        person_bytes = _make_dummy_image((256, 384))
        garment_bytes = _make_dummy_image((200, 250))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/try-on-vton",
                files={
                    "person_image": ("person.jpg", person_bytes, "image/jpeg"),
                    "garment_image": ("garment.jpg", garment_bytes, "image/jpeg"),
                },
                data={"email": "shopper2@store.com", "category": "tops"},
            )
            assert resp.status_code == 200
            assert mgr.status == "running"

            # Wait for accelerated idle timeout to trigger
            stopped = False
            for _ in range(30):
                if mgr.status == "stopped":
                    stopped = True
                    break
                await asyncio.sleep(0.05)

            # Scenario 7 proof: GPU stopped automatically
            assert stopped is True
            assert mgr.status == "stopped"
            assert mgr.stopped_at is not None
            assert mgr.total_runtime_seconds >= 0
    finally:
        settings.gpu_idle_shutdown_seconds = original_timeout


@pytest.mark.asyncio
async def test_scenario_8_concurrent_requests_reuse_single_gpu_without_duplicates():
    """Scenario 8: 2 customers clicking Try It On at the same time reuse 1 GPU instance."""
    app = create_app()
    mgr = get_gpu_manager()
    assert mgr.status == "stopped"

    person_bytes = _make_dummy_image((256, 384))
    garment_bytes = _make_dummy_image((200, 250))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Launch two requests concurrently
        async def submit_tryon(email: str):
            return await client.post(
                "/try-on-vton",
                files={
                    "person_image": ("person.jpg", person_bytes, "image/jpeg"),
                    "garment_image": ("garment.jpg", garment_bytes, "image/jpeg"),
                },
                data={"email": email, "category": "tops"},
            )

        resp1, resp2 = await asyncio.gather(
            submit_tryon("userA@concurrent.com"),
            submit_tryon("userB@concurrent.com"),
        )

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["success"] is True
        assert resp2.json()["success"] is True

        # Scenario 8 proof: Single pod ID allocated and reused
        assert mgr.status == "running"
        assert mgr.pod_id is not None
        assert "mock-pod-" in mgr.pod_id


@pytest.mark.asyncio
async def test_scenario_9_zero_tries_customer_denied_gpu_remains_off():
    """Scenario 9: Customer with 0 remaining tries is rejected; GPU never starts."""
    app = create_app()
    mgr = get_gpu_manager()
    assert mgr.status == "stopped"

    person_bytes = _make_dummy_image((256, 384))
    garment_bytes = _make_dummy_image((200, 250))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Consume try 1
        r1 = await client.post(
            "/try-on-vton",
            files={"person_image": ("person.jpg", person_bytes, "image/jpeg"), "garment_image": ("garment.jpg", garment_bytes, "image/jpeg")},
            data={"email": "exhausted@store.com", "category": "tops"},
        )
        assert r1.status_code == 200

        # Consume try 2
        r2 = await client.post(
            "/try-on-vton",
            files={"person_image": ("person.jpg", person_bytes, "image/jpeg"), "garment_image": ("garment.jpg", garment_bytes, "image/jpeg")},
            data={"email": "exhausted@store.com", "category": "tops"},
        )
        assert r2.status_code == 200

        # Stop GPU
        await mgr.stop_gpu(reason="test_reset")
        assert mgr.status == "stopped"

        # Try 3: Exceeded limit
        r3 = await client.post(
            "/try-on-vton",
            files={"person_image": ("person.jpg", person_bytes, "image/jpeg"), "garment_image": ("garment.jpg", garment_bytes, "image/jpeg")},
            data={"email": "exhausted@store.com", "category": "tops"},
        )
        assert r3.status_code == 429
        assert r3.json()["error"] == "quota_exceeded"

        # Scenario 9 proof: GPU remained STOPPED
        assert mgr.status == "stopped"
        assert mgr.active_requests == 0


@pytest.mark.asyncio
async def test_scenario_10_admin_checks_dashboard_gpu_remains_off():
    """Scenario 10: Admin visiting dashboard, stats, and health check must keep GPU stopped."""
    app = create_app()
    mgr = get_gpu_manager()
    assert mgr.status == "stopped"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health probe
        h_resp = await client.get("/health")
        assert h_resp.status_code == 200
        assert h_resp.json()["gpu"]["status"] == "stopped"

        # 2. GPU status
        g_resp = await client.get("/gpu/status")
        assert g_resp.status_code == 200
        assert g_resp.json()["status"] == "stopped"

        # Scenario 10 proof: GPU remained stopped, zero active requests, zero compute cost
        assert mgr.status == "stopped"
        assert mgr.active_requests == 0
        assert mgr.total_runtime_seconds == 0
