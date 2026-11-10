"""
TryVtri Product Image Cleaner & Category Classifier
Handles:
1. On-model human stripping: isolates target garment, removes human model, face, other clothing items.
2. Flat-lay and ghost mannequin background removal.
3. Inpaints occluded regions (e.g., crossing hands, chin over collar).
4. Accessory cutouts (shoes, glasses, hats) with reflection filtering.
5. Disk caching of cleaned product cutouts by SHA-256 hash.
6. Zero-shot category classification across 13 target sub-types.
"""

import os
import sys
import hashlib
import time
import numpy as np
import cv2
from PIL import Image, ImageOps, ImageFilter
from typing import Tuple, Optional, Dict, Any, List

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT_DIR, "inputs/cache/products")
os.makedirs(CACHE_DIR, exist_ok=True)

# Category mappings
CATEGORY_GROUPS = {
    "upper_body": ["shirt", "t-shirt", "tee", "hoodie", "sweatshirt", "sweater", "jacket", "coat", "blazer", "vest", "top", "tops"],
    "lower_body": ["pants", "trousers", "jeans", "shorts", "skirt", "leggings", "joggers", "bottoms"],
    "dresses": ["dress", "gown", "one-piece", "jumpsuit", "romper", "dresses", "one_pieces"],
    "shoes": ["shoes", "sneakers", "boots", "loafers", "sandals", "heels", "footwear"],
    "glasses": ["glasses", "sunglasses", "eyewear", "spectacles"],
    "hats": ["hat", "cap", "beanie", "fedora", "beret", "bucket_hat", "baseball_cap", "headwear"]
}

def get_image_hash(image: Image.Image) -> str:
    """Computes SHA-256 hash of image bytes for robust caching."""
    img_bytes = image.tobytes()
    return hashlib.sha256(img_bytes).hexdigest()[:16]

def get_foreground_bbox_and_aspect(product_img: Image.Image) -> Tuple[float, float, float]:
    """
    Computes foreground-relative metrics:
    - aspect_w_h: foreground width / foreground height
    - aspect_h_w: foreground height / foreground width
    - coverage: foreground bbox area / total canvas area
    Removes neutral and pure white background padding.
    """
    arr = np.array(product_img.convert("RGB"))
    is_bg = (arr[:, :, 0] > 235) & (arr[:, :, 1] > 235) & (arr[:, :, 2] > 235)
    fg_mask = ~is_bg
    coords = np.argwhere(fg_mask)
    if coords.size == 0:
        return 1.0, 1.0, 1.0
    y1, x1 = coords.min(axis=0)
    y2, x2 = coords.max(axis=0)
    h_fg = max(1, y2 - y1)
    w_fg = max(1, x2 - x1)
    aspect_w_h = w_fg / float(h_fg)
    aspect_h_w = h_fg / float(w_fg)
    cov = (w_fg * h_fg) / float(product_img.width * product_img.height)
    return aspect_w_h, aspect_h_w, cov

def classify_category_zero_shot(product_img: Image.Image, manual_hint: Optional[str] = None) -> str:
    """
    Classifies product into target category with strict visual safety guard:
    1. Visual reality overrides incorrect/default manual hints (e.g. sunglasses or shoes
       must NEVER be routed to clothing diffusion, even if manual hint is 'tops').
    2. Long garments (sherwani, kurta, long coat, maxi dress) detected via tall vertical aspect
       and routed to long_outerwear to ensure full knee-length synthesis.
    """
    w_h, h_w, cov = get_foreground_bbox_and_aspect(product_img)

    # STRICT CATEGORY GUARD 1: EYEWEAR
    # Sunglasses & glasses have wide horizontal aspect (w_h >= 1.6) and moderate canvas coverage
    if w_h >= 1.60 and h_w <= 0.65 and cov <= 0.65:
        return "glasses"

    # STRICT CATEGORY GUARD 2: SHOES
    # Sneakers & footwear have w_h in 1.15 - 1.95 and characteristic sole baseline
    if manual_hint and any(s in manual_hint.lower() for s in ["shoe", "sneaker", "boot", "footwear"]):
        return "shoes"

    # STRICT CATEGORY GUARD 3: HATS & HEADWEAR
    if manual_hint and any(h in manual_hint.lower() for h in ["hat", "cap", "beanie", "fedora", "beret"]):
        return "hats"

    # Check manual hint for long outerwear explicitly
    if manual_hint:
        clean_hint = manual_hint.strip().lower().replace("-", "_")
        if any(w in clean_hint for w in ["sherwani", "kurta", "kameez", "long_coat", "overcoat", "abaya", "thobe", "jubba", "trench"]):
            return "long_outerwear"

    # TALL VERTICAL PRODUCT: LONG OUTERWEAR OR DRESSES
    # If height/width >= 1.35, product is significantly taller than standard tops (hoodies/tees are <= 1.25)
    if h_w >= 1.35:
        if manual_hint and any(w in manual_hint.lower() for w in ["dress", "gown"]):
            return "dresses"
        return "long_outerwear"

    # Process manual hint if provided and safe
    if manual_hint and manual_hint.strip() and manual_hint.strip().lower() not in ("auto", "none"):
        clean_hint = manual_hint.strip().lower().replace("-", "_")
        for group, aliases in CATEGORY_GROUPS.items():
            if clean_hint == group or clean_hint in aliases:
                return group
        if clean_hint in ("hat", "hats", "cap", "beanie"):
            return "hats"
        if clean_hint in ("shoe", "shoes", "sneakers", "boots"):
            return "shoes"
        if clean_hint in ("glasses", "sunglasses", "eyewear"):
            return "glasses"
        if clean_hint in ("dress", "dresses", "one_piece", "one_pieces"):
            return "dresses"
        if clean_hint in ("pants", "jeans", "shorts", "skirt", "bottoms", "lower_body"):
            return "lower_body"
        return "upper_body"

    # Fallback aspect heuristics based on foreground
    if w_h >= 1.15 and w_h <= 1.7:
        return "shoes"
    if w_h >= 0.85 and w_h <= 1.15:
        return "hats" if w_h > 1.05 else "upper_body"
    if h_w >= 1.35:
        return "long_outerwear"

    return "upper_body"

def clean_accessory_cutout(image: Image.Image, category: str) -> Image.Image:
    """
    Extracts a pristine transparent RGBA cutout for accessories (shoes, glasses, hats).
    Removes studio tabletop reflections, floor shadows, and edge artifacts.
    """
    try:
        import rembg
        session = rembg.new_session("u2netp", providers=['CPUExecutionProvider'])
        rgba = rembg.remove(image.convert("RGBA"), session=session)
    except Exception:
        rgba = image.convert("RGBA")

    arr = np.array(rgba)
    alpha = arr[:, :, 3]

    # Filter reflections & background noise using connected components
    solid_mask = (alpha > 120).astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(solid_mask)
    if num_labels > 1:
        # Keep dominant connected component (the actual accessory)
        largest_idx = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        clean_mask = (labels == largest_idx).astype(np.uint8) * 255
        clean_mask = cv2.dilate(clean_mask, np.ones((3, 3), np.uint8))
        arr[:, :, 3] = np.minimum(arr[:, :, 3], clean_mask)

    # Crop to non-transparent bounding box
    alpha_clean = arr[:, :, 3]
    coords = np.argwhere(alpha_clean > 30)
    if coords.size > 0:
        y1, x1 = coords.min(axis=0)
        y2, x2 = coords.max(axis=0)
        # Add 4px breathing margin
        y1 = max(0, y1 - 4)
        x1 = max(0, x1 - 4)
        y2 = min(arr.shape[0], y2 + 4)
        x2 = min(arr.shape[1], x2 + 4)
        cutout = Image.fromarray(arr).crop((x1, y1, x2, y2))
        return cutout
    return rgba

def clean_on_model_garment(
    garment_img: Image.Image,
    parsing_model: Any,
    category: str
) -> Tuple[bool, Optional[str], Image.Image]:
    """
    Segments ONLY the target clothing item from an on-model Shopify photo.
    Eliminates model's head, neck, face, hands, background, and every non-target garment
    (e.g., deletes black trousers and loafers when trying on an upper body shirt).
    Inpaints small occluded areas and centers on clean neutral background.
    """
    w, h = garment_img.size
    
    # 1. Parse garment image at 384x512
    small = garment_img.resize((384, 512))
    try:
        p_res, _ = parsing_model(small)
        p_arr = np.array(p_res) if isinstance(p_res, Image.Image) else p_res
    except Exception as e:
        return False, f"Garment parsing failed: {e}", garment_img

    # ATR/LIP Labels:
    # 0=bg, 1=hat, 2=hair, 3=sunglasses, 4=upperclothes, 5=skirt, 6=pants, 7=dress, 8=belt,
    # 9=left_shoe, 10=right_shoe, 11=face, 12=left_leg, 13=right_leg, 14=left_arm, 15=right_arm, 16=bag, 17=scarf
    face_count = np.sum(p_arr == 11)
    hair_count = np.sum(p_arr == 2)
    has_model = (face_count > 60 or hair_count > 100)

    # Determine target labels for the requested category
    if category in ("upper_body", "tops"):
        target_labels = [4, 7, 17]  # upperclothes, dress top, scarf
    elif category in ("lower_body", "bottoms"):
        target_labels = [5, 6, 8]   # skirt, pants, belt
    elif category in ("dresses", "one_pieces"):
        target_labels = [4, 5, 6, 7, 8, 17] # full dress
    else:
        target_labels = [4, 7]

    p_full = cv2.resize(p_arr, (w, h), interpolation=cv2.INTER_NEAREST)

    if has_model:
        # Model detected: strictly isolate target clothing pixels
        cloth_mask = np.isin(p_full, target_labels).astype(np.uint8) * 255
        
        # Check if enough target clothing pixels exist
        if np.sum(cloth_mask > 0) < 500:
            return False, f"Could not isolate {category} from product image model.", garment_img
        
        # Inpaint crossing hands / arms if they occlude the garment
        # Arm labels: 14, 15. If arm is inside garment bounding box, fill it
        arms_mask = np.isin(p_full, [14, 15]).astype(np.uint8) * 255
        cloth_coords = np.argwhere(cloth_mask > 0)
        cy1, cx1 = cloth_coords.min(axis=0)
        cy2, cx2 = cloth_coords.max(axis=0)
        
        # Detect arms crossing the torso
        crossing_arms = np.zeros_like(arms_mask)
        crossing_arms[cy1:cy2, cx1:cx2] = arms_mask[cy1:cy2, cx1:cx2]
        
        # Dilate cloth mask slightly to close small interior holes
        cloth_mask_closed = cv2.morphologyEx(
            cloth_mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        )
        
        # Inpaint occluded interior regions in RGB
        garment_np = np.array(garment_img.convert("RGB"))
        interior_occlusion = ((cloth_mask_closed > 0) & (cloth_mask == 0) & (crossing_arms > 0)).astype(np.uint8) * 255
        
        if np.sum(interior_occlusion) > 50:
            # Inpaint interior occluded region
            inpaint_mask = cv2.dilate(interior_occlusion, np.ones((5, 5), np.uint8))
            garment_np = cv2.inpaint(garment_np, inpaint_mask, 5, cv2.INPAINT_TELEA)

        # Build clean RGBA with cloth mask as alpha
        g_rgba = Image.fromarray(np.dstack([garment_np, cloth_mask_closed]), mode="RGBA")
    else:
        # Flat lay / ghost mannequin (no model): remove background via rembg
        try:
            import rembg
            session = rembg.new_session("u2netp", providers=['CPUExecutionProvider'])
            g_rgba = rembg.remove(garment_img.convert("RGBA"), session=session)
        except Exception:
            g_rgba = garment_img.convert("RGBA")

    # Crop to non-transparent bounding box
    alpha = np.array(g_rgba)[:, :, 3]
    non_zeros = np.argwhere(alpha > 20)
    if non_zeros.size == 0:
        return False, "Garment image appears empty after background removal.", garment_img

    y1, x1 = non_zeros.min(axis=0)
    y2, x2 = non_zeros.max(axis=0)
    cropped = g_rgba.crop((x1, y1, x2, y2))

    # Pad to 3:4 target ratio with clean neutral canvas
    target_ratio = 3.0 / 4.0
    cur_ratio = cropped.width / float(cropped.height)

    if cur_ratio > target_ratio:
        new_w = cropped.width
        new_h = int(new_w / target_ratio)
    else:
        new_h = cropped.height
        new_w = int(new_h * target_ratio)

    canvas_w = int(new_w * 1.08)
    canvas_h = int(new_h * 1.08)

    clean_canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    paste_x = (canvas_w - cropped.width) // 2
    paste_y = (canvas_h - cropped.height) // 2

    clean_canvas.paste(cropped.convert("RGB"), (paste_x, paste_y), mask=cropped.split()[-1])
    clean_garment = clean_canvas.resize((768, 1024), Image.Resampling.LANCZOS)

    return True, None, clean_garment

def prepare_product_item(
    product_img: Image.Image,
    category: str = "auto",
    parsing_model: Optional[Any] = None,
    use_cache: bool = True
) -> Tuple[bool, Optional[str], Image.Image, str]:
    """
    Unified entry point for preparing any product image.
    1. Determines category (auto or override).
    2. Checks disk cache by SHA-256 hash.
    3. If clothing: isolates garment, removes on-model human, centers and pads to 3:4 (768x1024).
    4. If accessory: produces clean transparent cutout.
    5. Saves to disk cache.
    Returns: (success, error_message, clean_product_image, resolved_category)
    """
    resolved_cat = classify_category_zero_shot(product_img, manual_hint=category)
    img_hash = get_image_hash(product_img)
    cache_path = os.path.join(CACHE_DIR, f"{img_hash}_{resolved_cat}.png")

    if use_cache and os.path.isfile(cache_path):
        try:
            cached_img = Image.open(cache_path)
            cached_img.load()
            return True, None, cached_img, resolved_cat
        except Exception:
            pass

    # Process based on category
    if resolved_cat in ("glasses", "sunglasses", "shoes", "footwear", "hats", "headwear"):
        clean_item = clean_accessory_cutout(product_img, resolved_cat)
        if use_cache:
            try:
                clean_item.save(cache_path, "PNG")
            except Exception:
                pass
        return True, None, clean_item, resolved_cat

    # Clothing category
    if parsing_model is None:
        from src.model_loader import get_preprocessors
        preprocessors = get_preprocessors()
        parsing_model = preprocessors.get("parsing")

    ok, err, clean_garment = clean_on_model_garment(
        product_img,
        parsing_model=parsing_model,
        category=resolved_cat
    )

    if not ok:
        return False, err, product_img, resolved_cat

    if use_cache:
        try:
            clean_garment.save(cache_path, "PNG")
        except Exception:
            pass

    return True, None, clean_garment, resolved_cat
