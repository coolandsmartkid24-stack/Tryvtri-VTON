"""
Automated Image Preprocessing Pipeline for IDM-VTON
Extracts OpenPose keypoints, ATR/LIP human body parsing, DensePose segmentation,
and computes high-definition agnostic try-on masks automatically without manual painting.
"""

import os
import sys
import time
import torch
import numpy as np
from PIL import Image
from typing import Dict, Any, Tuple
from torchvision import transforms
from torchvision.transforms.functional import to_pil_image

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
demo_dir = os.path.join(ROOT_DIR, "gradio_demo")
if os.path.exists(demo_dir) and demo_dir not in sys.path:
    sys.path.insert(0, demo_dir)

from detectron2.data.detection_utils import convert_PIL_to_numpy, _apply_exif_orientation
import apply_net
from utils_mask import get_mask_location

_TENSOR_TRANSFORM = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize([0.5], [0.5]),
])

def preprocess_person(
    person_image: Image.Image,
    category: str = "upper_body",
    preprocessors: Dict[str, Any] = None,
    densepose_config: str = None,
    densepose_weights: str = None,
    target_size: Tuple[int, int] = (768, 1024),
    device: str = "cuda"
) -> Dict[str, Any]:
    """
    Executes full automatic preprocessing pipeline on a human model image:
    1. Resizing to target resolution (768x1024).
    2. Extracting OpenPose pose joints.
    3. Parsing human anatomical parts (ATR & LIP ONNX models).
    4. Generating category-specific agnostic mask (upper_body, lower_body, dresses).
    5. DensePose surface geometry inference.
    """
    t0 = time.time()
    
    if densepose_config is None:
        densepose_config = os.path.join(ROOT_DIR, "configs/densepose_rcnn_R_50_FPN_s1x.yaml")
    if densepose_weights is None:
        densepose_weights = os.path.join(ROOT_DIR, "ckpt/densepose/model_final_162be9.pkl")

    # 1. Normalize image
    person_full = person_image.convert("RGB").resize(target_size)
    person_small = person_full.resize((384, 512))
    
    # 2. Extract OpenPose Keypoints
    openpose_model = preprocessors["openpose"]
    keypoints = openpose_model(person_small)
    
    # 3. Human Body Parsing
    parsing_model = preprocessors["parsing"]
    model_parse, _ = parsing_model(person_small)
    
    # 4. Agnostic Mask Generation (HD, category-aware)
    mask, mask_gray = get_mask_location("hd", category, model_parse, keypoints)
    mask = mask.resize(target_size)
    
    # 5. DensePose Surface Geometry
    human_arg = _apply_exif_orientation(person_small)
    human_arg = convert_PIL_to_numpy(human_arg, format="BGR")
    
    dev_arg = "cuda" if torch.cuda.is_available() and device.startswith("cuda") else "cpu"
    args = apply_net.create_argument_parser().parse_args((
        "show",
        densepose_config,
        densepose_weights,
        "dp_segm",
        "-v",
        "--opts",
        "MODEL.DEVICE",
        dev_arg
    ))
    pose_img_arr = args.func(args, human_arg)[:, :, ::-1]
    pose_img = Image.fromarray(pose_img_arr).resize(target_size)
    
    # Transform pose into normalized tensor
    pose_tensor = _TENSOR_TRANSFORM(pose_img).unsqueeze(0).to(dev_arg, torch.float16 if dev_arg.startswith("cuda") else torch.float32)
    
    elapsed = time.time() - t0
    return {
        "person_image": person_full,
        "mask_image": mask,
        "mask_gray": mask_gray,
        "pose_image": pose_img,
        "pose_tensor": pose_tensor,
        "elapsed_seconds": round(elapsed, 3)
    }

def preprocess_garment(
    garment_image: Image.Image,
    target_size: Tuple[int, int] = (768, 1024),
    device: str = "cuda"
) -> Dict[str, Any]:
    """
    Preprocesses the garment image:
    Resizes to (768, 1024) and prepares both PIL image and normalized float16 tensor.
    """
    t0 = time.time()
    garm_full = garment_image.convert("RGB").resize(target_size)
    dev_arg = "cuda" if torch.cuda.is_available() and device.startswith("cuda") else "cpu"
    dtype = torch.float16 if dev_arg.startswith("cuda") else torch.float32
    garm_tensor = _TENSOR_TRANSFORM(garm_full).unsqueeze(0).to(dev_arg, dtype)
    
    return {
        "garment_image": garm_full,
        "garment_tensor": garm_tensor,
        "elapsed_seconds": round(time.time() - t0, 3)
    }
