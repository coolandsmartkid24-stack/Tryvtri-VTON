"""
TryVtri Virtual Try-On — FastAPI serverless proxy for fal.ai on Vercel.

Endpoints:
  POST /api/try-on   — person image (data URI) + garment URL → result image URL
  GET  /health       — health check

Authentication: FAL_KEY environment variable (set on Vercel project settings).
CORS: CORSMiddleware + exception handlers — REQUIRED because the Shopify
storefront browser calls this API cross-origin; without these headers the
browser blocks every request ("Failed to fetch").
"""

import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

import fal_client

app = FastAPI(title="TryVtri Virtual Try-On API")

FAL_MODEL = "fal-ai/flux-2-lora-gallery/virtual-tryon"

# fal-client reads FAL_KEY from environment (set on Vercel project settings)
if "FAL_KEY" not in os.environ:
    raise RuntimeError("FAL_KEY environment variable is not set on the server")

# ── CORS (browser-enforced; mandatory for cross-origin Shopify storefront) ───
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    max_age=86400,
)


# ── Exception handlers — CORS headers on error responses (422/500) too ───────

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        {"error": exc.detail},
        status_code=exc.status_code,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "86400",
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        {"error": "Invalid request", "details": exc.errors()},
        status_code=422,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "86400",
        },
    )


# ── OPTIONS preflight (browser handshake) ─────────────────────────────────────

@app.options("/api/try-on")
@app.options("/try-on")
@app.options("/api/try-on/api/try-on")
@app.options("/try-on/api/try-on")
@app.options("/api/try-on/")
@app.options("/try-on/")
@app.options("/api/try-on/api/try-on/")
@app.options("/try-on/api/try-on/")
def cors_preflight():
    return JSONResponse(
        {"ok": True},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "86400",
        },
    )


# ── Request / response models ────────────────────────────────────────────────

class TryOnRequest(BaseModel):
    image_base64: str
    garment_url: str
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


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "healthy", "service": "tryvtri-vton-api"}


@app.post("/api/try-on")
@app.post("/try-on")
@app.post("/api/try-on/api/try-on")
@app.post("/try-on/api/try-on")
@app.post("/api/try-on/")
@app.post("/try-on/")
@app.post("/api/try-on/api/try-on/")
@app.post("/try-on/api/try-on/")
def try_on(req: TryOnRequest):
    try:
        garment_url = req.garment_url.strip()
        if garment_url.startswith("//"):
            garment_url = "https:" + garment_url
        elif garment_url and not garment_url.startswith("http"):
            garment_url = "https://" + garment_url.lstrip("/")
        if not garment_url:
            raise HTTPException(status_code=400, detail="garment_url is required")

        final_prompt = req.prompt or "A person wearing the garment, virtual try-on, photorealistic, high detail"

        arguments: Dict[str, Any] = {
            "image_urls": [req.image_base64, garment_url],
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

        return TryOnResponse(
            images=images,
            seed=result.get("seed"),
            prompt=result.get("prompt"),
        )

    except HTTPException:
        raise
    except Exception as exc:
        s = str(exc)
        status = 404 if ("404" in s or "NOT_FOUND" in s or "Not Found" in s or "not found" in s) else 500
        if status == 404:
            s = ("NOT_FOUND: fal.ai could not fetch one of the images. "
                 "Check that both the person photo and this garment image open in a browser: " + garment_url + " | detail: " + s)
        raise HTTPException(status_code=status, detail=s)


# Mangum ASGI handler for Vercel Python serverless
try:
    from mangum import Mangum
    handler = Mangum(app)
except Exception:
    handler = app
