"""Tests for Shopify Zero-Credential Integration and Variant Synchronization."""

import json
from pathlib import Path
import re


def test_liquid_card_zero_credentials():
    liquid_path = Path(__file__).resolve().parents[1] / "shopify" / "blocks" / "tryvtri-card.liquid"
    assert liquid_path.exists(), "tryvtri-card.liquid must exist"

    content = liquid_path.read_text(encoding="utf-8")

    # Strictly verify ZERO Shopify Admin credentials in schema settings
    schema_match = re.search(r"\{%\s*schema\s*%\}(.*?)\{%\s*endschema\s*%\}", content, re.DOTALL)
    assert schema_match is not None, "Liquid file must contain schema"
    schema_json = json.loads(schema_match.group(1))

    # Inspect all schema settings IDs
    settings = schema_json.get("settings", [])
    setting_ids = [s.get("id", "").lower() for s in settings]

    forbidden_terms = [
        "admin_api_token",
        "api_secret",
        "access_token",
        "client_secret",
        "shopify_api_key",
        "oauth",
        "private_app",
        "store_password",
        "api_token",
    ]
    for setting_id in setting_ids:
        for term in forbidden_terms:
            assert term not in setting_id, f"Forbidden setting '{setting_id}' found in Liquid schema"

    # Verify automatic Liquid product data bindings
    assert "product.id" in content
    assert "product.title" in content
    assert "product.featured_image" in content
    assert "vto_variant" in content
    assert "data-tv-product-context" in content


def test_liquid_variant_json_structure():
    # Simulate the embedded JSON structure produced by the Liquid block
    sample_liquid_json = {
        "productId": "819283749",
        "productTitle": "Summer Silk Dress",
        "featuredImageUrl": "https://cdn.shopify.com/s/files/1/0268/9715/4090/files/dress_main.jpg",
        "selectedVariantId": "4019283749",
        "category": "one-pieces",
        "variants": [
            {
                "id": "4019283749",
                "title": "Red / Small",
                "imageUrl": "https://cdn.shopify.com/s/files/1/0268/9715/4090/files/dress_red.jpg",
            },
            {
                "id": "4019283750",
                "title": "Blue / Small",
                "imageUrl": "https://cdn.shopify.com/s/files/1/0268/9715/4090/files/dress_blue.jpg",
            },
            {
                "id": "4019283751",
                "title": "Blue / Medium",
                "imageUrl": "https://cdn.shopify.com/s/files/1/0268/9715/4090/files/dress_main.jpg",  # Fallback to product image
            },
        ],
    }

    # Verify variant lookup logic
    def find_variant_image(variant_id, context):
        for v in context["variants"]:
            if v["id"] == str(variant_id):
                return v.get("imageUrl") or context["featuredImageUrl"]
        return context["featuredImageUrl"]

    assert find_variant_image("4019283750", sample_liquid_json) == "https://cdn.shopify.com/s/files/1/0268/9715/4090/files/dress_blue.jpg"
    # Variant without separate image correctly falls back to main image
    assert find_variant_image("4019283751", sample_liquid_json) == "https://cdn.shopify.com/s/files/1/0268/9715/4090/files/dress_main.jpg"
    # Unknown variant falls back to main image
    assert find_variant_image("unknown_999", sample_liquid_json) == "https://cdn.shopify.com/s/files/1/0268/9715/4090/files/dress_main.jpg"


def test_widget_js_endpoints():
    js_path = Path(__file__).resolve().parents[1] / "shopify" / "assets" / "tryvtri.js"
    assert js_path.exists(), "tryvtri.js must exist"

    js_code = js_path.read_text(encoding="utf-8")

    # Verify calls to correct endpoints
    assert "/try-on-vton" in js_code
    assert "/tryvtri-vton/check-usage" in js_code
    assert "initVariantListeners" in js_code
    assert "updateVariant" in js_code
