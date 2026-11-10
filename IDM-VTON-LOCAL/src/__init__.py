"""IDM-VTON Local High Performance Pipeline"""
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
demo_dir = os.path.join(ROOT_DIR, "gradio_demo")
if os.path.exists(demo_dir) and demo_dir not in sys.path:
    sys.path.insert(0, demo_dir)

from src.model_loader import load_pipeline, get_pipeline, get_preprocessors, get_gpu_info
from src.preprocessing import preprocess_person, preprocess_garment
from src.inference import run_tryon
from src.utils import load_image, pil_to_base64, save_result

__all__ = [
    "load_pipeline",
    "get_pipeline",
    "get_preprocessors",
    "get_gpu_info",
    "preprocess_person",
    "preprocess_garment",
    "run_tryon",
    "load_image",
    "pil_to_base64",
    "save_result"
]
