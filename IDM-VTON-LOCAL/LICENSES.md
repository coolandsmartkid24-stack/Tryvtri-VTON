# Open Source & Model Licenses for TryVtri VTON Pipeline

This document details the software licenses, model weights, and commercial usage terms for all components utilized in the TryVtri virtual try-on multi-category pipeline.

---

## 1. Summary Matrix

| Component | Upstream Project | License | Commercial Use Permitted? |
| :--- | :--- | :--- | :--- |
| **IDM-VTON** | [yisol/IDM-VTON](https://github.com/yisol/IDM-VTON) | **CC BY-NC-SA 4.0** | **NO** (Non-Commercial Only) |
| **MediaPipe FaceMesh** | [Google MediaPipe](https://github.com/google/mediapipe) | **Apache 2.0** | **YES** |
| **DensePose / Detectron2** | [Facebook Research](https://github.com/facebookresearch/detectron2) | **Apache 2.0** | **YES** |
| **rembg / U2-Net-p** | [danielgatis/rembg](https://github.com/danielgatis/rembg) | **MIT License** | **YES** |
| **OpenPose / DWPose** | [openmmlab/mmpose](https://github.com/open-mmlab/mmpose) | **Apache 2.0** | **YES** |
| **Diffusers / PyTorch** | [HuggingFace / Linux Foundation](https://github.com/huggingface/diffusers) | **Apache 2.0 / BSD-3** | **YES** |
| **FastAPI / Uvicorn** | [tiangolo/fastapi](https://github.com/tiangolo/fastapi) | **MIT License** | **YES** |

---

## 2. Critical Commercial Restrictions

> [!CAUTION]
> ### IDM-VTON Non-Commercial Restriction (CC BY-NC-SA 4.0)
> The core diffusion weights for IDM-VTON (`yisol/IDM-VTON`) are licensed under **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)**.
> - **Permitted**: Research, non-commercial evaluation, personal use, academic benchmarking, open demonstrations.
> - **Restricted**: Direct commercial exploitation, paid SaaS virtual try-on billing, merchant licensing without a commercial license from the original authors.
> - **Commercial Alternative**: For production enterprise storefronts requiring unrestricted commercial terms, FASHN API / FASHN commercial weights or private model fine-tuning under Apache 2.0 foundation models (such as Stable Diffusion 1.5 / SDXL commercial tiers) is recommended.

---

## 3. Component Details & Citations

### A. IDM-VTON (Improving Diffusion Models for Virtual Try-ON)
- **Authors**: Yisol Choi, Sangkyung Kwak, Kyungmin Lee, Min-Koo Kang, Xintao Wang, Xiangyu Chen
- **License**: Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International
- **Repository**: `https://github.com/yisol/IDM-VTON`
- **Citation**:
  ```bibtex
  @article{choi2024improving,
    title={Improving Diffusion Models for Authentic Virtual Try-on in the Wild},
    author={Choi, Yisol and Kwak, Sangkyung and Lee, Kyungmin and Kang, Min-Koo and Wang, Xintao and Chen, Xiangyu},
    journal={arXiv preprint arXiv:2403.05139},
    year={2024}
  }
  ```

### B. Google MediaPipe
- **Authors**: Google LLC
- **License**: Apache License 2.0
- **Usage in TryVtri**: 478 3D facial landmarks detection, facial yaw/pitch/roll tracking, nose bridge anchor placement, pupil and temple alignment for eyewear try-on.
- **Commercial Use**: Permitted under standard Apache 2.0 attribution terms.

### C. Detectron2 & DensePose
- **Authors**: Meta AI (Facebook Research)
- **License**: Apache License 2.0
- **Usage in TryVtri**: Human surface UV coordinate estimation, anatomical body segment boundaries.
- **Commercial Use**: Permitted under Apache 2.0.

### D. rembg & U2-Net
- **Authors**: Daniel Gatis & Qin et al.
- **License**: MIT License (rembg), Apache 2.0 (u2net weights)
- **Usage in TryVtri**: Automated catalog product isolation, background removal running under CPUExecutionProvider.
- **Commercial Use**: Permitted under MIT / Apache 2.0.
