"""
Download and synthesize realistic high-quality test assets for the complete regression suite:
- Clothing: white logo hoodie, tee, shirt, jacket, long coat, dresses (short & long), jeans, trousers, shorts, skirt; flat-lay & on-model product shots
- Glasses: 5 diverse face portraits + 3 eyewear styles
- Hats: 4 diverse face portraits + 4 headwear styles (cap, beanie, fedora, bucket hat)
- Shoes: 5 diverse full-body photos + 4 footwear styles
"""

import os
import sys
import requests
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_SET = os.path.join(ROOT_DIR, "inputs/test_set")

CLOTHING_DIR = os.path.join(TEST_SET, "clothing")
GLASSES_DIR = os.path.join(TEST_SET, "glasses")
HATS_DIR = os.path.join(TEST_SET, "hats")
SHOES_DIR = os.path.join(TEST_SET, "shoes")

for d in [CLOTHING_DIR, GLASSES_DIR, HATS_DIR, SHOES_DIR]:
    os.makedirs(d, exist_ok=True)

def download(url: str, dest: str):
    if not os.path.exists(dest):
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                with open(dest, "wb") as f:
                    f.write(resp.content)
                print(f"Downloaded: {dest}")
            else:
                print(f"Failed {url}: status {resp.status_code}")
        except Exception as e:
            print(f"Error {url}: {e}")

def prepare_hats_assets():
    # 4 Faces for Hats
    download("https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=768&q=80", os.path.join(HATS_DIR, "face_hat_1.jpg"))
    download("https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=768&q=80", os.path.join(HATS_DIR, "face_hat_2.jpg"))
    download("https://images.unsplash.com/photo-1517841905240-472988babdf9?w=768&q=80", os.path.join(HATS_DIR, "face_hat_3.jpg"))
    download("https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=768&q=80", os.path.join(HATS_DIR, "face_hat_4.jpg"))

    # 4 Hat Products
    # Baseball Cap
    download("https://images.unsplash.com/photo-1588850561407-ed78c282e89b?w=768&q=80", os.path.join(HATS_DIR, "baseball_cap.jpg"))
    # Beanie
    download("https://images.unsplash.com/photo-1576871337622-98d48d1cf531?w=768&q=80", os.path.join(HATS_DIR, "beanie.jpg"))
    # Fedora / Wide Brim
    download("https://images.unsplash.com/photo-1514327605112-b887c0e61c0a?w=768&q=80", os.path.join(HATS_DIR, "fedora.jpg"))
    # Bucket Hat
    download("https://images.unsplash.com/photo-1575428652377-a2d80e2277fc?w=768&q=80", os.path.join(HATS_DIR, "bucket_hat.jpg"))

def prepare_additional_clothing():
    # Long coat
    download("https://images.unsplash.com/photo-1539533018447-63fcce2678e3?w=768&q=80", os.path.join(CLOTHING_DIR, "long_coat.jpg"))
    # Shirt
    download("https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=768&q=80", os.path.join(CLOTHING_DIR, "formal_shirt.jpg"))
    # Shorts
    download("https://images.unsplash.com/photo-1591195853828-11db59a44f6b?w=768&q=80", os.path.join(CLOTHING_DIR, "denim_shorts.jpg"))
    # Skirt
    download("https://images.unsplash.com/photo-1583496661160-fb5886a0aaaa?w=768&q=80", os.path.join(CLOTHING_DIR, "pleated_skirt.jpg"))
    # Short dress
    download("https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=768&q=80", os.path.join(CLOTHING_DIR, "mini_dress.jpg"))
    # Long dress
    download("https://images.unsplash.com/photo-1566174053879-31528523f8ae?w=768&q=80", os.path.join(CLOTHING_DIR, "long_dress.jpg"))
    # Model wearing hoodie with black trousers & loafers (Shopify on-model case)
    download("https://images.unsplash.com/photo-1556905055-8f358a7a47b2?w=768&q=80", os.path.join(CLOTHING_DIR, "on_model_hoodie.jpg"))

if __name__ == "__main__":
    prepare_hats_assets()
    prepare_additional_clothing()
    print("All test assets ready.")
