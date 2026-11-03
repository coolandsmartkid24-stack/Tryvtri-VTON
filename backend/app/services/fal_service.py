"""FAL AI integration for TryVtri virtual try-on.

Provides:
- Connectivity verification with FAL API
- Virtual try-on execution using FAL cloud models (e.g. fal-ai/fashn/tryon or fal-ai/idm-vton)
- Image payload formatting and graceful error handling
"""

from __future__ import annotations

import base64
import io
from typing import Optional, Tuple

import httpx

from ..config import get_settings
from ..core.errors import GpuError
from ..logging_config import get_logger

log = get_logger("fal_service")


async def test_fal_connectivity() -> dict:
    """Check FAL API credentials and connectivity."""
    settings = get_settings()
    if not settings.fal_key:
        return {"status": "unconfigured", "message": "FAL_KEY not set"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://rest.alpha.fal.ai/models",
                headers={"Authorization": f"Key {settings.fal_key}"},
            )
            return {
                "status": "connected" if resp.status_code == 200 else "error",
                "http_status": resp.status_code,
            }
    except Exception as exc:
        return {"status": "unreachable", "error": str(exc)}


async def run_fal_tryon(
    *,
    person_bytes: bytes,
    garment_bytes: bytes,
    category: str = "tops",
    timeout_seconds: Optional[float] = None,
) -> Tuple[bytes, str]:
    """Execute virtual try-on through FAL AI API.

    Returns:
        Tuple of (result_image_bytes, mime_type)
    """
    settings = get_settings()
    if not settings.fal_key:
        raise GpuError("FAL AI is not configured (missing FAL_KEY)")

    timeout = timeout_seconds or settings.inference_timeout_seconds

    # Encode images to data URLs
    person_b64 = base64.b64encode(person_bytes).decode("ascii")
    garment_b64 = base64.b64encode(garment_bytes).decode("ascii")
    person_data_url = f"data:image/jpeg;base64,{person_b64}"
    garment_data_url = f"data:image/jpeg;base64,{garment_b64}"

    endpoint = f"https://fal.run/{settings.fal_model_endpoint.strip('/')}"
    headers = {
        "Authorization": f"Key {settings.fal_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model_image": person_data_url,
        "garment_image": garment_data_url,
        "category": category,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            log.info("calling_fal_ai_vton", endpoint=endpoint, category=category)
            resp = await client.post(endpoint, json=payload, headers=headers)

            if resp.status_code != 200:
                err_text = resp.text
                log.error("fal_inference_failed", status=resp.status_code, body=err_text)
                raise GpuError(f"FAL AI try-on failed: HTTP {resp.status_code} - {err_text}")

            result = resp.json()
            image_url = None
            if "image" in result and isinstance(result["image"], dict):
                image_url = result["image"].get("url")
            elif "images" in result and result["images"]:
                image_url = result["images"][0].get("url")

            if not image_url:
                raise GpuError("FAL AI response did not contain an output image URL")

            # Fetch the resulting image
            img_resp = await client.get(image_url, timeout=30.0)
            if img_resp.status_code != 200:
                raise GpuError("Failed to download generated try-on image from FAL AI")

            return img_resp.content, img_resp.headers.get("content-type", "image/png")

    except httpx.TimeoutException:
        raise GpuError(f"FAL AI inference timed out after {timeout} seconds.")
    except Exception as exc:
        log.error("fal_request_exception", error=str(exc))
        raise GpuError(f"FAL AI communication error: {str(exc)}")
