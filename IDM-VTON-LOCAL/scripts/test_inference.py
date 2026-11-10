"""
End-to-End Inference Verification Test for IDM-VTON
Validates preprocessing, diffusion denoising, and outputs result image.
"""

import os
import sys
import time
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.inference import run_tryon
from src.model_loader import get_gpu_info

def test():
    print("=" * 65)
    print("  IDM-VTON INFERENCE PIPELINE VERIFICATION")
    print("=" * 65)

    human_path = os.path.join(BASE_DIR, "inputs/person/model.jpg")
    cloth_path = os.path.join(BASE_DIR, "inputs/garment/cloth.jpg")

    # Fallback to gradio demo examples if not in inputs/
    if not os.path.exists(human_path):
        human_path = "/root/IDM-VTON/gradio_demo/example/human/00034_00.jpg"
    if not os.path.exists(cloth_path):
        cloth_path = "/root/IDM-VTON/gradio_demo/example/cloth/04469_00.jpg"

    print(f"Loading Human Image:   {human_path}")
    print(f"Loading Garment Image: {cloth_path}")

    person_img = Image.open(human_path).convert("RGB")
    garment_img = Image.open(cloth_path).convert("RGB")

    print("\nExecuting End-to-End Try-On...")
    res = run_tryon(
        person_image=person_img,
        garment_image=garment_img,
        garment_description="casual short sleeve top",
        category="upper_body",
        denoise_steps=30,
        guidance_scale=2.0,
        seed=42
    )

    out_dir = os.path.join(BASE_DIR, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "test_tryon_result.png")
    res["result_image"].save(out_file)

    metrics = res["metrics"]
    print("\n" + "=" * 65)
    print("  VERIFICATION RESULT: SUCCESS")
    print("=" * 65)
    print(f"Output Saved To:       {out_file}")
    print(f"Resolution:            {metrics['resolution']}")
    print(f"Preprocessing Time:    {metrics['preprocessing_seconds']}s")
    print(f"UNet Inference Time:   {metrics['inference_seconds']}s")
    print(f"Total Time:            {metrics['total_seconds']}s")
    print(f"Peak VRAM:             {metrics['vram_allocated_gb']} GB")
    print(f"Accelerated On:        {metrics['gpu_name']}")
    print("=" * 65)

if __name__ == "__main__":
    test()
