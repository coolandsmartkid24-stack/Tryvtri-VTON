"""
Benchmark Script for IDM-VTON: Cold Start vs Warm Latency
Executes 2 consecutive virtual try-on requests to prove memory caching
and benchmark steady-state inference throughput.
"""

import os
import sys
import time
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.inference import run_tryon
from src.model_loader import load_pipeline, get_gpu_info

def benchmark():
    print("=" * 65)
    print("  IDM-VTON LATENCY BENCHMARK: COLD vs WARM INFERENCE")
    print("=" * 65)

    human_path = "/root/IDM-VTON/gradio_demo/example/human/00034_00.jpg"
    cloth_path = "/root/IDM-VTON/gradio_demo/example/cloth/04469_00.jpg"

    person_img = Image.open(human_path).convert("RGB")
    garment_img = Image.open(cloth_path).convert("RGB")

    print("\n--- RUN 1: Pipeline Initialization & First Inference ---")
    t1 = time.time()
    res1 = run_tryon(
        person_image=person_img,
        garment_image=garment_img,
        garment_description="casual top",
        denoise_steps=30,
        seed=101
    )
    r1_total = time.time() - t1

    print(f"Run 1 Preprocessing:   {res1['metrics']['preprocessing_seconds']}s")
    print(f"Run 1 UNet Diffusion:  {res1['metrics']['inference_seconds']}s")
    print(f"Run 1 Total Time:      {res1['metrics']['total_seconds']}s")

    print("\n--- RUN 2: Warm In-Memory Inference (No Model Reload) ---")
    t2 = time.time()
    res2 = run_tryon(
        person_image=person_img,
        garment_image=garment_img,
        garment_description="casual top variant",
        denoise_steps=30,
        seed=202
    )
    r2_total = time.time() - t2

    print(f"Run 2 Preprocessing:   {res2['metrics']['preprocessing_seconds']}s")
    print(f"Run 2 UNet Diffusion:  {res2['metrics']['inference_seconds']}s")
    print(f"Run 2 Total Time:      {res2['metrics']['total_seconds']}s")

    print("\n" + "=" * 65)
    print("  BENCHMARK SUMMARY")
    print("=" * 65)
    print(f"Cold Start Inference:  {res1['metrics']['total_seconds']}s")
    print(f"Warm Steady Inference: {res2['metrics']['total_seconds']}s")
    print(f"Speedup Factor:        {res1['metrics']['total_seconds'] / max(res2['metrics']['total_seconds'], 0.01):.2f}x")
    print(f"Steady Throughput:     ~{60 / res2['metrics']['total_seconds']:.1f} try-ons/minute")
    print("=" * 65)

if __name__ == "__main__":
    benchmark()
