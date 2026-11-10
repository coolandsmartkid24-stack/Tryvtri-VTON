"""
Prepare Test Assets for Virtual Try-On Regression Suite
Downloads and structures real test images for:
- Clothing (White hoodie on layered outfit, plain tee, jacket, jeans, dress, chest logo)
- Glasses (5 face variations: front, angled, hair over ears, existing glasses, diverse skin tones)
- Shoes (5 shoe variations: sneakers, boots, formal shoes, angled feet, front feet)
"""

import os
import sys
import requests
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DIR = os.path.join(ROOT_DIR, "inputs/test_set")

def download_image(url: str, save_path: str):
    """Downloads an image from URL if not already present."""
    if os.path.exists(save_path) and os.path.getsize(save_path) > 1000:
        return
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(resp.content)
            print(f"Downloaded: {save_path}")
    except Exception as e:
        print(f"Failed to download {url}: {e}")

def create_synthetic_logo_garment(base_garment_path: str, out_path: str, logo_text: str = "TRYVTRI"):
    """Creates a test garment with a sharp chest logo for logo-preservation testing."""
    if not os.path.exists(base_garment_path):
        return
    img = Image.open(base_garment_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    
    # Draw central chest emblem
    cx, cy = w // 2, int(h * 0.42)
    radius = int(w * 0.12)
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=(20, 20, 20), width=4, fill=(240, 240, 240))
    draw.rectangle([cx - radius + 8, cy - 12, cx + radius - 8, cy + 12], fill=(220, 30, 30))
    draw.text((cx - 30, cy - 6), logo_text, fill=(255, 255, 255))
    
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path)
    print(f"Created logo garment: {out_path}")

def prepare_all():
    # 1. CLOTHING TEST CASES
    # White hoodie on layered outfit (the primary failure case to verify)
    download_image(
        "https://images.unsplash.com/photo-1556905055-8f358a7a47b2?w=800", # hoodie
        os.path.join(TEST_DIR, "clothing/white_hoodie.jpg")
    )
    download_image(
        "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=800", # model layered outfit
        os.path.join(TEST_DIR, "clothing/person_layered.jpg")
    )
    download_image(
        "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=800", # plain tee
        os.path.join(TEST_DIR, "clothing/plain_tee.jpg")
    )
    download_image(
        "https://images.unsplash.com/photo-1551028719-00167b16eac5?w=800", # jacket
        os.path.join(TEST_DIR, "clothing/jacket.jpg")
    )
    download_image(
        "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=800", # jeans
        os.path.join(TEST_DIR, "clothing/jeans.jpg")
    )
    download_image(
        "https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=800", # dress
        os.path.join(TEST_DIR, "clothing/dress.jpg")
    )

    # 2. GLASSES TEST CASES (Product frames + 5 diverse face photos)
    # Glasses product frames
    download_image(
        "https://images.unsplash.com/photo-1511499767150-a48a237f0083?w=800", # sunglasses product
        os.path.join(TEST_DIR, "glasses/sunglasses_black.jpg")
    )
    download_image(
        "https://images.unsplash.com/photo-1574258495973-f010dfbb5371?w=800", # round optical glasses product
        os.path.join(TEST_DIR, "glasses/glasses_round.jpg")
    )
    download_image(
        "https://images.unsplash.com/photo-1508296695146-257a814070b4?w=800", # aviator sunglasses
        os.path.join(TEST_DIR, "glasses/sunglasses_aviator.jpg")
    )

    # 5 Faces:
    # 1. Front-facing clean portrait
    download_image(
        "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=800",
        os.path.join(TEST_DIR, "glasses/face_1_front.jpg")
    )
    # 2. Slight turn / 3/4 angle
    download_image(
        "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800",
        os.path.join(TEST_DIR, "glasses/face_2_turn.jpg")
    )
    # 3. Hair over ears
    download_image(
        "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=800",
        os.path.join(TEST_DIR, "glasses/face_3_hair.jpg")
    )
    # 4. Model with existing glasses
    download_image(
        "https://images.unsplash.com/photo-1570295999919-56ceb5ecca61?w=800",
        os.path.join(TEST_DIR, "glasses/face_4_existing_glasses.jpg")
    )
    # 5. Different skin tone
    download_image(
        "https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=800",
        os.path.join(TEST_DIR, "glasses/face_5_diverse.jpg")
    )

    # 3. SHOES TEST CASES (Product footwear + 5 full body photos)
    # Shoe products
    download_image(
        "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=800", # red sneakers
        os.path.join(TEST_DIR, "shoes/sneakers_red.jpg")
    )
    download_image(
        "https://images.unsplash.com/photo-1549298916-b41d501d3772?w=800", # sneakers multi
        os.path.join(TEST_DIR, "shoes/sneakers_white.jpg")
    )
    download_image(
        "https://images.unsplash.com/photo-1608256246200-53e635b5b65f?w=800", # leather boots
        os.path.join(TEST_DIR, "shoes/boots_leather.jpg")
    )
    download_image(
        "https://images.unsplash.com/photo-1533867617858-e7b97e060509?w=800", # formal dress shoes
        os.path.join(TEST_DIR, "shoes/formal_shoes.jpg")
    )

    # 5 Foot / Full Body Photos:
    download_image(
        "https://images.unsplash.com/photo-1509631179647-0177331693ae?w=800", # full body front
        os.path.join(TEST_DIR, "shoes/feet_1_front.jpg")
    )
    download_image(
        "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=800", # full body street
        os.path.join(TEST_DIR, "shoes/feet_2_street.jpg")
    )
    download_image(
        "https://images.unsplash.com/photo-1483985988355-763728e1935b?w=800", # full body fashion
        os.path.join(TEST_DIR, "shoes/feet_3_fashion.jpg")
    )
    download_image(
        "https://images.unsplash.com/photo-1529139574466-a303027c1d8b?w=800", # full body boots
        os.path.join(TEST_DIR, "shoes/feet_4_boots.jpg")
    )
    download_image(
        "https://images.unsplash.com/photo-1492562080023-ab3db95bfbce?w=800", # full body male casual
        os.path.join(TEST_DIR, "shoes/feet_5_casual.jpg")
    )

    # Create logo garment from plain tee
    create_synthetic_logo_garment(
        os.path.join(TEST_DIR, "clothing/plain_tee.jpg"),
        os.path.join(TEST_DIR, "clothing/tee_with_logo.jpg")
    )

if __name__ == "__main__":
    prepare_all()
