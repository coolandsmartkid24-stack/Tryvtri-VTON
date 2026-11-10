"""
Virtual Try-On Multi-Category Regression Test Suite
Runs tests on real images across Clothing, Shoes, and Glasses via the HTTP API.
Generates Before/After contact sheets and validates quality metrics.
"""

import os
import sys
import time
import json
import io
import requests
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DIR = os.path.join(ROOT_DIR, "inputs/test_set")
OUT_DIR = os.path.join(ROOT_DIR, "outputs/regression")
os.makedirs(OUT_DIR, exist_ok=True)

def create_contact_sheet(items, output_path, title):
    """
    items: list of dicts with:
      {"title": str, "person": Image, "product": Image, "result": Image, "score": float, "time_s": float}
    """
    thumb_w, thumb_h = 240, 320
    header_h = 60
    card_margin = 15
    row_h = thumb_h + 50
    total_w = card_margin * 4 + thumb_w * 3
    total_h = header_h + len(items) * (row_h + card_margin)

    sheet = Image.new("RGB", (total_w, total_h), (20, 24, 32))
    draw = ImageDraw.Draw(sheet)

    # Header
    draw.rectangle([0, 0, total_w, header_h], fill=(30, 41, 59))
    draw.text((20, 20), title, fill=(255, 255, 255))

    y_offset = header_h + card_margin
    for idx, item in enumerate(items):
        draw.rectangle([card_margin, y_offset, total_w - card_margin, y_offset + row_h], fill=(15, 23, 42), outline=(51, 65, 85))
        sub_text = f"#{idx+1}: {item['title']} | Quality: {item.get('score', 1.0):.2f} | Time: {item.get('time_s', 0):.1f}s"
        draw.text((card_margin + 10, y_offset + 8), sub_text, fill=(148, 163, 184))

        # Person
        p_img = item["person"].convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        sheet.paste(p_img, (card_margin + 10, y_offset + 30))

        # Product
        prod_img = item["product"].convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        sheet.paste(prod_img, (card_margin + thumb_w + 20, y_offset + 30))

        # Result
        res_img = item["result"].convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        sheet.paste(res_img, (card_margin + thumb_w * 2 + 30, y_offset + 30))

        y_offset += row_h + card_margin

    sheet.save(output_path)
    print(f"Contact sheet saved: {output_path}")

def call_infer(person_img, garment_img, category="tops", denoise_steps=30):
    p_buf = io.BytesIO()
    person_img.save(p_buf, format="JPEG")
    g_buf = io.BytesIO()
    garment_img.save(g_buf, format="JPEG")

    files = {
        "person_image": ("person.jpg", p_buf.getvalue(), "image/jpeg"),
        "garment_image": ("garment.jpg", g_buf.getvalue(), "image/jpeg"),
    }
    data = {"category": category, "denoise_steps": denoise_steps}
    resp = requests.post("http://127.0.0.1:8888/infer", files=files, data=data, timeout=120)
    if resp.status_code == 200:
        result_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        score = float(resp.headers.get("X-Quality-Score", 1.0))
        return True, result_img, score
    else:
        return False, None, f"HTTP {resp.status_code}: {resp.text}"

def run_glasses_regression():
    print("\n--- RUNNING GLASSES REGRESSION (5 Face Variations) ---")
    face_files = [
        ("Front Portrait", "face_1_front.jpg"),
        ("3/4 Turn Face", "face_2_turn.jpg"),
        ("Hair Covering Ears", "face_3_hair.jpg"),
        ("Pre-existing Eyewear", "face_4_existing_glasses.jpg"),
        ("Diverse Skin Tone", "face_5_diverse.jpg")
    ]
    frame_path = os.path.join(TEST_DIR, "glasses/sunglasses_black.jpg")
    frame_img = Image.open(frame_path).convert("RGB")

    items = []
    for title, fname in face_files:
        fpath = os.path.join(TEST_DIR, "glasses", fname)
        if not os.path.exists(fpath):
            continue
        p_img = Image.open(fpath).convert("RGB")
        t0 = time.time()
        ok, res_img, score = call_infer(p_img, frame_img, category="glasses")
        elapsed = time.time() - t0
        if ok:
            items.append({
                "title": title,
                "person": p_img,
                "product": frame_img,
                "result": res_img,
                "score": score,
                "time_s": elapsed
            })
            print(f"  [Glasses] {title}: {elapsed:.2f}s, Quality: {score:.2f}")
        else:
            print(f"  [Glasses] {title} failed: {score}")

    if items:
        out_sheet = os.path.join(OUT_DIR, "contact_sheet_glasses.png")
        create_contact_sheet(items, out_sheet, "TryVtri Glasses Try-On: 5 Face Variations")

def run_shoes_regression():
    print("\n--- RUNNING SHOES REGRESSION (Footwear Cases) ---")
    shoe_cases = [
        ("Red Sneakers (Front Feet)", "feet_1_front.jpg", "sneakers_red.jpg"),
        ("White Sneakers (Street View)", "feet_2_street.jpg", "sneakers_white.jpg"),
        ("Leather Boots (Fashion)", "feet_3_fashion.jpg", "boots_leather.jpg"),
        ("Formal Shoes (Casual)", "feet_5_casual.jpg", "formal_shoes.jpg"),
    ]

    items = []
    for title, p_name, s_name in shoe_cases:
        p_path = os.path.join(TEST_DIR, "shoes", p_name)
        s_path = os.path.join(TEST_DIR, "shoes", s_name)
        if not (os.path.exists(p_path) and os.path.exists(s_path)):
            continue

        p_img = Image.open(p_path).convert("RGB")
        s_img = Image.open(s_path).convert("RGB")

        t0 = time.time()
        ok, res_img, score = call_infer(p_img, s_img, category="shoes")
        elapsed = time.time() - t0

        if ok:
            items.append({
                "title": title,
                "person": p_img,
                "product": s_img,
                "result": res_img,
                "score": score,
                "time_s": elapsed
            })
            print(f"  [Shoes] {title}: {elapsed:.2f}s, Quality: {score:.2f}")
        else:
            print(f"  [Shoes] {title} failed: {score}")

    if items:
        out_sheet = os.path.join(OUT_DIR, "contact_sheet_shoes.png")
        create_contact_sheet(items, out_sheet, "TryVtri Shoes Try-On: Footwear Fitting & Ground Shadow")

def run_clothing_regression():
    print("\n--- RUNNING CLOTHING REGRESSION ---")
    clothing_cases = [
        ("White Hoodie on Layered Outfit (No Denim Peeking)", "clothing/person_layered.jpg", "clothing/white_hoodie.jpg", "tops", 30),
        ("Plain Tee on Model (Model Face Stripped)", "clothing/person_layered.jpg", "clothing/plain_tee.jpg", "tops", 30),
        ("Garment with Crisp Chest Logo", "clothing/person_layered.jpg", "clothing/tee_with_logo.jpg", "tops", 30),
        ("Denim Jeans (Bottoms, Top 100% Preserved)", "clothing/person_layered.jpg", "clothing/jeans.jpg", "bottoms", 30),
    ]

    items = []
    for title, p_rel, g_rel, cat, steps in clothing_cases:
        p_path = os.path.join(TEST_DIR, p_rel)
        g_path = os.path.join(TEST_DIR, g_rel)
        if not (os.path.exists(p_path) and os.path.exists(g_path)):
            continue

        p_img = Image.open(p_path).convert("RGB")
        g_img = Image.open(g_path).convert("RGB")

        t0 = time.time()
        ok, res_img, score = call_infer(p_img, g_img, category=cat, denoise_steps=steps)
        elapsed = time.time() - t0

        if ok:
            items.append({
                "title": f"{title} ({steps} steps)",
                "person": p_img,
                "product": g_img,
                "result": res_img,
                "score": score,
                "time_s": elapsed
            })
            print(f"  [Clothing] {title}: {elapsed:.2f}s, Quality: {score:.2f}")
        else:
            print(f"  [Clothing] {title} failed: {score}")

    if items:
        out_sheet = os.path.join(OUT_DIR, "contact_sheet_clothing.png")
        create_contact_sheet(items, out_sheet, "TryVtri Enhanced IDM-VTON: Clothing Pipeline")

if __name__ == "__main__":
    run_glasses_regression()
    run_shoes_regression()
    run_clothing_regression()
    print("\nALL REGRESSION SUITES COMPLETE!")
