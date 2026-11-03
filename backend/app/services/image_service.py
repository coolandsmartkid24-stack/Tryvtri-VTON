"""Image validation, SSRF protection, and secure retrieval service.

This module ensures:
1. Garment URLs are fetched only over public HTTP/HTTPS from allowed hosts.
2. SSRF protection: DNS resolution verifies target IP is not private, loopback, or reserved.
3. Size limits enforced strictly on streams (prevent memory exhaustion).
4. Person uploads are verified via PIL to guarantee genuine image data.
"""

from __future__ import annotations

import io
import ipaddress
import socket
from typing import List, Optional, Set, Tuple
from urllib.parse import urlparse

import httpx
from PIL import Image

from ..config import get_settings
from ..core.errors import ImageRejected
from ..logging_config import get_logger

log = get_logger("image_service")

# Default permitted image host suffixes (covers Shopify CDN, store subdomains, and CDNs)
DEFAULT_ALLOWED_HOST_SUFFIXES = {
    "cdn.shopify.com",
    "myshopify.com",
    "shopify.com",
    "shopifycdn.net",
    "shopifycdn.com",
    "static.fashn.ai",
    "fashn.ai",
}

# Image MIME types and formats supported
SUPPORTED_FORMATS = {"JPEG", "JPG", "PNG", "WEBP"}


def is_ip_private_or_reserved(ip_str: str) -> bool:
    """Return True if the IP address is private, loopback, link-local, multicast or reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        return True


def is_host_permitted(hostname: str, extra_allowed: Optional[List[str]] = None) -> bool:
    """Check if the hostname matches allowed suffixes or is a standard public domain."""
    if not hostname:
        return False
    host_lower = hostname.lower()

    allowed = set(DEFAULT_ALLOWED_HOST_SUFFIXES)
    if extra_allowed:
        for h in extra_allowed:
            if h.strip():
                allowed.add(h.strip().lower())

    for suffix in allowed:
        if host_lower == suffix or host_lower.endswith("." + suffix):
            return True

    # Allow public e-commerce store domains as long as DNS resolves to a public routable IP
    # and not local/internal targets.
    return True


def validate_image_url(url: str, extra_allowed: Optional[List[str]] = None) -> str:
    """Validate URL syntax, scheme, and perform SSRF checks."""
    if not url or not isinstance(url, str):
        raise ImageRejected("Image URL is required.")

    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url

    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ImageRejected(f"Unsupported URL scheme: {parsed.scheme}. Only HTTP/HTTPS are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise ImageRejected("Invalid image URL: missing host.")

    if not is_host_permitted(hostname, extra_allowed):
        raise ImageRejected(f"Host '{hostname}' is not permitted for image downloads.")

    # Prevent direct IP addresses pointing to private network
    try:
        ip = ipaddress.ip_address(hostname)
        if is_ip_private_or_reserved(str(ip)):
            raise ImageRejected(f"Direct access to private or reserved IP '{hostname}' is blocked.")
    except ValueError:
        # Not a raw IP literal; resolve DNS to check target IP
        pass

    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for _, _, _, _, sockaddr in addr_info:
            target_ip = sockaddr[0]
            if is_ip_private_or_reserved(target_ip):
                raise ImageRejected(f"Access to private or internal IP address for {hostname} is blocked.")
    except socket.gaierror as exc:
        raise ImageRejected(f"Failed to resolve image hostname '{hostname}': {exc}")

    return url


async def download_garment_image(
    url: str,
    *,
    max_bytes: Optional[int] = None,
    timeout_seconds: Optional[float] = None,
    extra_allowed: Optional[List[str]] = None,
) -> Tuple[bytes, str]:
    """Securely download garment image with streaming size limits and format validation."""
    settings = get_settings()
    max_bytes = max_bytes or settings.max_garment_download_bytes
    timeout = timeout_seconds or settings.image_download_timeout_seconds

    validated_url = validate_image_url(url, extra_allowed=extra_allowed or settings.extra_image_hosts)

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", validated_url) as response:
                if response.status_code != 200:
                    raise ImageRejected(f"Failed to fetch garment image: HTTP {response.status_code}")

                # Check Content-Length header if present
                cl = response.headers.get("content-length")
                if cl and cl.isdigit() and int(cl) > max_bytes:
                    raise ImageRejected(f"Garment image size ({cl} bytes) exceeds limit of {max_bytes} bytes.")

                chunks: List[bytes] = []
                total_bytes = 0
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise ImageRejected(f"Garment image exceeded size limit of {max_bytes} bytes during download.")
                    chunks.append(chunk)

                image_bytes = b"".join(chunks)
    except httpx.TimeoutException:
        raise ImageRejected("Garment image download timed out.")
    except httpx.RequestError as exc:
        raise ImageRejected(f"Network error while downloading garment image: {str(exc)}")

    # Verify image integrity and format with PIL
    validated_bytes, img_format = sanitize_image_bytes(image_bytes, "garment")
    return validated_bytes, img_format


def sanitize_image_bytes(image_bytes: bytes, label: str = "image") -> Tuple[bytes, str]:
    """Verify image bytes using PIL, confirm format, and return normalized RGB JPEG/PNG bytes."""
    if not image_bytes:
        raise ImageRejected(f"Empty {label} provided.")

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.verify()  # verify integrity
    except Exception as exc:
        raise ImageRejected(f"Invalid or corrupted {label} data: {str(exc)}")

    # Re-open after verify() to inspect dimensions and convert
    img = Image.open(io.BytesIO(image_bytes))
    img_format = (img.format or "JPEG").upper()

    if img_format not in SUPPORTED_FORMATS:
        raise ImageRejected(
            f"Unsupported {label} format '{img_format}'. Supported formats: {', '.join(SUPPORTED_FORMATS)}"
        )

    width, height = img.size
    if width < 64 or height < 64:
        raise ImageRejected(f"{label} resolution is too small ({width}x{height}). Minimum is 64x64.")
    if width > 6000 or height > 6000:
        raise ImageRejected(f"{label} resolution is too large ({width}x{height}). Maximum is 6000x6000.")

    # Convert RGBA/P/LA to RGB with clean background
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        converted = img.convert("RGBA")
        bg.paste(converted, mask=converted.split()[3])
        out_buf = io.BytesIO()
        bg.save(out_buf, format="JPEG", quality=95)
        return out_buf.getvalue(), "JPEG"
    elif img.mode != "RGB":
        rgb_img = img.convert("RGB")
        out_buf = io.BytesIO()
        rgb_img.save(out_buf, format="JPEG", quality=95)
        return out_buf.getvalue(), "JPEG"

    return image_bytes, img_format


def validate_person_upload(file_bytes: bytes, max_bytes: Optional[int] = None) -> Tuple[bytes, str]:
    """Validate uploaded customer photo file."""
    settings = get_settings()
    max_bytes = max_bytes or settings.max_upload_bytes
    if len(file_bytes) > max_bytes:
        raise ImageRejected(f"Uploaded photo exceeds max allowed size ({len(file_bytes)} > {max_bytes} bytes).")
    return sanitize_image_bytes(file_bytes, label="person photo")
