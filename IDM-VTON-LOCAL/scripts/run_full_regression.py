"""
Master Regression & Performance Suite for TryVtri VTON
Tests:
- Step benchmark (15, 20, 25, 30 steps) for speed vs quality
- Clothing: white logo hoodie, tee, shirt, jacket, long coat, dresses (short & long), jeans, shorts, skirt
- On-model product image test (strips model's pants & loafers, preserves customer's jeans & sneakers)
- Glasses: 5 diverse face portraits
- Hats: 4 headwear styles (cap, beanie, fedora, bucket hat)
- Shoes: 5 footwear photos
Generates before/after contact sheets and reports p50/p95 latency.
"""

import os
import sys
import time
import json
import io
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT_DIR, "outputs/regression")
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_URL = "http://127.0.0.1:8888"
HEADERS = {"X-Inference-Key": "sk_tryvtri_inference_2026_rtx5080"}

def make_panel(person_img: Image.Image, garment_img: Image.Image, result_img: Image.Image, label: str, duration: float, score: float) -> Image.Image:
    """Creates a clean 3-column before / garment / after panel."""
    pw, ph = 240, 320
    p1 = person_img.convert("RGB").resize((pw, ph), Image.Resampling.LANCZOS)
    p2 = garment_img.convert("RGB").resize((pw, ph), Image.Resampling.LANCZOS)
    p3 = result_img.convert("RGB").resize((pw, ph), Image.Resampling.LANCZOS)

    header_h = 36
    panel_w = pw * 3 + 40
    panel_h = ph + header_h + 15
    panel = Image.new("RGB", (panel_w, panel_h), (20, 23, 28))
    draw = ImageDraw.Draw(panel)

    draw.text((15, 10), f"{label} | Time: {duration:.2f}s | Quality Score: {score:.2f}", fill=(240, 240, 240))
    panel.paste(p1, (15, header_h))
    panel.paste(p2, (15 + pw + 10, header_h))
    panel.paste(p3, (15 + (pw + 10) * 2, header_h))

    return panel

def call_infer(person_path: str, product_path: str, category: str, steps: int = 20) -> tuple:
    with open(person_path, "rb") as fp, open(product_path, "rb") as fg:
        files = {
            "person_image": ("person.jpg", fp, "image/jpeg"),
            "garment_image": ("garment.jpg", fg, "image/jpeg")
        }
        data = {
            "category": category,
            "num_inference_steps": steps,
            "guidance_scale": 2.0,
            "seed": 42
        }
        t0 = time.time()
        resp = requests.post(f"{BASE_URL}/infer", files=files, data=data, headers=HEADERS, timeout=90)
        elapsed = time.time() - t0

    if resp.status_code != 200:
        raise RuntimeError(f"Request failed {resp.status_code}: {resp.text}")

    score = float(resp.headers.get("X-TryVtri-Quality-Score", "1.0"))
    warning = resp.headers.get("X-TryVtri-Quality-Warning", "False") == "True"
    res_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    return res_img, elapsed, score, warning

def assemble_sheet(panels: list, output_path: str, title: str):
    if not panels:
        return
    pw, ph = panels[0].size
    title_h = 60
    sheet = Image.new("RGB", (pw, title_h + ph * len(panels)), (14, 16, 20))
    draw = ImageDraw.Draw(sheet)
    draw.text((20, 20), title, fill=(255, 255, 255))
    for idx, p in enumerate(panels):
        sheet.paste(p, (0, title_h + idx * ph))
    sheet.save(output_path, "PNG")
    print(f"Saved contact sheet: {output_path}")

def run_suite():
    test_set = os.path.join(ROOT_DIR, "inputs/test_set")
    results_summary = {}

    # -------------------------------------------------------------
    # 1. DIFFUSION STEP BENCHMARK (RTX 5080 sm_120)
    # -------------------------------------------------------------
    print("\n=== 1. RUNNING DIFFUSION STEP BENCHMARK (15, 20, 25, 30 STEPS) ===")
    p_hoodie = os.path.join(test_set, "clothing/person_layered.jpg")
    g_hoodie = os.path.join(test_set, "clothing/white_hoodie.jpg")
    benchmark_results = []
    
    for s in [15, 20, 25, 30]:
        try:
            img, dur, score, warn = call_infer(p_hoodie, g_hoodie, "tops", steps=s)
            print(f"Steps: {s:2d} -> Latency: {dur:.2f}s | Quality Score: {score:.2f} | Warning: {warn}")
            benchmark_results.append({"steps": s, "latency": round(dur, 2), "quality": score})
        except Exception as e:
            print(f"Benchmark step {s} failed: {e}")
    results_summary["step_benchmark"] = benchmark_results

    # -------------------------------------------------------------
    # 2. CLOTHING REGRESSION (Shirts, Hoodies, Jackets, Coats, Dresses, Jeans, Shorts, Skirt, On-Model)
    # -------------------------------------------------------------
    print("\n=== 2. RUNNING CLOTHING REGRESSION ===")
    clothing_tests = [
        ("White Logo Hoodie (Layered Outfit)", p_hoodie, g_hoodie, "tops"),
        ("Tee with Chest Logo", os.path.join(test_set, "clothing/person_layered.jpg"), os.path.join(test_set, "clothing/tee_with_logo.jpg"), "tops"),
        ("Formal Shirt", p_hoodie, os.path.join(test_set, "clothing/formal_shirt.jpg"), "tops"),
        ("Outer Jacket", p_hoodie, os.path.join(test_set, "clothing/jacket.jpg"), "tops"),
        ("Long Coat", p_hoodie, os.path.join(test_set, "clothing/long_coat.jpg"), "tops"),
        ("Mini Dress (Short)", os.path.join(test_set, "clothing/person_layered.jpg"), os.path.join(test_set, "clothing/mini_dress.jpg"), "dresses"),
        ("Long Dress", os.path.join(test_set, "clothing/person_layered.jpg"), os.path.join(test_set, "clothing/long_dress.jpg"), "dresses"),
        ("Denim Jeans (Bottoms)", os.path.join(test_set, "clothing/person_layered.jpg"), os.path.join(test_set, "clothing/jeans.jpg"), "bottoms"),
        ("Denim Shorts (Bottoms)", os.path.join(test_set, "clothing/person_layered.jpg"), os.path.join(test_set, "clothing/denim_shorts.jpg"), "bottoms"),
        ("Pleated Skirt (Bottoms)", os.path.join(test_set, "clothing/person_layered.jpg"), os.path.join(test_set, "clothing/pleated_skirt.jpg"), "bottoms"),
        ("On-Model Shopify Product (Model Stripped)", os.path.join(test_set, "clothing/person_layered.jpg"), os.path.join(test_set, "clothing/on_model_hoodie.jpg"), "tops"),
    ]

    clothing_panels = []
    clothing_times = []
    for label, p_path, g_path, cat in clothing_tests:
        if not (os.path.exists(p_path) and os.path.exists(g_path)):
            continue
        try:
            res_img, dur, score, warn = call_infer(p_path, g_path, cat, steps=20)
            clothing_times.append(dur)
            p_img = Image.open(p_path)
            g_img = Image.open(g_path)
            panel = make_panel(p_img, g_img, res_img, label, dur, score)
            clothing_panels.append(panel)
            print(f"Clothing [{label}]: {dur:.2f}s | Score: {score:.2f}")
        except Exception as e:
            print(f"Clothing [{label}] ERROR: {e}")

    assemble_sheet(clothing_panels, os.path.join(OUTPUT_DIR, "contact_sheet_clothing.png"), "TryVtri VTON — Complete Clothing Regression (RTX 5080)")

    # -------------------------------------------------------------
    # 3. GLASSES REGRESSION (5 Diverse Faces)
    # -------------------------------------------------------------
    print("\n=== 3. RUNNING GLASSES REGRESSION (5 DIVERSE FACES) ===")
    glasses_tests = [
        ("Front Portrait", os.path.join(test_set, "glasses/face_1_front.jpg"), os.path.join(test_set, "glasses/sunglasses_black.jpg")),
        ("3/4 Turn Face", os.path.join(test_set, "glasses/face_2_turn.jpg"), os.path.join(test_set, "glasses/glasses_round.jpg")),
        ("Hair Covering Ears", os.path.join(test_set, "glasses/face_3_hair.jpg"), os.path.join(test_set, "glasses/sunglasses_aviator.jpg")),
        ("Pre-existing Eyewear", os.path.join(test_set, "glasses/face_4_existing_glasses.jpg"), os.path.join(test_set, "glasses/sunglasses_black.jpg")),
        ("Diverse Skin Tone", os.path.join(test_set, "glasses/face_5_diverse.jpg"), os.path.join(test_set, "glasses/glasses_round.jpg")),
    ]
    glasses_panels = []
    glasses_times = []
    for label, p_path, g_path in glasses_tests:
        if not (os.path.exists(p_path) and os.path.exists(g_path)):
            continue
        try:
            res_img, dur, score, warn = call_infer(p_path, g_path, "glasses")
            glasses_times.append(dur)
            p_img = Image.open(p_path)
            g_img = Image.open(g_path)
            panel = make_panel(p_img, g_img, res_img, label, dur, score)
            glasses_panels.append(panel)
            print(f"Glasses [{label}]: {dur:.2f}s | Score: {score:.2f}")
        except Exception as e:
            print(f"Glasses [{label}] ERROR: {e}")

    assemble_sheet(glasses_panels, os.path.join(OUTPUT_DIR, "contact_sheet_glasses.png"), "TryVtri VTON — Glasses & Eyewear Regression (MediaPipe 3D)")

    # -------------------------------------------------------------
    # 4. HATS REGRESSION (4 Headwear Styles)
    # -------------------------------------------------------------
    print("\n=== 4. RUNNING HATS REGRESSION (4 HEADWEAR STYLES) ===")
    hats_tests = [
        ("Baseball Cap", os.path.join(test_set, "hats/face_hat_1.jpg"), os.path.join(test_set, "hats/baseball_cap.jpg")),
        ("Winter Beanie", os.path.join(test_set, "hats/face_hat_2.jpg"), os.path.join(test_set, "hats/beanie.jpg")),
        ("Wide Brim Fedora", os.path.join(test_set, "hats/face_hat_3.jpg"), os.path.join(test_set, "hats/fedora.jpg")),
        ("Bucket Hat", os.path.join(test_set, "hats/face_hat_4.jpg"), os.path.join(test_set, "hats/bucket_hat.jpg")),
    ]
    hats_panels = []
    hats_times = []
    for label, p_path, g_path in hats_tests:
        if not (os.path.exists(p_path) and os.path.exists(g_path)):
            continue
        try:
            res_img, dur, score, warn = call_infer(p_path, g_path, "hats")
            hats_times.append(dur)
            p_img = Image.open(p_path)
            g_img = Image.open(g_path)
            panel = make_panel(p_img, g_img, res_img, label, dur, score)
            hats_panels.append(panel)
            print(f"Hats [{label}]: {dur:.2f}s | Score: {score:.2f}")
        except Exception as e:
            print(f"Hats [{label}] ERROR: {e}")

    assemble_sheet(hats_panels, os.path.join(OUTPUT_DIR, "contact_sheet_hats.png"), "TryVtri VTON — Hats & Headwear Regression (3D Head Alignment)")

    # -------------------------------------------------------------
    # 5. SHOES REGRESSION (5 Footwear Photos)
    # -------------------------------------------------------------
    print("\n=== 5. RUNNING SHOES REGRESSION (5 FOOTWEAR STYLES) ===")
    shoes_tests = [
        ("Red Sneakers (Front Feet)", os.path.join(test_set, "shoes/feet_1_front.jpg"), os.path.join(test_set, "shoes/sneakers_red.jpg")),
        ("White Sneakers (Street View)", os.path.join(test_set, "shoes/feet_2_street.jpg"), os.path.join(test_set, "shoes/sneakers_white.jpg")),
        ("Leather Boots (Fashion)", os.path.join(test_set, "shoes/feet_3_fashion.jpg"), os.path.join(test_set, "shoes/boots_leather.jpg")),
        ("Formal Shoes (Casual Outfit)", os.path.join(test_set, "shoes/feet_5_casual.jpg"), os.path.join(test_set, "shoes/formal_shoes.jpg")),
        ("Boots on Denim (Street)", os.path.join(test_set, "shoes/feet_4_boots.jpg"), os.path.join(test_set, "shoes/boots_leather.jpg")),
    ]
    shoes_panels = []
    shoes_times = []
    for label, p_path, g_path in shoes_tests:
        if not (os.path.exists(p_path) and os.path.exists(g_path)):
            continue
        try:
            res_img, dur, score, warn = call_infer(p_path, g_path, "shoes")
            shoes_times.append(dur)
            p_img = Image.open(p_path)
            g_img = Image.open(g_path)
            panel = make_panel(p_img, g_img, res_img, label, dur, score)
            shoes_panels.append(panel)
            print(f"Shoes [{label}]: {dur:.2f}s | Score: {score:.2f}")
        except Exception as e:
            print(f"Shoes [{label}] ERROR: {e}")

    assemble_sheet(shoes_panels, os.path.join(OUTPUT_DIR, "contact_sheet_shoes.png"), "TryVtri VTON — Shoes & Footwear Regression (Foot Alignment & Shadow)")

    # Latency Percentiles
    def calc_percentiles(times: list) -> dict:
        if not times:
            return {"p50": 0.0, "p95": 0.0, "mean": 0.0}
        arr = np.array(times)
        return {
            "p50": round(float(np.percentile(arr, 50)), 2),
            "p95": round(float(np.percentile(arr, 95)), 2),
            "mean": round(float(np.mean(arr)), 2)
        }

    summary = {
        "step_benchmark": benchmark_results,
        "latencies": {
            "clothing": calc_percentiles(clothing_times),
            "glasses": calc_percentiles(glasses_times),
            "hats": calc_percentiles(hats_times),
            "shoes": calc_percentiles(shoes_times)
        }
    }

    with open(os.path.join(OUTPUT_DIR, "regression_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== REGRESSION SUITE COMPLETED SUCCESSFULLY ===")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    run_suite()
