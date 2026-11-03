"""Tests for Image Validation and SSRF Protection."""

import io
import pytest
from PIL import Image

from backend.app.core.errors import ImageRejected
from backend.app.services.image_service import (
    is_ip_private_or_reserved,
    sanitize_image_bytes,
    validate_image_url,
    validate_person_upload,
)


def _make_dummy_image(format="JPEG", size=(256, 256), mode="RGB") -> bytes:
    img = Image.new(mode, size, color=(200, 100, 50))
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


def test_private_ip_detection():
    # Loopback
    assert is_ip_private_or_reserved("127.0.0.1") is True
    assert is_ip_private_or_reserved("127.0.0.2") is True
    assert is_ip_private_or_reserved("::1") is True

    # RFC 1918 Private
    assert is_ip_private_or_reserved("10.0.0.1") is True
    assert is_ip_private_or_reserved("172.16.0.5") is True
    assert is_ip_private_or_reserved("192.168.1.100") is True

    # Link-local / Cloud metadata (169.254.169.254)
    assert is_ip_private_or_reserved("169.254.169.254") is True

    # Public IP
    assert is_ip_private_or_reserved("8.8.8.8") is False
    assert is_ip_private_or_reserved("1.1.1.1") is False


def test_validate_image_url_blocks_private_targets():
    # Block localhost
    with pytest.raises(ImageRejected):
        validate_image_url("http://127.0.0.1/secret.jpg")

    # Block 169.254.169.254 cloud metadata
    with pytest.raises(ImageRejected):
        validate_image_url("http://169.254.169.254/latest/meta-data")

    # Block file protocol
    with pytest.raises(ImageRejected):
        validate_image_url("file:///etc/passwd")

    # Block invalid scheme
    with pytest.raises(ImageRejected):
        validate_image_url("ftp://cdn.shopify.com/image.jpg")


def test_validate_image_url_accepts_public_cdn():
    shopify_url = "https://cdn.shopify.com/s/files/1/0268/9715/4090/files/product.jpg"
    assert validate_image_url(shopify_url) == shopify_url

    protocol_relative = "//cdn.shopify.com/s/files/test.png"
    assert validate_image_url(protocol_relative) == "https://cdn.shopify.com/s/files/test.png"


def test_sanitize_image_bytes_valid_jpeg():
    valid_bytes = _make_dummy_image(format="JPEG", size=(300, 400))
    cleaned, fmt = sanitize_image_bytes(valid_bytes, label="garment")
    assert fmt == "JPEG"
    assert len(cleaned) > 0


def test_sanitize_image_bytes_converts_rgba_to_rgb():
    rgba_bytes = _make_dummy_image(format="PNG", size=(200, 200), mode="RGBA")
    cleaned, fmt = sanitize_image_bytes(rgba_bytes, label="garment")
    # Verify resulting image is RGB
    res_img = Image.open(io.BytesIO(cleaned))
    assert res_img.mode == "RGB"


def test_sanitize_image_rejects_corrupted_data():
    with pytest.raises(ImageRejected):
        sanitize_image_bytes(b"not-an-image-payload", label="test")


def test_sanitize_image_rejects_too_small_resolution():
    tiny = _make_dummy_image(format="JPEG", size=(32, 32))
    with pytest.raises(ImageRejected):
        sanitize_image_bytes(tiny, label="test")


def test_validate_person_upload_enforces_size_cap():
    valid_bytes = _make_dummy_image(format="JPEG", size=(200, 300))
    # Cap smaller than image
    with pytest.raises(ImageRejected):
        validate_person_upload(valid_bytes, max_bytes=100)

    # Cap larger than image
    res, fmt = validate_person_upload(valid_bytes, max_bytes=10_000_000)
    assert fmt == "JPEG"
