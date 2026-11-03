"""Standalone GPU Inference Service for FASHN VTON 1.5.

Runs inside the Lium GPU pod (Ubuntu 22.04+ with NVIDIA RTX 5080 and CUDA 12.x).
Loads FASHN VTON 1.5 in bfloat16 on the GPU and serves fast try-on requests.
Supports on-demand sleep and wake lifecycle to conserve power and VRAM when idle.
"""

from __future__ import annotations

import gc
import io
import os
import sys
from typing import Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from PIL import Image

app = FastAPI(title="TryVtri FASHN VTON 1.5 Inference Engine", version="1.5.0")

_pipeline = None


def verify_api_key(request: Request):
    expected_key = os.environ.get("INFERENCE_API_KEY", "").strip()
    if not expected_key:
        return
    provided = request.headers.get("X-Inference-Key") or request.headers.get("Authorization", "")
    if provided.startswith("Bearer "):
        provided = provided[7:].strip()
    if provided != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing inference key")


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        try:
            import torch
            from fashn_vton import TryOnPipeline

            weights_dir = os.environ.get("WEIGHTS_DIR", "./weights")
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"Initializing FASHN VTON 1.5 pipeline on device: {device}")
            _pipeline = TryOnPipeline(weights_dir=weights_dir)
            print("Pipeline successfully initialized.")
        except Exception as exc:
            print(f"Error loading TryOnPipeline: {exc}", file=sys.stderr)
            raise
    return _pipeline


def unload_pipeline():
    """Unload model from GPU memory and clear CUDA cache to enter low-power sleep."""
    global _pipeline
    if _pipeline is not None:
        try:
            del _pipeline
            _pipeline = None
            gc.collect()
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.ipc_collect()
            except Exception:
                pass
            print("FASHN VTON 1.5 pipeline unloaded and VRAM cleared.")
        except Exception as exc:
            print(f"Warning during pipeline unload: {exc}", file=sys.stderr)
            _pipeline = None


@app.on_event("startup")
async def startup_event():
    # Detect GPU hardware on startup
    try:
        import torch

        if torch.cuda.is_available():
            print(f"GPU Detected: {torch.cuda.get_device_name(0)}")
            print(f"Total VRAM: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.2f} GB")
    except Exception as e:
        print(f"Startup check warning: {e}")


@app.get("/health")
def health():
    gpu_available = False
    gpu_name = None
    vram_free_gb = None
    vram_allocated_mb = 0.0
    pipeline_loaded = _pipeline is not None

    try:
        import torch

        gpu_available = torch.cuda.is_available()
        if gpu_available:
            gpu_name = torch.cuda.get_device_name(0)
            free_mem, total_mem = torch.cuda.mem_get_info()
            vram_free_gb = round(free_mem / (1024**3), 2)
            vram_allocated_mb = round(torch.cuda.memory_allocated() / (1024**2), 2)
    except Exception:
        pass

    return {
        "status": "healthy",
        "service": "fashn-vton-1.5-inference",
        "gpu_state": "ready" if pipeline_loaded else "sleeping",
        "pipeline_loaded": pipeline_loaded,
        "gpu_available": gpu_available,
        "gpu_name": gpu_name,
        "vram_free_gb": vram_free_gb,
        "vram_allocated_mb": vram_allocated_mb,
    }


@app.post("/sleep")
def sleep_gpu(request: Request):
    """Admin or lifecycle manager trigger to put GPU into low-power sleep mode."""
    verify_api_key(request)
    unload_pipeline()
    vram_free = None
    try:
        import torch

        if torch.cuda.is_available():
            free_mem, _ = torch.cuda.mem_get_info()
            vram_free = round(free_mem / (1024**3), 2)
    except Exception:
        pass
    return {
        "status": "sleeping",
        "service": "fashn-vton-1.5-inference",
        "pipeline_loaded": False,
        "vram_free_gb": vram_free,
        "message": "GPU pipeline unloaded and VRAM cleared.",
    }


@app.post("/wake")
def wake_gpu(request: Request):
    """Pre-warm or wake the GPU pipeline on-demand."""
    verify_api_key(request)
    get_pipeline()
    vram_free = None
    gpu_name = None
    try:
        import torch

        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            free_mem, _ = torch.cuda.mem_get_info()
            vram_free = round(free_mem / (1024**3), 2)
    except Exception:
        pass
    return {
        "status": "ready",
        "service": "fashn-vton-1.5-inference",
        "pipeline_loaded": True,
        "gpu_name": gpu_name,
        "vram_free_gb": vram_free,
        "message": "GPU pipeline loaded and ready for inference.",
    }


@app.post("/infer")
async def infer(
    request: Request,
    person_image: UploadFile = File(...),
    garment_image: UploadFile = File(...),
    category: str = Form("tops"),
    num_timesteps: Optional[int] = Form(None),
    num_inference_steps: Optional[int] = Form(None),
    guidance_scale: float = Form(1.5),
    garment_photo_type: str = Form("model"),
    seed: int = Form(42),
):
    verify_api_key(request)
    valid_categories = {"tops", "bottoms", "one-pieces"}
    clean_cat = category.strip().lower().replace("_", "-")
    if clean_cat not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{category}'. Must be one of: tops, bottoms, one-pieces",
        )

    # Reconcile timesteps
    steps = num_timesteps or num_inference_steps or 30

    try:
        person_bytes = await person_image.read()
        garment_bytes = await garment_image.read()

        person = Image.open(io.BytesIO(person_bytes)).convert("RGB")
        garment = Image.open(io.BytesIO(garment_bytes)).convert("RGB")

        pipeline = get_pipeline()
        result = pipeline(
            person_image=person,
            garment_image=garment,
            category=clean_cat,
            garment_photo_type=garment_photo_type if garment_photo_type in ("model", "flat-lay") else "model",
            num_timesteps=steps,
            guidance_scale=guidance_scale,
            seed=seed,
        )

        output_img = result.images[0]
        buf = io.BytesIO()
        output_img.save(buf, format="PNG")
        buf.seek(0)

        return Response(content=buf.getvalue(), media_type="image/png")

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inference error: {str(exc)}")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
