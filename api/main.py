"""
TryVtri Virtual Try-On — FastAPI serverless proxy for fal.ai on Vercel.

Endpoints:
  POST /api/try-on   — person image (data URI) + garment URL (Shopify CDN) → result image URL
  GET  /health       — health check

Authentication: FAL_KEY environment variable (set on Vercel project settings, never exposed to browser).
CORS: explicit headers on EVERY response (including errors and OPTIONS preflight).
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

import fal_client

app = FastAPI(title="TryVtri Virtual Try-On API")

FAL_MODEL = "fal-ai/flux-2-lora-gallery/virtual-tryon"

# fal-client reads FAL_KEY from the environment (set on Vercel project settings)
if "FAL_KEY" not in os.environ:
    raise RuntimeError("FAL_KEY environment variable is not set on the server")

# CORS headers applied to every response
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
}


def cors_json(content: Any, status_code: int = 200) -> JSONResponse:
    """Return JSONResponse with CORS headers always present."""
    return JSONResponse(content=content, status_code=status_code, headers=CORS_HEADERS)


# ── Preflight (OPTIONS) — must return 200 with CORS headers ──────────────────

@app.options("/api/try-on")
@app.options("/try-on")
@app.options("/health")
def cors_preflight():
    return cors_json({"ok": True}, 200)


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return cors_json({"status": "healthy", "service": "tryvtri-vton-api"})


class TryOnRequest(BaseModel):
    image_base64: str          # data URI of customer photo
    garment_url: str           # Shopify CDN URL of the garment image
    prompt: Optional[str] = None
    guidance_scale: Optional[float] = 2.5
    num_inference_steps: Optional[int] = 40
    acceleration: Optional[str] = "regular"
    enable_safety_checker: Optional[bool] = True
    output_format: Optional[str] = "png"
    num_images: Optional[int] = 1
    lora_scale: Optional[float] = 1.0
    image_size: Optional[Dict[str, int]] = None
    seed: Optional[int] = None
    sync_mode: Optional[bool] = False


class ImageOutput(BaseModel):
    url: str
    content_type: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None


class TryOnResponse(BaseModel):
    images: List[ImageOutput]
    seed: Optional[int] = None
    prompt: Optional[str] = None


@app.post("/api/try-on")
@app.post("/try-on")
def try_on(req: TryOnRequest):
    try:
        final_prompt = req.prompt or "A person wearing the garment, virtual try-on, photorealistic, high detail"

        arguments: Dict[str, Any] = {
            "image_urls": [req.image_base64, req.garment_url],
            "prompt": final_prompt,
            "guidance_scale": req.guidance_scale,
            "num_inference_steps": req.num_inference_steps,
            "acceleration": req.acceleration,
            "enable_safety_checker": req.enable_safety_checker,
            "output_format": req.output_format,
            "num_images": req.num_images,
            "lora_scale": req.lora_scale,
            "sync_mode": req.sync_mode,
        }

        if req.image_size is not None:
            arguments["image_size"] = req.image_size
        if req.seed is not None:
            arguments["seed"] = req.seed

        result = fal_client.subscribe(
            FAL_MODEL,
            arguments=arguments,
            with_logs=True,
        )

        images = []
        for img in (result.get("images") or []):
            images.append(ImageOutput(
                url=img.get("url", ""),
                content_type=img.get("content_type"),
                file_name=img.get("file_name"),
                file_size=img.get("file_size"),
                width=img.get("width"),
                height=img.get("height"),
            ))

        return cors_json(
            TryOnResponse(
                images=images,
                seed=result.get("seed"),
                prompt=result.get("prompt"),
            ).model_dump(),
            status_code=200,
        )

    except Exception as exc:
        return cors_json({"error": str(exc)}, status_code=500)


# Mangum ASGI handler for Vercel Python serverless
try:
    from mangum import Mangum
    handler = Mangum(app)
except Exception:
    handler = app
