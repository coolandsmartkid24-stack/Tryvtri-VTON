"""Try-on inference client.

Communicates with the FASHN VTON 1.5 inference service running on the GPU pod.
Also provides a fallback synthetic compositing engine for local testing without GPU.
"""

from __future__ import annotations

import base64
import io
import time
from typing import Optional, Tuple

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import get_settings
from ..core.errors import GpuError, ValidationError
from ..logging_config import get_logger

log = get_logger("inference_client")

# TryVtri Multi-Category Supported Categories: Clothing, Shoes, Glasses, Hats
VALID_CATEGORIES = {"tops", "bottoms", "one-pieces", "shoes", "glasses", "hats", "auto"}


def validate_category(category: Optional[str]) -> str:
    """Validate garment category according to TryVtri specifications.

    Supported categories:
    - tops: Upper body (t-shirts, shirts, blouses, jackets, coats, hoodies)
    - bottoms: Lower body (pants, jeans, skirts, shorts)
    - one-pieces: Full body (dresses, jumpsuits, rompers)
    - shoes: Footwear (sneakers, boots, formal shoes)
    - glasses: Eyewear and sunglasses
    - hats: Headwear, caps, and beanies
    - auto: Zero-shot automatic category detection from product image
    """
    if not category:
        return "tops"
    cat_clean = category.strip().lower().replace("_", "-").replace(" ", "-")
    if cat_clean in ("top", "shirt", "t-shirt", "jacket", "blouse", "coat", "hoodie", "sweater", "upper-body"):
        return "tops"
    if cat_clean in ("bottom", "pants", "pant", "jeans", "skirt", "shorts", "trouser", "lower-body"):
        return "bottoms"
    if cat_clean in ("one-piece", "onepiece", "dress", "jumpsuit", "overall", "gown", "dresses"):
        return "one-pieces"
    if cat_clean in ("shoe", "shoes", "footwear", "sneaker", "sneakers", "boot", "boots", "heels", "sandals"):
        return "shoes"
    if cat_clean in ("glasses", "sunglasses", "eyewear", "spectacles", "shades"):
        return "glasses"
    if cat_clean in ("hat", "hats", "cap", "caps", "beanie", "headwear", "fedora", "beret"):
        return "hats"
    if cat_clean in ("auto", "detect"):
        return "auto"

    if cat_clean not in VALID_CATEGORIES:
        raise ValidationError(
            f"Category '{category}' is unsupported. "
            f"Supported categories are: {', '.join(sorted(VALID_CATEGORIES))}."
        )
    return cat_clean


async def run_vton_inference(
    *,
    endpoint: str,
    person_bytes: bytes,
    garment_bytes: bytes,
    category: str,
    mock_mode: bool = False,
    timeout_seconds: Optional[float] = None,
) -> Tuple[bytes, str]:
    """Execute virtual try-on inference.

    Returns:
        Tuple of (result_image_bytes, mime_type)
    """
    category = validate_category(category)
    settings = get_settings()
    timeout = timeout_seconds or settings.inference_timeout_seconds

    # 1) If in mock mode or local endpoint without GPU worker, generate synthetic preview
    if mock_mode or "mock" in endpoint:
        log.info("generating_synthetic_preview_for_mock_mode", category=category)
        return _generate_mock_tryon_result(person_bytes, garment_bytes, category), "image/png"

    # 2) Live GPU Inference Service via HTTP
    files = {
        "person_image": ("person.jpg", person_bytes, "image/jpeg"),
        "garment_image": ("garment.jpg", garment_bytes, "image/jpeg"),
    }
    data = {"category": category}
    req_headers = {}
    if settings.inference_api_key:
        req_headers["X-Inference-Key"] = settings.inference_api_key

    max_retries = 2
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{endpoint.rstrip('/')}/infer",
                    files=files,
                    data=data,
                    headers=req_headers,
                )
                if resp.status_code != 200:
                    err_text = resp.text
                    log.error("gpu_inference_failed", status=resp.status_code, body=err_text)
                    raise GpuError(f"Try-on generation failed on GPU: HTTP {resp.status_code} - {err_text}")

                content_type = resp.headers.get("content-type", "")
                if "image" in content_type:
                    return resp.content, content_type

                # Check if JSON with base64 result
                body = resp.json()
                if "output_base64" in body:
                    result_bytes = base64.b64decode(body["output_base64"])
                    return result_bytes, "image/png"
                if "result_url" in body:
                    # Fetch output image from result_url
                    img_resp = await client.get(body["result_url"], timeout=30.0)
                    return img_resp.content, img_resp.headers.get("content-type", "image/png")

                raise GpuError("Inference service did not return an image.")

        except httpx.ConnectError as ce:
            if attempt < max_retries:
                log.warning("gpu_inference_connect_retry", attempt=attempt, error=str(ce))
                import asyncio
                await asyncio.sleep(2.0)
                continue
            raise
        except httpx.TimeoutException:
            raise GpuError(f"Virtual try-on model inference timed out after {timeout} seconds.")
        except Exception as exc:
            log.warning("gpu_inference_failed_evaluating_fallback", error=str(exc))
            if settings.fal_key:
                try:
                    from .fal_service import run_fal_tryon
                    log.info("falling_back_to_fal_ai")
                    return await run_fal_tryon(
                        person_bytes=person_bytes,
                        garment_bytes=garment_bytes,
                        category=category,
                        timeout_seconds=timeout,
                    )
                except Exception as fal_exc:
                    log.error("fal_fallback_failed", error=str(fal_exc))

            if settings.environment != "production":
                log.info("using_synthetic_preview_fallback")
                return _generate_mock_tryon_result(person_bytes, garment_bytes, category), "image/png"
            raise GpuError(f"Could not connect to inference service: {str(exc)}")


def _generate_mock_tryon_result(person_bytes: bytes, garment_bytes: bytes, category: str) -> bytes:
    """Generate a high quality visual composited preview for local testing and mock mode."""
    person_img = Image.open(io.BytesIO(person_bytes)).convert("RGB")
    garment_img = Image.open(io.BytesIO(garment_bytes)).convert("RGB")

    pw, ph = person_img.size

    # Scale garment to proportion of person
    if category == "tops":
        gw = int(pw * 0.6)
        gh = int(ph * 0.4)
        gx = int(pw * 0.2)
        gy = int(ph * 0.28)
    elif category == "bottoms":
        gw = int(pw * 0.55)
        gh = int(ph * 0.45)
        gx = int(pw * 0.22)
        gy = int(ph * 0.52)
    else:  # one-pieces
        gw = int(pw * 0.65)
        gh = int(ph * 0.7)
        gx = int(pw * 0.18)
        gy = int(ph * 0.25)

    garment_resized = garment_img.resize((gw, gh), Image.Resampling.LANCZOS)

    # Composite result
    result = person_img.copy()
    # Semi-blend garment over person
    result.paste(garment_resized, (gx, gy))

    # Add a clean aesthetic watermark badge indicating TryVtri preview
    draw = ImageDraw.Draw(result)
    badge_text = "TryVtri VTON Preview"
    draw.rectangle([10, ph - 35, 180, ph - 10], fill=(0, 0, 0, 180))
    draw.text((18, ph - 30), badge_text, fill=(255, 255, 255))

    out_io = io.BytesIO()
    result.save(out_io, format="PNG")
    return out_io.getvalue()
