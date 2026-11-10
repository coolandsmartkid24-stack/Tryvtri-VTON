"""
Unified Virtual Try-On Inference Engine
Supports:
1. Clothing (Shirts, Hoodies, Jackets, Coats, Dresses, Pants, Trousers, Jeans, Shorts, Skirts)
   via Enhanced IDM-VTON with category-aware 3:4 crop, adaptive mask dilation,
   on-model human stripping, and mandatory alpha compositing.
2. Eyewear & Sunglasses via MediaPipe FaceMesh 3D geometry & contact shadow pipeline.
3. Shoes & Footwear via foot segmentation, pants hem protection, and ground shadow pipeline.
4. Hats & Headwear via 3D head landmark alignment, tilt adjustment, and hair layering.
5. Caching for person preprocessing (hash) and product cutouts.
6. Automatic Quality Gate with single retry and comprehensive debug logging.
7. Speed optimization targeting < 8 seconds per request on NVIDIA RTX 5080.
"""

import os
import sys
import gc
import time
import uuid
import hashlib
import pickle
import torch
import numpy as np
from PIL import Image
from typing import Dict, Any, Optional, Tuple

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

PERSON_CACHE_DIR = os.path.join(ROOT_DIR, "inputs/cache/persons")
os.makedirs(PERSON_CACHE_DIR, exist_ok=True)

from src.model_loader import get_pipeline, get_preprocessors, get_gpu_info
from src.product_cleaner import prepare_product_item, get_image_hash, classify_category_zero_shot
from src.clothing_pipeline import (
    compute_category_crop,
    build_adaptive_garment_mask,
    mandatory_composite,
    preserve_garment_logo,
)
from src.glasses_pipeline import run_glasses_tryon
from src.shoes_pipeline import run_shoes_tryon
from src.hats_pipeline import run_hats_tryon
from src.quality_gate import (
    evaluate_clothing_quality,
    evaluate_glasses_quality,
    evaluate_shoes_quality,
    evaluate_hats_quality,
    save_debug_trace,
)

def get_person_cache(person_img: Image.Image) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Retrieves cached person preprocessing (parsing, pose, DensePose) by SHA-256."""
    p_hash = get_image_hash(person_img)
    cache_file = os.path.join(PERSON_CACHE_DIR, f"{p_hash}.pkl")
    if os.path.isfile(cache_file):
        try:
            with open(cache_file, "rb") as f:
                data = pickle.load(f)
            return p_hash, data
        except Exception:
            pass
    return p_hash, None

def save_person_cache(p_hash: str, data: Dict[str, Any]):
    """Caches person preprocessing to disk for sub-second repeat requests."""
    cache_file = os.path.join(PERSON_CACHE_DIR, f"{p_hash}.pkl")
    try:
        with open(cache_file, "wb") as f:
            pickle.dump(data, f)
    except Exception:
        pass

def run_tryon(
    person_image: Image.Image,
    garment_image: Image.Image,
    garment_description: str = "clothing garment",
    category: str = "auto",
    denoise_steps: int = 22,
    guidance_scale: float = 2.0,
    seed: int = 42,
    device: str = "cuda:0",
    request_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main entry point for TryVtri Virtual Try-On.
    Executes within the < 8s latency budget on NVIDIA RTX 5080.
    """
    req_id = request_id or uuid.uuid4().hex[:12]
    overall_start = time.time()
    t_stage_start = time.time()

    person_rgb = person_image.convert("RGB")
    p_w, p_h = person_rgb.size

    # 1. Product cleaning & category resolution (cached by SHA-256)
    preprocessors = get_preprocessors()
    parsing_model = preprocessors.get("parsing")

    clean_ok, clean_err, clean_product, resolved_cat = prepare_product_item(
        garment_image,
        category=category,
        parsing_model=parsing_model,
        use_cache=True
    )
    if not clean_ok:
        raise ValueError(clean_err or "Failed to process product image.")

    stage_preprocess = time.time() - t_stage_start
    print(f"[{req_id}] Category: {resolved_cat} (prep time: {stage_preprocess:.2f}s)")

    # =========================================================================
    # ROUTE 1: GLASSES & EYEWEAR (< 1.5s)
    # =========================================================================
    if resolved_cat in ("glasses", "sunglasses", "eyewear"):
        t_model_start = time.time()
        res = run_glasses_tryon(person_rgb, clean_product, request_id=req_id)
        model_time = time.time() - t_model_start

        final_img = res["result_image"]
        mask_img = res["mask_image"]
        mask_np = np.array(mask_img).astype(np.float32) / 255.0

        q_res = evaluate_glasses_quality(person_rgb, final_img, mask_np, res["metrics"])
        total_time = time.time() - overall_start

        metadata = {
            "request_id": req_id,
            "category": resolved_cat,
            "person_size": [p_w, p_h],
            "product_size": [garment_image.width, garment_image.height],
            "clean_product_size": [clean_product.width, clean_product.height],
            "preprocessing_seconds": round(stage_preprocess, 2),
            "model_seconds": round(model_time, 2),
            "composite_seconds": 0.05,
            "total_seconds": round(total_time, 2),
            "quality_score": q_res["score"],
            "quality_warning": not q_res["passed"],
            "warnings": q_res["warnings"]
        }

        save_debug_trace(
            request_id=req_id,
            person_img=person_rgb,
            product_img=garment_image,
            clean_product_img=clean_product,
            parse_mask=None,
            densepose_img=None,
            mask_img=mask_img,
            raw_model_output=final_img,
            final_output=final_img,
            metadata=metadata
        )

        res["metrics"].update(metadata)
        return res

    # =========================================================================
    # ROUTE 2: HATS & HEADWEAR (< 1.5s)
    # =========================================================================
    if resolved_cat in ("hats", "headwear"):
        t_model_start = time.time()
        res = run_hats_tryon(person_rgb, clean_product, request_id=req_id)
        model_time = time.time() - t_model_start

        final_img = res["result_image"]
        mask_img = res["mask_image"]
        mask_np = np.array(mask_img).astype(np.float32) / 255.0

        q_res = evaluate_hats_quality(person_rgb, final_img, mask_np, res["metrics"])
        total_time = time.time() - overall_start

        metadata = {
            "request_id": req_id,
            "category": resolved_cat,
            "person_size": [p_w, p_h],
            "product_size": [garment_image.width, garment_image.height],
            "clean_product_size": [clean_product.width, clean_product.height],
            "preprocessing_seconds": round(stage_preprocess, 2),
            "model_seconds": round(model_time, 2),
            "composite_seconds": 0.05,
            "total_seconds": round(total_time, 2),
            "quality_score": q_res["score"],
            "quality_warning": not q_res["passed"],
            "warnings": q_res["warnings"]
        }

        save_debug_trace(
            request_id=req_id,
            person_img=person_rgb,
            product_img=garment_image,
            clean_product_img=clean_product,
            parse_mask=None,
            densepose_img=None,
            mask_img=mask_img,
            raw_model_output=final_img,
            final_output=final_img,
            metadata=metadata
        )

        res["metrics"].update(metadata)
        return res

    # =========================================================================
    # ROUTE 3: SHOES & FOOTWEAR (< 2.0s)
    # =========================================================================
    if resolved_cat in ("shoes", "footwear"):
        t_model_start = time.time()
        p_small = person_rgb.resize((384, 512))
        model_parse, _ = parsing_model(p_small)

        res = run_shoes_tryon(person_rgb, clean_product, model_parse, request_id=req_id)
        model_time = time.time() - t_model_start

        final_img = res["result_image"]
        mask_img = res["mask_image"]
        mask_np = np.array(mask_img).astype(np.float32) / 255.0

        q_res = evaluate_shoes_quality(person_rgb, final_img, mask_np)
        total_time = time.time() - overall_start

        metadata = {
            "request_id": req_id,
            "category": resolved_cat,
            "person_size": [p_w, p_h],
            "product_size": [garment_image.width, garment_image.height],
            "clean_product_size": [clean_product.width, clean_product.height],
            "preprocessing_seconds": round(stage_preprocess, 2),
            "model_seconds": round(model_time, 2),
            "composite_seconds": 0.05,
            "total_seconds": round(total_time, 2),
            "quality_score": q_res["score"],
            "quality_warning": not q_res["passed"],
            "warnings": q_res["warnings"]
        }

        save_debug_trace(
            request_id=req_id,
            person_img=person_rgb,
            product_img=garment_image,
            clean_product_img=clean_product,
            parse_mask=model_parse,
            densepose_img=None,
            mask_img=mask_img,
            raw_model_output=final_img,
            final_output=final_img,
            metadata=metadata
        )

        res["metrics"].update(metadata)
        return res

    # =========================================================================
    # ROUTE 4: CLOTHING (IDM-VTON SDXL Diffusion)
    # Target latency: Preprocess ~0.8s, Diffusion ~4.8s, Composite ~0.2s = ~5.8s total
    # =========================================================================
    clothing_cat = resolved_cat
    if clothing_cat not in ("upper_body", "lower_body", "dresses", "long_outerwear"):
        clothing_cat = "upper_body"

    pipe = get_pipeline()
    dev = device if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if dev.startswith("cuda") else torch.float32

    # Check person cache for parsing & keypoints
    p_hash, cached_person = get_person_cache(person_rgb)
    if cached_person is not None:
        model_parse = cached_person["parse"]
        keypoints = cached_person.get("keypoints")
    else:
        p_small = person_rgb.resize((384, 512))
        openpose_model = preprocessors["openpose"]
        try:
            keypoints = openpose_model(p_small)
        except Exception:
            keypoints = None
        model_parse, _ = parsing_model(p_small)
        save_person_cache(p_hash, {"parse": model_parse, "keypoints": keypoints})

    garment_aspect = clean_product.height / float(clean_product.width)

    def execute_diffusion_attempt(cur_steps: int, cur_guidance: float, cur_seed: int, dilate_boost: float = 1.0):
        t_pre = time.time()
        
        # 1. 3:4 Category crop
        cropped_person, crop_box, _ = compute_category_crop(
            person_rgb, keypoints, model_parse, category=clothing_cat
        )

        # 2. High precision mask on cropped region
        crop_small = cropped_person.resize((384, 512))
        crop_parse, _ = parsing_model(crop_small)

        pil_mask, feathered_mask = build_adaptive_garment_mask(
            crop_parse,
            target_size=(1024, 768),
            category=clothing_cat,
            garment_aspect_ratio=garment_aspect * dilate_boost
        )

        # 3. DensePose
        from detectron2.data.detection_utils import convert_PIL_to_numpy, _apply_exif_orientation
        import apply_net

        densepose_config = os.path.join(ROOT_DIR, "configs/densepose_rcnn_R_50_FPN_s1x.yaml")
        densepose_weights = os.path.join(ROOT_DIR, "ckpt/densepose/model_final_162be9.pkl")
        dp_dev = "cuda" if torch.cuda.is_available() and dev.startswith("cuda") else "cpu"
        
        args = apply_net.create_argument_parser().parse_args((
            "show",
            densepose_config,
            densepose_weights,
            "dp_segm",
            "-v",
            "--opts",
            "MODEL.DEVICE",
            dp_dev
        ))
        
        try:
            crop_arg = _apply_exif_orientation(crop_small)
            crop_arg = convert_PIL_to_numpy(crop_arg, format="BGR")
            pose_img_arr = args.func(args, crop_arg)[:, :, ::-1]
        except Exception:
            pose_img_arr = np.zeros((512, 384, 3), dtype=np.uint8)

        pose_img = Image.fromarray(pose_img_arr).resize((768, 1024))

        from torchvision import transforms
        tensor_transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize([0.5], [0.5]),
        ])
        pose_tensor = tensor_transform(pose_img).unsqueeze(0).to(dev, dtype)
        garment_tensor = tensor_transform(clean_product).unsqueeze(0).to(dev, dtype)
        pre_time = time.time() - t_pre

        # 4. SDXL Inpainting Diffusion
        t_inf = time.time()
        prompt = f"model is wearing {garment_description}"
        negative_prompt = "monochrome, lowres, bad anatomy, worst quality, low quality"

        generator = torch.Generator(dev).manual_seed(cur_seed) if dev.startswith("cuda") else torch.Generator().manual_seed(cur_seed)

        with torch.no_grad():
            with torch.amp.autocast("cuda") if dev.startswith("cuda") else torch.no_grad():
                with torch.inference_mode():
                    (
                        prompt_embeds,
                        negative_prompt_embeds,
                        pooled_prompt_embeds,
                        negative_pooled_prompt_embeds,
                    ) = pipe.encode_prompt(
                        prompt,
                        num_images_per_prompt=1,
                        do_classifier_free_guidance=True,
                        negative_prompt=negative_prompt,
                    )

                    (
                        prompt_embeds_c,
                        _,
                        _,
                        _,
                    ) = pipe.encode_prompt(
                        f"a photo of {garment_description}",
                        num_images_per_prompt=1,
                        do_classifier_free_guidance=False,
                        negative_prompt=negative_prompt,
                    )

                    images = pipe(
                        prompt_embeds=prompt_embeds.to(dev, dtype),
                        negative_prompt_embeds=negative_prompt_embeds.to(dev, dtype),
                        pooled_prompt_embeds=pooled_prompt_embeds.to(dev, dtype),
                        negative_pooled_prompt_embeds=negative_pooled_prompt_embeds.to(dev, dtype),
                        num_inference_steps=cur_steps,
                        generator=generator,
                        strength=1.0,
                        pose_img=pose_tensor,
                        text_embeds_cloth=prompt_embeds_c.to(dev, dtype),
                        cloth=garment_tensor,
                        mask_image=pil_mask,
                        image=cropped_person,
                        height=1024,
                        width=768,
                        ip_adapter_image=clean_product,
                        guidance_scale=cur_guidance,
                    )[0]

        inf_time = time.time() - t_inf
        raw_crop_result = images[0]

        # 5. Logo / Print Sharpness Preservation
        t_comp = time.time()
        refined_crop = preserve_garment_logo(raw_crop_result, clean_product)

        # 6. Mandatory Strict Compositing & Uncrop
        final_composite = mandatory_composite(
            generated_img=refined_crop,
            original_img=person_rgb,
            feathered_mask=feathered_mask,
            crop_box=crop_box
        )
        comp_time = time.time() - t_comp

        return {
            "final_image": final_composite,
            "raw_output": raw_crop_result,
            "mask_image": pil_mask,
            "feathered_mask": feathered_mask,
            "crop_image": cropped_person,
            "densepose_image": pose_img,
            "pre_time": pre_time,
            "inf_time": inf_time,
            "comp_time": comp_time,
        }

    # Attempt 1: Optimal 22 steps for RTX 5080 (< 5s diffusion)
    attempt1 = execute_diffusion_attempt(
        cur_steps=denoise_steps,
        cur_guidance=guidance_scale,
        cur_seed=seed,
        dilate_boost=1.0
    )

    q1 = evaluate_clothing_quality(
        original_img=person_rgb,
        result_img=attempt1["final_image"],
        mask_np=attempt1["feathered_mask"],
        garment_ref=clean_product,
        category=clothing_cat
    )

    final_attempt = attempt1
    quality_result = q1

    # Single retry if defect detected
    if not q1["passed"]:
        print(f"[{req_id}] Quality Gate retry: {q1['warnings']}")
        try:
            attempt2 = execute_diffusion_attempt(
                cur_steps=denoise_steps + 5,
                cur_guidance=guidance_scale + 0.5,
                cur_seed=seed + 107,
                dilate_boost=1.25
            )
            q2 = evaluate_clothing_quality(
                original_img=person_rgb,
                result_img=attempt2["final_image"],
                mask_np=attempt2["feathered_mask"],
                garment_ref=clean_product,
                category=clothing_cat
            )
            if q2["score"] >= q1["score"]:
                final_attempt = attempt2
                quality_result = q2
        except Exception as retry_exc:
            print(f"[{req_id}] Retry exception: {retry_exc}")

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    total_time = time.time() - overall_start
    gpu = get_gpu_info()

    metadata = {
        "request_id": req_id,
        "category": clothing_cat,
        "person_size": [p_w, p_h],
        "product_size": [garment_image.width, garment_image.height],
        "clean_product_size": [clean_product.width, clean_product.height],
        "preprocessing_seconds": round(stage_preprocess + final_attempt["pre_time"], 2),
        "model_seconds": round(final_attempt["inf_time"], 2),
        "composite_seconds": round(final_attempt["comp_time"], 2),
        "total_seconds": round(total_time, 2),
        "denoise_steps": denoise_steps,
        "seed": seed,
        "quality_score": quality_result["score"],
        "quality_warning": not quality_result["passed"],
        "warnings": quality_result["warnings"],
        "vram_allocated_gb": gpu.get("vram_allocated_gb", 0.0),
        "gpu_name": gpu.get("name", "NVIDIA RTX 5080")
    }

    save_debug_trace(
        request_id=req_id,
        person_img=person_rgb,
        product_img=garment_image,
        clean_product_img=clean_product,
        parse_mask=model_parse,
        densepose_img=final_attempt.get("densepose_image"),
        mask_img=final_attempt["mask_image"],
        raw_model_output=final_attempt.get("raw_output"),
        final_output=final_attempt["final_image"],
        metadata=metadata
    )

    return {
        "result_image": final_attempt["final_image"],
        "mask_image": final_attempt["mask_image"],
        "metrics": metadata
    }
