"""
Production FastAPI Inference Microservice for Virtual Try-On
Supports Clothing (Shirts, Hoodies, Jackets, Coats, Dresses, Pants, Trousers, Jeans, Shorts, Skirts),
Eyewear/Glasses, Shoes/Footwear, and Hats/Headwear.
Enforces single-inference concurrency lock, automatic quality gate, and OOM protection.
Runs on port 8888 (externally mapped to 40398).
"""

import os
import sys
import io
import time
import uuid
import asyncio
import requests
import torch
import gc
from typing import Optional, List
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from PIL import Image

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.inference import run_tryon
from src.model_loader import get_gpu_info, load_pipeline
import src.model_loader as ml
from src.utils import load_image, pil_to_base64

EXPECTED_INFERENCE_KEY = os.environ.get("INFERENCE_API_KEY", "sk_tryvtri_inference_2026_rtx5080").strip()

# GPU concurrency lock: strictly one inference at a time on 16GB VRAM
_INFERENCE_LOCK = asyncio.Lock()

app = FastAPI(
    title="TryVtri Complete Virtual Try-On Service",
    description="High-Speed Multi-Category Virtual Try-On Microservice for Clothing, Shoes, Glasses, and Hats",
    version="2.5.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def verify_api_key(request: Request):
    """Optional API key check for secure cloud microservice."""
    if not EXPECTED_INFERENCE_KEY:
        return
    provided = (
        request.headers.get("X-Inference-Key")
        or request.headers.get("x-inference-key")
        or request.headers.get("Authorization", "")
    )
    if provided.startswith("Bearer "):
        provided = provided[7:].strip()
    client_host = request.client.host if request.client else ""
    if client_host in ("127.0.0.1", "localhost") and not provided:
        return
    if provided and provided != EXPECTED_INFERENCE_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing inference key")

class TryonRequest(BaseModel):
    person_image: str = Field(..., description="Base64 encoded string or public URL of the model photo")
    garment_image: str = Field(..., description="Base64 encoded string or public URL of the garment photo")
    garment_description: Optional[str] = Field("clothing garment", description="Text description of the garment")
    category: Optional[str] = Field("auto", description="tops | bottoms | one-pieces | shoes | glasses | hats | auto")
    denoise_steps: Optional[int] = Field(22, ge=10, le=50, description="Number of diffusion denoising steps")
    guidance_scale: Optional[float] = Field(2.0, ge=1.0, le=5.0, description="Classifier-free guidance scale")
    seed: Optional[int] = Field(42, description="RNG Seed for reproducibility")
    output_format: Optional[str] = Field("png", description="png | webp | jpeg")

def fetch_image(source: str) -> Image.Image:
    """Helper to fetch image from URL or parse base64."""
    try:
        if source.startswith("http://") or source.startswith("https://"):
            resp = requests.get(source, timeout=15)
            resp.raise_for_status()
            return Image.open(io.BytesIO(resp.content)).convert("RGB")
        return load_image(source)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to load image: {str(e)}")

@app.on_event("startup")
async def startup_event():
    """Warm up pipeline on server startup."""
    print("Starting TryVtri Multi-Category API Service on port 8888...")
    try:
        load_pipeline()
        print("Pipeline warmed up and ready in GPU VRAM.")
    except Exception as e:
        print(f"Warning during pipeline warmup: {e}")

@app.get("/health")
def health():
    """Health check endpoint indicating model readiness and system status."""
    gpu = get_gpu_info()
    pipeline_loaded = ml._PIPELINE is not None
    vram_alloc_mb = 0.0
    vram_free_gb = 0.0
    if torch.cuda.is_available():
        vram_alloc_mb = round(torch.cuda.memory_allocated() / (1024**2), 2)
        free_bytes, _ = torch.cuda.mem_get_info()
        vram_free_gb = round(free_bytes / (1024**3), 2)

    return {
        "status": "healthy",
        "service": "tryvtri-complete-vton",
        "categories_supported": ["tops", "bottoms", "one-pieces", "shoes", "glasses", "hats"],
        "gpu_state": "ready" if pipeline_loaded else "sleeping",
        "pipeline_loaded": pipeline_loaded,
        "gpu_available": gpu.get("available", False),
        "gpu_name": gpu.get("name", "NVIDIA RTX 5080"),
        "vram_free_gb": vram_free_gb,
        "vram_allocated_mb": vram_alloc_mb,
        "gpu": gpu
    }

@app.get("/gpu")
def gpu_status():
    """Detailed GPU diagnostics and VRAM allocation."""
    return get_gpu_info()

@app.post("/wake")
def wake(request: Request):
    """Lifecycle endpoint to ensure pipeline is warmed up in VRAM."""
    verify_api_key(request)
    load_pipeline()
    gpu = get_gpu_info()
    return {
        "status": "ready",
        "service": "tryvtri-complete-vton",
        "pipeline_loaded": True,
        "gpu_name": gpu.get("name", "NVIDIA RTX 5080"),
        "vram_allocated_gb": gpu.get("vram_allocated_gb", 0.0),
        "message": "Pipeline resident in GPU memory and ready."
    }

@app.post("/sleep")
def sleep(request: Request):
    """Lifecycle endpoint for low-power sleep."""
    verify_api_key(request)
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return {
        "status": "sleeping",
        "service": "tryvtri-complete-vton",
        "message": "Low power idle acknowledged and VRAM cache cleared."
    }

@app.post("/infer")
async def infer(
    request: Request,
    person_image: UploadFile = File(...),
    garment_image: UploadFile = File(...),
    category: str = Form("auto"),
    num_timesteps: Optional[int] = Form(None),
    num_inference_steps: Optional[int] = Form(None),
    guidance_scale: float = Form(2.0),
    garment_photo_type: str = Form("model"),
    output_format: str = Form("png"),
    seed: int = Form(42),
):
    """
    Standard multipart try-on endpoint called directly by the TryVtri Vercel backend.
    Enforces concurrency lock to protect 16GB VRAM and handles CUDA OOM.
    Returns synthesized image bytes (PNG, WebP, or JPEG quality 90).
    """
    verify_api_key(request)
    # Default 22 steps for RTX 5080 to maintain latency < 8s
    steps = num_timesteps or num_inference_steps or 22
    req_id = uuid.uuid4().hex[:12]
    t0 = time.time()

    async with _INFERENCE_LOCK:
        try:
            person_bytes = await person_image.read()
            garment_bytes = await garment_image.read()

            person = Image.open(io.BytesIO(person_bytes)).convert("RGB")
            garment = Image.open(io.BytesIO(garment_bytes)).convert("RGB")

            result = run_tryon(
                person_image=person,
                garment_image=garment,
                garment_description="product item",
                category=category,
                denoise_steps=steps,
                guidance_scale=guidance_scale,
                seed=seed,
                request_id=req_id
            )

            output_img = result["result_image"]
            buf = io.BytesIO()
            clean_fmt = output_format.lower().strip()
            
            if clean_fmt in ("webp", "image/webp"):
                output_img.save(buf, format="WEBP", quality=90)
                media_type = "image/webp"
            elif clean_fmt in ("jpeg", "jpg", "image/jpeg"):
                output_img.save(buf, format="JPEG", quality=90)
                media_type = "image/jpeg"
            else:
                output_img.save(buf, format="PNG")
                media_type = "image/png"

            buf.seek(0)
            elapsed_ms = int((time.time() - t0) * 1000)

            metrics = result.get("metrics", {})
            headers = {
                "X-TryVtri-Quality-Score": str(metrics.get("quality_score", 1.0)),
                "X-TryVtri-Quality-Warning": str(metrics.get("quality_warning", False)),
                "X-TryVtri-Category": str(metrics.get("category", category)),
                "X-TryVtri-Latency-Ms": str(elapsed_ms)
            }

            return Response(content=buf.getvalue(), media_type=media_type, headers=headers)

        except torch.cuda.OutOfMemoryError as oom_exc:
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            print(f"[{req_id}] CUDA Out of Memory caught: {oom_exc}")
            raise HTTPException(
                status_code=503,
                detail="GPU temporarily out of memory. Please retry in a few moments."
            )
        except ValueError as val_exc:
            raise HTTPException(status_code=400, detail=str(val_exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Inference error: {str(exc)}")

@app.post("/tryon")
async def create_tryon(req: TryonRequest, request: Request):
    """
    JSON try-on endpoint with Base64 or URL payloads.
    """
    verify_api_key(request)
    req_id = uuid.uuid4().hex[:12]

    async with _INFERENCE_LOCK:
        try:
            person_img = fetch_image(req.person_image)
            garment_img = fetch_image(req.garment_image)

            result = run_tryon(
                person_image=person_img,
                garment_image=garment_img,
                garment_description=req.garment_description,
                category=req.category or "auto",
                denoise_steps=req.denoise_steps or 22,
                guidance_scale=req.guidance_scale or 2.0,
                seed=req.seed or 42,
                request_id=req_id
            )
            
            result_b64 = pil_to_base64(result["result_image"])
            return {
                "status": "success",
                "image": result_b64,
                "metrics": result["metrics"]
            }
        except torch.cuda.OutOfMemoryError as oom_exc:
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            raise HTTPException(status_code=503, detail="GPU temporarily out of memory.")
        except ValueError as val_exc:
            raise HTTPException(status_code=400, detail=str(val_exc))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8888))
    uvicorn.run(app, host="0.0.0.0", port=port)
