"""Comprehensive API Endpoint Tests."""

import io
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from backend.app.db.memory import MemoryStore
from backend.app.db.store import set_store
from backend.app.main import app
from backend.app.services.gpu_manager import get_gpu_manager


def _create_test_image(size=(200, 200)) -> bytes:
    img = Image.new("RGB", size, color=(120, 80, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def setup_environment():
    store = MemoryStore(limit=2, window_hours=24)
    set_store(store)
    mgr = get_gpu_manager()
    mgr.mock_mode = True
    yield
    set_store(None)


@pytest.mark.asyncio
async def test_storefront_products_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Zero API credentials - directly supplies CDN url
        url = "https://cdn.shopify.com/s/files/1/0268/9715/4090/files/shirt.jpg"
        resp = await client.get(
            "/tryvtry-vton/products",
            params={
                "garment_url": url,
                "product_id": "prod_123",
                "variant_id": "var_456",
                "product_title": "Classic Oxford Shirt",
                "category": "tops",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_valid"] is True
        assert data["product_id"] == "prod_123"
        assert data["category"] == "tops"
        assert "tops" in data["supported_categories"]
        assert "bottoms" in data["supported_categories"]
        assert "one-pieces" in data["supported_categories"]


@pytest.mark.asyncio
async def test_try_on_vton_flow_and_quota_enforcement():
    transport = ASGITransport(app=app)
    person_bytes = _create_test_image((256, 384))
    garment_bytes = _create_test_image((200, 250))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try 1
        resp1 = await client.post(
            "/try-on-vton",
            files={"person_image": ("person.jpg", person_bytes, "image/jpeg"), "garment_image": ("garment.jpg", garment_bytes, "image/jpeg")},
            data={"email": "customer@shopify-store.com", "category": "tops", "product_title": "Denim Jacket"},
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["success"] is True
        assert "output_url" in data1
        assert data1["quota"]["used"] == 1
        assert data1["quota"]["remaining"] == 1

        # Try 2
        resp2 = await client.post(
            "/try-on-vton",
            files={"person_image": ("person.jpg", person_bytes, "image/jpeg"), "garment_image": ("garment.jpg", garment_bytes, "image/jpeg")},
            data={"email": "customer@shopify-store.com", "category": "tops"},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["quota"]["used"] == 2
        assert data2["quota"]["remaining"] == 0

        # Try 3 - Quota Exceeded
        resp3 = await client.post(
            "/try-on-vton",
            files={"person_image": ("person.jpg", person_bytes, "image/jpeg"), "garment_image": ("garment.jpg", garment_bytes, "image/jpeg")},
            data={"email": "customer@shopify-store.com", "category": "tops"},
        )
        assert resp3.status_code == 429
        data3 = resp3.json()
        assert data3["error"] == "quota_exceeded"


@pytest.mark.asyncio
async def test_unsupported_category_rejection():
    transport = ASGITransport(app=app)
    person_bytes = _create_test_image((200, 200))
    garment_bytes = _create_test_image((200, 200))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Sunglasses are NOT supported by FASHN VTON 1.5
        resp = await client.post(
            "/try-on-vton",
            files={"person_image": ("person.jpg", person_bytes, "image/jpeg"), "garment_image": ("garment.jpg", garment_bytes, "image/jpeg")},
            data={"email": "shopper@store.com", "category": "sunglasses"},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert "unsupported by FASHN VTON 1.5" in data["message"]
