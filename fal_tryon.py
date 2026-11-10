"""
Fal.ai Virtual Try-On integration for TryVtri.

Wraps the fal-ai/flux-2-lora-gallery/virtual-tryon model:
  - Person image: uploaded by the user (local file path or public URL)
  - Garment image: served from Shopify CDN (public URL)
Returns the generated try-on image URL.
"""

import os
import json
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

import fal_client

FAL_MODEL = "fal-ai/flux-2-lora-gallery/virtual-tryon"

# API key provided by the user. Prefer FAL_KEY env var; fall back to the key below.
FAL_API_KEY = os.environ.get("FAL_KEY")

# fal-client reads credentials from the FAL_KEY environment variable.
if not FAL_API_KEY:
    raise RuntimeError(
        "FAL_KEY environment variable is not set. "
        "Export it (export FAL_KEY=\"...\") before running, or pass it to fal_client."
    )
os.environ["FAL_KEY"] = FAL_API_KEY


def _is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _upload_person_image(person_source: str) -> str:
    """
    Ensure the person image is a publicly accessible URL for fal.ai.
    - If it's already a URL, return it as-is.
    - If it's a local file path, upload it to fal storage and return the hosted URL.
    """
    if _is_url(person_source):
        return person_source

    p = Path(person_source)
    if not p.exists():
        raise FileNotFoundError(f"Person image not found: {person_source}")

    # fal_client.upload takes raw bytes + content type + file name and returns a hosted URL.
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    with open(p, "rb") as f:
        data = f.read()
    url = fal_client.upload(data, content_type=mime, file_name=p.name)
    return url


def virtual_tryon(
    person_image: str,
    garment_url: str,
    prompt: Optional[str] = None,
    guidance_scale: float = 2.5,
    num_inference_steps: int = 40,
    acceleration: str = "regular",
    enable_safety_checker: bool = True,
    output_format: str = "png",
    num_images: int = 1,
    lora_scale: float = 1.0,
    image_size: Optional[Dict[str, int]] = None,
    seed: Optional[int] = None,
    sync_mode: bool = False,
) -> Dict[str, Any]:
    """
    Run virtual try-on via fal.ai.

    Args:
        person_image: Local file path or public URL of the person/model photo.
        garment_url: Public URL of the garment image (Shopify CDN).
        prompt: Optional generation prompt.
        guidance_scale: CFG scale (default 2.5).
        num_inference_steps: Diffusion steps (default 40).
        acceleration: "regular" or "none" (default "regular").
        enable_safety_checker: Enable safety checker (default True).
        output_format: "png", "jpeg", or "webp" (default "png").
        num_images: Number of images to generate (default 1).
        lora_scale: Strength of virtual try-on effect (default 1).
        image_size: Optional {"width": int, "height": int}.
        seed: Optional random seed for reproducibility.
        sync_mode: If True, media returned as data URI and not saved in history.

    Returns:
        Dict with keys: images (list of {url, content_type, file_name, file_size, width, height}),
        seed, prompt.
    """
    person_url = _upload_person_image(person_image)

    if prompt is None:
        prompt = "A person wearing the garment, virtual try-on, photorealistic, high detail"

    arguments: Dict[str, Any] = {
        "image_urls": [person_url, garment_url],
        "prompt": prompt,
        "guidance_scale": guidance_scale,
        "num_inference_steps": num_inference_steps,
        "acceleration": acceleration,
        "enable_safety_checker": enable_safety_checker,
        "output_format": output_format,
        "num_images": num_images,
        "lora_scale": lora_scale,
        "sync_mode": sync_mode,
    }

    if image_size is not None:
        arguments["image_size"] = image_size
    if seed is not None:
        arguments["seed"] = seed

    result = fal_client.subscribe(FAL_MODEL, arguments=arguments, with_logs=True)
    return result


def virtual_tryon_submit(
    person_image: str,
    garment_url: str,
    prompt: Optional[str] = None,
    webhook_url: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Submit a virtual try-on request asynchronously (queue mode).
    Returns {"request_id": ...}. Use virtual_tryon_result() to fetch.
    """
    person_url = _upload_person_image(person_image)

    if prompt is None:
        prompt = "A person wearing the garment, virtual try-on, photorealistic, high detail"

    arguments: Dict[str, Any] = {
        "image_urls": [person_url, garment_url],
        "prompt": prompt,
    }
    arguments.update(kwargs)

    result = fal_client.submit(FAL_MODEL, arguments=arguments, webhook_url=webhook_url)
    request_id = getattr(result, "request_id", None)
    if request_id is None and isinstance(result, dict):
        request_id = result.get("request_id")
    return {"request_id": request_id}


def virtual_tryon_result(request_id: str, logs: bool = False) -> Dict[str, Any]:
    """Fetch the result of a previously submitted virtual try-on request."""
    return fal_client.result(FAL_MODEL, request_id=request_id)


def virtual_tryon_status(request_id: str, logs: bool = False) -> Dict[str, Any]:
    """Fetch the status of a previously submitted virtual try-on request."""
    return fal_client.status(FAL_MODEL, request_id=request_id, with_logs=logs)


if __name__ == "__main__":
    import sys

    # Usage: python fal_tryon.py <person_image_path_or_url> <garment_shopify_url> [prompt]
    if len(sys.argv) < 3:
        print("Usage: python fal_tryon.py <person_image> <garment_url> [prompt]")
        sys.exit(1)

    person = sys.argv[1]
    garment = sys.argv[2]
    prompt = sys.argv[3] if len(sys.argv) > 3 else None

    try:
        out = virtual_tryon(person, garment, prompt=prompt)
        print(json.dumps(out, indent=2))
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
