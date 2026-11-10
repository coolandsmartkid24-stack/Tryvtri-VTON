"""
Advanced Clothing Virtual Try-On Pipeline for IDM-VTON
Supports:
- Upper body: shirts, t-shirts, hoodies, jackets, coats, blazers
- Lower body: pants, trousers, jeans, shorts, skirts
- Dresses: long dresses, short/mini dresses, jumpsuits

Key Features:
1. Category-aware 3:4 aspect ratio crop & uncrop.
2. Adaptive mask extension matching the product's real length, width, and sleeves (coat vs tee, shorts vs trousers).
3. Anatomy protection (face, hair, hands, opposite body half strictly preserved).
4. Edge feathering (4-8px) and mandatory bit-exact background compositing:
   final = generated * feathered_mask + original * (1 - feathered_mask)
5. Central logo / graphic sharpness preservation.
"""

import os
import sys
import time
import math
import numpy as np
import cv2
from PIL import Image, ImageFilter, ImageOps
from typing import Dict, Any, Tuple, Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.product_cleaner import clean_on_model_garment

def compute_category_crop(
    person_img: Image.Image,
    keypoints: Optional[Dict[str, Any]],
    parse_mask: Any,
    category: str = "upper_body",
    product_subtype: str = "auto"
) -> Tuple[Image.Image, Tuple[int, int, int, int], float]:
    """
    Computes an optimal 3:4 aspect ratio crop of the person:
    - upper_body: from top of head/neck down to hips or mid-thigh.
    - lower_body: from waist/hips down to ankles/feet.
    - dresses: from neck/shoulders down to feet.
    Returns: (cropped_image_768x1024, (x1, y1, x2, y2), scale_factor)
    """
    orig_w, orig_h = person_img.size
    
    if isinstance(parse_mask, Image.Image):
        parse_mask = np.array(parse_mask)
    
    parse_h, parse_w = parse_mask.shape[:2]
    scale_y = orig_h / float(parse_h)
    scale_x = orig_w / float(parse_w)

    clean_cat = category.lower().replace("-", "_")

    if clean_cat in ("long_outerwear", "sherwani", "kurta", "long_coat"):
        # 1. Upper body & arms
        cloth_mask = np.isin(parse_resized, [4, 7, 8, 17]).astype(np.uint8) * 255
        arms_mask = np.isin(parse_resized, [14, 15]).astype(np.uint8) * 255
        base_mask = np.maximum(cloth_mask, arms_mask)

        # 2. Mask pants/shorts/thighs down to the knee (75% of legs)
        pants_mask = np.isin(parse_resized, [5, 6, 12, 13]).astype(np.uint8) * 255
        pants_indices = np.where(pants_mask > 0)
        if len(pants_indices[0]) > 0:
            knee_y = int(np.percentile(pants_indices[0], 75))
            thigh_mask = pants_mask.copy()
            thigh_mask[knee_y:, :] = 0
            base_mask = np.maximum(base_mask, thigh_mask)
        else:
            cloth_indices = np.where(cloth_mask > 0)
            if len(cloth_indices[0]) > 0:
                bot_y = int(np.percentile(cloth_indices[0], 98))
                base_mask[bot_y:min(H - 1, bot_y + 180), :] = 255

        # Dilation to cover placket, embroidery, mandarin collar & cuffs
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        dilated = cv2.dilate(base_mask, kernel, iterations=1)

        # Protect face & hair strictly
        protected = np.isin(parse_resized, [1, 2, 3, 11]).astype(np.uint8) * 255
        face_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        protected_dilated = cv2.dilate(protected, face_kernel, iterations=1)
        dilated[protected_dilated > 0] = 0

        # Protect calves, lower shins, feet & shoes below knee
        if len(pants_indices[0]) > 0:
            knee_cut = int(np.percentile(pants_indices[0], 75))
            dilated[knee_cut:, :] = 0

        # Protect hands / wrists
        arm_indices = np.where(arms_mask > 0)
        if len(arm_indices[0]) > 0:
            wrist_thresh = np.percentile(arm_indices[0], 92)
            hand_region = (arms_mask > 0) & (np.arange(H)[:, None] > wrist_thresh)
            dilated[hand_region] = 0

    elif clean_cat in ("upper_body", "tops"):
        # Torso labels: 4=upperclothes, 7=dress, 14=left_arm, 15=right_arm
        torso_rows = np.where(np.isin(parse_mask, [4, 7, 14, 15]))[0]
        face_rows = np.where(parse_mask == 11)[0]
        pants_rows = np.where(np.isin(parse_mask, [5, 6]))[0]

        if len(torso_rows) > 0:
            top_y = int(min(torso_rows) * scale_y)
            bot_y = int(max(torso_rows) * scale_y)
        else:
            top_y = int(orig_h * 0.15)
            bot_y = int(orig_h * 0.65)

        if len(face_rows) > 0:
            head_top_y = int(min(face_rows) * scale_y)
        else:
            head_top_y = int(top_y * 0.5)

        # Crop starts from head top (with small margin)
        crop_top = max(0, head_top_y - int(orig_h * 0.05))
        
        # Bottom of crop: coats extend down to mid-thigh / knee; tees stop at hips
        is_coat = product_subtype in ("coat", "long_coat", "trench_coat", "jacket")
        extra_down = 0.25 if is_coat else 0.18

        if len(pants_rows) > 0:
            hip_y = int(min(pants_rows) * scale_y)
            crop_bot = min(orig_h, max(bot_y, hip_y) + int(orig_h * extra_down))
        else:
            crop_bot = min(orig_h, bot_y + int(orig_h * extra_down))

    elif clean_cat in ("lower_body", "bottoms"):
        pants_rows = np.where(np.isin(parse_mask, [5, 6, 12, 13]))[0]
        if len(pants_rows) > 0:
            top_y = int(min(pants_rows) * scale_y)
            bot_y = int(max(pants_rows) * scale_y)
        else:
            top_y = int(orig_h * 0.45)
            bot_y = orig_h

        crop_top = max(0, top_y - int(orig_h * 0.08)) # include waist & belt
        crop_bot = orig_h

    else: # dresses
        torso_rows = np.where(np.isin(parse_mask, [4, 7]))[0]
        face_rows = np.where(parse_mask == 11)[0]
        if len(face_rows) > 0:
            crop_top = max(0, int(min(face_rows) * scale_y) - int(orig_h * 0.04))
        elif len(torso_rows) > 0:
            crop_top = max(0, int(min(torso_rows) * scale_y) - int(orig_h * 0.08))
        else:
            crop_top = int(orig_h * 0.10)
        crop_bot = orig_h

    # Ensure 3:4 aspect ratio
    crop_h = crop_bot - crop_top
    required_w = int(crop_h * (3.0 / 4.0))

    # Center horizontally around person
    center_x = orig_w // 2
    crop_x1 = max(0, center_x - required_w // 2)
    crop_x2 = min(orig_w, crop_x1 + required_w)

    # Adjust boundary overflow
    if crop_x2 - crop_x1 < required_w:
        crop_x1 = max(0, crop_x2 - required_w)

    actual_w = crop_x2 - crop_x1
    required_h = int(actual_w * (4.0 / 3.0))
    if required_h <= orig_h:
        crop_h = required_h
        crop_bot = min(orig_h, crop_top + crop_h)
        if crop_bot - crop_top < required_h:
            crop_top = max(0, crop_bot - required_h)

    crop_box = (crop_x1, crop_top, crop_x2, crop_bot)
    cropped_img = person_img.crop(crop_box).resize((768, 1024), Image.Resampling.LANCZOS)
    return cropped_img, crop_box, 1.0

def build_adaptive_garment_mask(
    parse_mask: Any,
    target_size: Tuple[int, int] = (1024, 768),
    category: str = "upper_body",
    garment_aspect_ratio: float = 1.0,
    product_subtype: str = "auto"
) -> Tuple[Image.Image, np.ndarray]:
    """
    Builds enhanced inpainting mask tailored for the NEW product:
    1. Masks old clothing item.
    2. Extends dynamically to product's real length:
       - Coats/jackets: extends down across waistband/hips to mid-thigh.
       - Shorts: restricts mask to mid-thigh, keeping lower legs untouched.
       - Trousers/jeans: masks down to ankles, protecting shoes.
       - Long dresses: masks down to mid-calf/ankles.
       - Short/mini dresses: masks down to mid-thigh.
    3. Strictly protects anatomy: face, hair, hands, and untouched body half.
    4. Feathers edges by 6 pixels for seamless alpha blending.
    """
    if isinstance(parse_mask, Image.Image):
        parse_mask = np.array(parse_mask)
    H, W = target_size
    parse_resized = cv2.resize(parse_mask, (W, H), interpolation=cv2.INTER_NEAREST)

    clean_cat = category.lower().replace("-", "_")

    if clean_cat in ("long_outerwear", "sherwani", "kurta", "long_coat"):
        # 1. Upper body & arms
        cloth_mask = np.isin(parse_resized, [4, 7, 8, 17]).astype(np.uint8) * 255
        arms_mask = np.isin(parse_resized, [14, 15]).astype(np.uint8) * 255
        base_mask = np.maximum(cloth_mask, arms_mask)

        # 2. Mask pants/shorts/thighs down to the knee (75% of legs)
        pants_mask = np.isin(parse_resized, [5, 6, 12, 13]).astype(np.uint8) * 255
        pants_indices = np.where(pants_mask > 0)
        if len(pants_indices[0]) > 0:
            knee_y = int(np.percentile(pants_indices[0], 75))
            thigh_mask = pants_mask.copy()
            thigh_mask[knee_y:, :] = 0
            base_mask = np.maximum(base_mask, thigh_mask)
        else:
            cloth_indices = np.where(cloth_mask > 0)
            if len(cloth_indices[0]) > 0:
                bot_y = int(np.percentile(cloth_indices[0], 98))
                base_mask[bot_y:min(H - 1, bot_y + 180), :] = 255

        # Dilation to cover placket, embroidery, mandarin collar & cuffs
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        dilated = cv2.dilate(base_mask, kernel, iterations=1)

        # Protect face & hair strictly
        protected = np.isin(parse_resized, [1, 2, 3, 11]).astype(np.uint8) * 255
        face_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        protected_dilated = cv2.dilate(protected, face_kernel, iterations=1)
        dilated[protected_dilated > 0] = 0

        # Protect calves, lower shins, feet & shoes below knee
        if len(pants_indices[0]) > 0:
            knee_cut = int(np.percentile(pants_indices[0], 75))
            dilated[knee_cut:, :] = 0

        # Protect hands / wrists
        arm_indices = np.where(arms_mask > 0)
        if len(arm_indices[0]) > 0:
            wrist_thresh = np.percentile(arm_indices[0], 92)
            hand_region = (arms_mask > 0) & (np.arange(H)[:, None] > wrist_thresh)
            dilated[hand_region] = 0

    elif clean_cat in ("upper_body", "tops"):
        # 4=upper_clothes, 7=dress, 8=belt, 17=scarf
        cloth_mask = np.isin(parse_resized, [4, 7, 8, 17]).astype(np.uint8) * 255
        # Arms: 14=left_arm, 15=right_arm
        arms_mask = np.isin(parse_resized, [14, 15]).astype(np.uint8) * 255
        base_mask = np.maximum(cloth_mask, arms_mask)

        # Extend hem downwards based on product type
        cloth_indices = np.where(cloth_mask > 0)
        if len(cloth_indices[0]) > 0:
            bot_y = int(np.percentile(cloth_indices[0], 98))
            
            # Extension distance:
            # For coats: +120px; for hoodies/jackets: +60px; for tees: +35px
            is_coat = product_subtype in ("coat", "long_coat", "jacket")
            if is_coat:
                ext_distance = int(110 * max(1.0, garment_aspect_ratio))
            else:
                ext_distance = int(45 * max(1.0, garment_aspect_ratio))
            
            cloth_cols = cloth_indices[1]
            min_x = max(0, int(np.percentile(cloth_cols, 2)) - 10)
            max_x = min(W, int(np.percentile(cloth_cols, 98)) + 10)
            ext_y2 = min(H - 1, bot_y + ext_distance)
            
            hem_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 25))
            extended_region = cv2.dilate(cloth_mask[bot_y - 20:ext_y2, min_x:max_x], hem_kernel)
            base_mask[bot_y - 20:ext_y2, min_x:max_x] = np.maximum(
                base_mask[bot_y - 20:ext_y2, min_x:max_x],
                extended_region
            )

        # Dilation to cover collars and cuffs
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        dilated = cv2.dilate(base_mask, kernel, iterations=1)

        # Protect face & hair
        protected = np.isin(parse_resized, [1, 2, 3, 11]).astype(np.uint8) * 255
        face_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        protected_dilated = cv2.dilate(protected, face_kernel, iterations=1)
        dilated[protected_dilated > 0] = 0

        # Protect hands / wrists
        if len(cloth_indices[0]) > 0:
            arm_indices = np.where(arms_mask > 0)
            if len(arm_indices[0]) > 0:
                wrist_thresh = np.percentile(arm_indices[0], 91)
                hand_region = (arms_mask > 0) & (np.arange(H)[:, None] > wrist_thresh)
                dilated[hand_region] = 0

        # Protect pants below upper thigh (keep pants and shoes intact!)
        pants_mask = np.isin(parse_resized, [5, 6]).astype(np.uint8) * 255
        pants_indices = np.where(pants_mask > 0)
        if len(pants_indices[0]) > 0:
            # If coat, allow down to 55% of pants; otherwise 30% of pants
            pants_protect_pct = 55 if product_subtype in ("coat", "long_coat") else 30
            cut_line = np.percentile(pants_indices[0], pants_protect_pct)
            dilated[int(cut_line):, :] = 0

    elif clean_cat in ("lower_body", "bottoms"):
        is_shorts = product_subtype in ("shorts", "short")
        is_skirt = product_subtype in ("skirt", "mini_skirt")

        if is_shorts:
            # Shorts: mask waist, hips, upper thighs only; leave knees, calves, ankles untouched!
            cloth_mask = np.isin(parse_resized, [5, 6, 8]).astype(np.uint8) * 255
            # Find knees / lower legs
            leg_indices = np.where(cloth_mask > 0)
            if len(leg_indices[0]) > 0:
                thigh_cut = np.percentile(leg_indices[0], 45)
                cloth_mask[int(thigh_cut):, :] = 0
        else:
            # Pants / jeans / trousers
            cloth_mask = np.isin(parse_resized, [5, 6, 8, 12, 13]).astype(np.uint8) * 255
        
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        dilated = cv2.dilate(cloth_mask, kernel, iterations=1)
        
        # Protect upper clothes, arms, chest, face
        upper_protect = np.isin(parse_resized, [4, 7, 11, 14, 15]).astype(np.uint8) * 255
        upper_protect_indices = np.where(upper_protect > 0)
        if len(upper_protect_indices[0]) > 0:
            # Allow 15px waist overlap
            upper_protect[int(np.percentile(upper_protect_indices[0], 95)):, :] = 0
        dilated[upper_protect > 0] = 0

        # Protect shoes / feet: 9, 10, 18, 19
        shoes_protect = np.isin(parse_resized, [9, 10, 18, 19]).astype(np.uint8) * 255
        shoe_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        shoes_dilated = cv2.dilate(shoes_protect, shoe_kernel, iterations=1)
        dilated[shoes_dilated > 0] = 0

    else: # dresses
        is_short_dress = product_subtype in ("short_dress", "mini_dress")
        if is_short_dress:
            cloth_mask = np.isin(parse_resized, [4, 7, 8, 14, 15, 17]).astype(np.uint8) * 255
            # Include upper thighs
            lower_legs = np.isin(parse_resized, [12, 13]).astype(np.uint8) * 255
            leg_indices = np.where(lower_legs > 0)
            if len(leg_indices[0]) > 0:
                mid_thigh = np.percentile(leg_indices[0], 40)
                cloth_mask[lower_legs > 0] = 0
                cloth_mask[:int(mid_thigh), :] = np.maximum(cloth_mask[:int(mid_thigh), :], lower_legs[:int(mid_thigh), :])
        else:
            cloth_mask = np.isin(parse_resized, [4, 5, 6, 7, 8, 12, 13, 14, 15, 17]).astype(np.uint8) * 255
        
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        dilated = cv2.dilate(cloth_mask, kernel, iterations=1)
        face_hair = np.isin(parse_resized, [1, 2, 3, 11]).astype(np.uint8) * 255
        dilated[face_hair > 0] = 0

    # Smooth & feather edges (6px Gaussian blur for seamless alpha blending)
    blurred_mask = cv2.GaussianBlur(dilated.astype(np.float32) / 255.0, (13, 13), 3.0)
    blurred_mask = np.clip(blurred_mask, 0.0, 1.0)
    
    pil_mask = Image.fromarray((blurred_mask * 255).astype(np.uint8), mode="L")
    return pil_mask, blurred_mask

def mandatory_composite(
    generated_img: Image.Image,
    original_img: Image.Image,
    feathered_mask: np.ndarray,
    crop_box: Optional[Tuple[int, int, int, int]] = None
) -> Image.Image:
    """
    Guarantees mathematical pixel-perfection outside the try-on mask:
    final = generated * mask + original * (1 - mask)
    Pastes the blended crop back into original_img at native resolution!
    """
    gen_np = np.array(generated_img, dtype=np.float32)

    if crop_box is not None:
        x1, y1, x2, y2 = crop_box
        box_w = x2 - x1
        box_h = y2 - y1
        
        gen_resized = cv2.resize(gen_np, (box_w, box_h), interpolation=cv2.INTER_LANCZOS4)
        mask_resized = cv2.resize(feathered_mask, (box_w, box_h), interpolation=cv2.INTER_LINEAR)
        if mask_resized.ndim == 2:
            mask_resized = mask_resized[:, :, np.newaxis]

        orig_full = np.array(original_img, dtype=np.float32)
        orig_patch = orig_full[y1:y2, x1:x2]

        gen_harmonized = color_harmonize(gen_resized, orig_patch, mask_resized)
        blended_patch = gen_harmonized * mask_resized + orig_patch * (1.0 - mask_resized)
        
        final_full = orig_full.copy()
        final_full[y1:y2, x1:x2] = blended_patch
        return Image.fromarray(np.clip(final_full, 0, 255).astype(np.uint8))
    else:
        orig_np = np.array(original_img.resize(generated_img.size), dtype=np.float32)
        mask_3d = feathered_mask[:, :, np.newaxis] if feathered_mask.ndim == 2 else feathered_mask
        gen_harmonized = color_harmonize(gen_np, orig_np, mask_3d)
        blended = gen_harmonized * mask_3d + orig_np * (1.0 - mask_3d)
        return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8))

def color_harmonize(
    generated: np.ndarray,
    original: np.ndarray,
    mask: np.ndarray
) -> np.ndarray:
    """
    Light color transfer to harmonize generated clothing with original scene lighting:
    Subtly aligns ambient luminance without altering the garment's core hue.
    """
    try:
        gen_lab = cv2.cvtColor(np.clip(generated, 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
        orig_lab = cv2.cvtColor(np.clip(original, 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)

        boundary_mask = ((mask > 0.05) & (mask < 0.95)).squeeze()
        if np.sum(boundary_mask) > 100:
            l_orig_mean = np.mean(orig_lab[boundary_mask, 0])
            l_gen_mean = np.mean(gen_lab[boundary_mask, 0])
            diff = np.clip(l_orig_mean - l_gen_mean, -20, 20) * 0.35
            gen_lab[:, :, 0] = np.clip(gen_lab[:, :, 0] + diff, 0, 255)
            harmonized = cv2.cvtColor(gen_lab.astype(np.uint8), cv2.COLOR_LAB2RGB).astype(np.float32)
            return harmonized
    except Exception:
        pass
    return generated

def preserve_garment_logo(
    generated_img: Image.Image,
    garment_clean: Image.Image,
    keypoints: Optional[Dict[str, Any]] = None
) -> Image.Image:
    """
    Preserves central chest logo / graphic sharpness from the reference garment.
    Extracts high-frequency Laplacian details from reference print and injects onto chest.
    """
    try:
        g_np = np.array(garment_clean.resize((768, 1024)))
        res_np = np.array(generated_img.resize((768, 1024)), dtype=np.float32)

        H, W = 1024, 768
        chest_y1, chest_y2 = int(0.28 * H), int(0.56 * H)
        chest_x1, chest_x2 = int(0.25 * W), int(0.75 * W)

        logo_patch = g_np[chest_y1:chest_y2, chest_x1:chest_x2]
        gray_patch = cv2.cvtColor(logo_patch, cv2.COLOR_RGB2GRAY)
        laplacian = cv2.Laplacian(gray_patch, cv2.CV_32F)
        var_lap = laplacian.var()

        if var_lap > 110:
            blur_patch = cv2.GaussianBlur(logo_patch.astype(np.float32), (9, 9), 2.0)
            high_freq = logo_patch.astype(np.float32) - blur_patch
            target_patch = res_np[chest_y1:chest_y2, chest_x1:chest_x2]
            enhanced_patch = target_patch + high_freq * 0.35
            res_np[chest_y1:chest_y2, chest_x1:chest_x2] = np.clip(enhanced_patch, 0, 255)
            return Image.fromarray(res_np.astype(np.uint8))
    except Exception:
        pass
    return generated_img
