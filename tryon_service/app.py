"""Standalone GPU Inference Service for FASHN VTON 1.5.

Runs inside the Lium GPU pod (Ubuntu 22.04+ with NVIDIA RTX 5080 and CUDA 12.x).
Loads FASHN VTON 1.5 in bfloat16 on the GPU and serves fast try-on requests.
"""

from __future__ import annotations

import io
import os
import sys
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image

app = FastAPI(title="TryVtri FASHN VTON 1.5 Inference Engine", version="1.5.0")

_pipeline = None


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


@app.on_event("startup")
async def startup_event():
    # Warm up / check weights on startup if GPU available
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

    try:
        import torch

        gpu_available = torch.cuda.is_available()
        if gpu_available:
            gpu_name = torch.cuda.get_device_name(0)
            free_mem, total_mem = torch.cuda.mem_get_info()
            vram_free_gb = round(free_mem / (1024**3), 2)
    except Exception:
        pass

    return {
        "status": "healthy",
        "service": "fashn-vton-1.5-inference",
        "gpu_available": gpu_available,
        "gpu_name": gpu_name,
        "vram_free_gb": vram_free_gb,
    }


@app.post("/infer")
async def infer(
    person_image: UploadFile = File(...),
    garment_image: UploadFile = File(...),
    category: str = Form("tops"),
    num_inference_steps: int = Form(30),
    guidance_scale: float = Form(2.5),
):
    valid_categories = {"tops", "bottoms", "one-pieces"}
    clean_cat = category.strip().lower().replace("_", "-")
    if clean_cat not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{category}'. Must be one of: tops, bottoms, one-pieces",
        )

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
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
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
