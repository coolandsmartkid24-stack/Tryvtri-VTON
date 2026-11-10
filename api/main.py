from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os

import fal_client

app = FastAPI(title="TryVtri Virtual Try-On API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FAL_MODEL = "fal-ai/flux-2-lora-gallery/virtual-tryon"

# FAL_KEY is set as a Vercel Environment Variable
if "FAL_KEY" not in os.environ:
    raise RuntimeError("FAL_KEY environment variable is not set on the server")

fal_client.config(credentials=os.environ["FAL_KEY"])


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


@app.get("/health")
def health():
    return {"status": "healthy", "service": "tryvtri-vton-api"}


@app.post("/api/try-on", response_model=TryOnResponse)
async def try_on(req: TryOnRequest):
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

        result = await fal_client.subscribe_async(
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

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/try-on", response_model=TryOnResponse)
async def try_on_alias(req: TryOnRequest):
    return await try_on(req)


# Mangum ASGI handler for Vercel Python serverless functions
handler = Mangum(app)
