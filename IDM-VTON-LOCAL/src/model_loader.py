"""
IDM-VTON Model Loader & GPU Memory Manager
Supports NVIDIA RTX 5080 (Blackwell sm_120) in FP16 precision.
Implements in-memory singleton pipeline for low-latency re-use without reloads.
"""

import os
import sys
import gc
import torch
import time
from typing import Dict, Any, Tuple

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
demo_dir = os.path.join(ROOT_DIR, "gradio_demo")
if os.path.exists(demo_dir) and demo_dir not in sys.path:
    sys.path.insert(0, demo_dir)

# Enable PyTorch expandable segments to eliminate CUDA fragmentation
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

_PIPELINE = None
_PREPROCESSORS = None
_DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"

def get_gpu_info() -> Dict[str, Any]:
    """Returns detected GPU specifications and current VRAM usage."""
    if not torch.cuda.is_available():
        return {
            "available": False,
            "device": "cpu",
            "name": "CPU",
            "compute_capability": None,
            "vram_total_gb": 0.0,
            "vram_allocated_gb": 0.0,
            "vram_free_gb": 0.0
        }
    
    props = torch.cuda.get_device_properties(0)
    alloc = torch.cuda.memory_allocated(0) / (1024 ** 3)
    free, total = torch.cuda.mem_get_info(0)
    
    return {
        "available": True,
        "device": _DEVICE,
        "name": props.name,
        "compute_capability": f"{props.major}.{props.minor}",
        "multi_processor_count": props.multi_processor_count,
        "vram_total_gb": round(total / (1024 ** 3), 2),
        "vram_allocated_gb": round(alloc, 2),
        "vram_free_gb": round(free / (1024 ** 3), 2)
    }

def load_pipeline(base_path: str = "yisol/IDM-VTON", device: str = None) -> Tuple[Any, Dict[str, Any]]:
    """
    Loads all IDM-VTON diffusion and vision models into GPU memory.
    Cached as a singleton to allow warm, instantaneous subsequent inferences.
    """
    global _PIPELINE, _PREPROCESSORS, _DEVICE
    if device is not None:
        _DEVICE = device

    if _PIPELINE is not None and _PREPROCESSORS is not None:
        return _PIPELINE, _PREPROCESSORS

    from src.tryon_pipeline import StableDiffusionXLInpaintPipeline as TryonPipeline
    from src.unet_hacked_garmnet import UNet2DConditionModel as UNet2DConditionModel_ref
    from src.unet_hacked_tryon import UNet2DConditionModel
    from transformers import (
        CLIPImageProcessor,
        CLIPVisionModelWithProjection,
        CLIPTextModel,
        CLIPTextModelWithProjection,
        AutoTokenizer,
    )
    from diffusers import DDPMScheduler, AutoencoderKL
    from preprocess.humanparsing.run_parsing import Parsing
    from preprocess.openpose.run_openpose import OpenPose

    t0 = time.time()
    print(f"[{time.strftime('%X')}] Initializing IDM-VTON pipeline on {_DEVICE}...")

    # Load UNet & UNet Encoder
    unet = UNet2DConditionModel.from_pretrained(
        base_path, subfolder="unet", torch_dtype=torch.float16
    ).to(_DEVICE)
    unet.requires_grad_(False)

    unet_encoder = UNet2DConditionModel_ref.from_pretrained(
        base_path, subfolder="unet_encoder", torch_dtype=torch.float16
    ).to(_DEVICE)
    unet_encoder.requires_grad_(False)

    # Tokenizers and text/image encoders
    tokenizer_one = AutoTokenizer.from_pretrained(base_path, subfolder="tokenizer", use_fast=False)
    tokenizer_two = AutoTokenizer.from_pretrained(base_path, subfolder="tokenizer_2", use_fast=False)
    noise_scheduler = DDPMScheduler.from_pretrained(base_path, subfolder="scheduler")

    text_encoder_one = CLIPTextModel.from_pretrained(
        base_path, subfolder="text_encoder", torch_dtype=torch.float16
    ).to(_DEVICE)
    text_encoder_two = CLIPTextModelWithProjection.from_pretrained(
        base_path, subfolder="text_encoder_2", torch_dtype=torch.float16
    ).to(_DEVICE)
    image_encoder = CLIPVisionModelWithProjection.from_pretrained(
        base_path, subfolder="image_encoder", torch_dtype=torch.float16
    ).to(_DEVICE)
    vae = AutoencoderKL.from_pretrained(
        base_path, subfolder="vae", torch_dtype=torch.float16
    ).to(_DEVICE)

    image_encoder.requires_grad_(False)
    vae.requires_grad_(False)
    text_encoder_one.requires_grad_(False)
    text_encoder_two.requires_grad_(False)

    pipe = TryonPipeline.from_pretrained(
        base_path,
        unet=unet,
        vae=vae,
        feature_extractor=CLIPImageProcessor(),
        text_encoder=text_encoder_one,
        text_encoder_2=text_encoder_two,
        tokenizer=tokenizer_one,
        tokenizer_2=tokenizer_two,
        scheduler=noise_scheduler,
        image_encoder=image_encoder,
        torch_dtype=torch.float16,
    )
    pipe.unet_encoder = unet_encoder
    pipe.to(_DEVICE)
    pipe.unet_encoder.to(_DEVICE)

    # Enable VAE tiling and slicing to eliminate high-resolution VRAM spikes
    pipe.enable_vae_tiling()
    pipe.enable_vae_slicing()

    # Preprocessors
    parsing_model = Parsing(0 if _DEVICE.startswith("cuda") else -1)
    openpose_model = OpenPose(0 if _DEVICE.startswith("cuda") else -1)
    if _DEVICE.startswith("cuda"):
        openpose_model.preprocessor.body_estimation.model.to(_DEVICE)

    _PREPROCESSORS = {
        "parsing": parsing_model,
        "openpose": openpose_model,
    }
    _PIPELINE = pipe

    elapsed = time.time() - t0
    gpu = get_gpu_info()
    print(f"[{time.strftime('%X')}] Pipeline successfully loaded in {elapsed:.2f}s | VRAM: {gpu['vram_allocated_gb']} GB used")

    return _PIPELINE, _PREPROCESSORS

def get_pipeline():
    """Returns singleton pipeline instance, loading it on demand if needed."""
    if _PIPELINE is None:
        return load_pipeline()[0]
    return _PIPELINE

def get_preprocessors():
    """Returns singleton preprocessors dictionary."""
    if _PREPROCESSORS is None:
        return load_pipeline()[1]
    return _PREPROCESSORS
