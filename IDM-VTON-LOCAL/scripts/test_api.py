"""
API Test Script for IDM-VTON FastAPI Service
Tests POST /tryon endpoint with base64 encoded images.
"""

import sys
import os
import requests
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.utils import pil_to_base64

def test_api():
    print("Testing FastAPI /tryon endpoint...")
    human_path = "/root/IDM-VTON/gradio_demo/example/human/00034_00.jpg"
    cloth_path = "/root/IDM-VTON/gradio_demo/example/cloth/04469_00.jpg"

    p_b64 = pil_to_base64(Image.open(human_path))
    g_b64 = pil_to_base64(Image.open(cloth_path))

    payload = {
        "person_image": p_b64,
        "garment_image": g_b64,
        "garment_description": "casual cotton top",
        "category": "upper_body",
        "denoise_steps": 20,
        "seed": 42
    }

    resp = requests.post("http://127.0.0.1:8888/tryon", json=payload, timeout=60)
    data = resp.json()

    print("=" * 65)
    print("API RESPONSE:")
    print("Status:", data.get("status"))
    print("Metrics:", data.get("metrics"))
    print("Image Data URL Received (length):", len(data.get("image", "")))
    print("=" * 65)

if __name__ == "__main__":
    test_api()
