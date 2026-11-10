# TryVtri — Multi-Category Virtual Try-On Pipeline (NVIDIA RTX 5080)

Production-grade, low-latency virtual try-on pipeline powered by the official **IDM-VTON** (Improving Diffusion Models for Authentic Virtual Try-on in the Wild) diffusion architecture and dedicated geometric/keypoint pipelines, running on the **NVIDIA GeForce RTX 5080** (Blackwell architecture, sm_120 compute capability).

---

## 1. System Architecture

```
                          ┌───────────────────────────┐
                          │  Storefront / Web Client  │
                          └─────────────┬─────────────┘
                                        │
                         HTTP REST API  │  Gradio Web UI
                        (Port 8888)     │  (Port 7860)
                                        ▼
    ┌────────────────────────────────────────────────────────────────────────┐
    │                 TryVtri Multi-Category Pipeline Engine                 │
    │                                                                        │
    │  ┌───────────────────────┐              ┌───────────────────────────┐  │
    │  │ Category Auto-Router  │              │ Pipelines                 │  │
    │  │  - Clothing (Tops,    │─────────────►│  - Clothing (IDM-VTON)    │  │
    │  │    Bottoms, Dresses)  │              │  - Shoes (Foot & Shadow)  │  │
    │  │  - Shoes / Footwear   │              │  - Glasses (MediaPipe 3D) │  │
    │  │  - Glasses / Eyewear  │              └─────────────┬─────────────┘  │
    │  └───────────────────────┘                            │                │
    │                                                       ▼                │
    │                                         ┌───────────────────────────┐  │
    │                                         │ Automated Quality Gate    │  │
    │                                         │  - Drift Check (<4.0)     │  │
    │                                         │  - Mask Area Coverage     │  │
    │                                         │  - Contrast & Color Dist. │  │
    │                                         │  - Auto-Retry if Failed   │  │
    │                                         └─────────────┬─────────────┘  │
    │                                                       ▼                │
    │                                         ┌───────────────────────────┐  │
    │                                         │ Seamless Alpha Composite  │  │
    │                                         └─────────────┬─────────────┘  │
    └───────────────────────────────────────────────────────┼────────────────┘
                                                            ▼
                                             High-Definition Try-On Result
                                                   (768 x 1024 PNG)
```

---

## 2. Hardware & Environment Specifications

- **Target GPU**: NVIDIA GeForce RTX 5080
- **Architecture**: Blackwell (sm_120, Compute Capability 12.0)
- **VRAM**: 16,303 MiB (15.9 GB)
- **Driver Version**: 595.99.02 (CUDA 13.2 compatible)
- **PyTorch**: 2.12.0+cu130 (compiled with native Blackwell sm_120 support)
- **Precision**: FP16 Mixed Precision with expandable memory segments

---

## 3. Dedicated Category Pipelines

### A. Clothing (Enhanced IDM-VTON)
- **Category-Aware Crop**: Automatically identifies the relevant body region (shoulders to hips for tops; waist to feet for bottoms; neck to feet for dresses) and crops to a standard 3:4 aspect ratio.
- **On-Model Human Stripping**: If catalog garment shots include an on-model person, uses human parsing to isolate only the clothing garment pixels, preventing the model's head/beard from appearing on the user.
- **Adaptive Mask Dilation (+30 to 70px)**: Dilates past existing garment boundaries so no underlying collars, hoodies, or denim peek through the new garment.
- **Compositing**: Preserves 100% of the non-target pixels (face, hair, hands, opposite body half, and background).

### B. Shoes & Footwear
- **Foot & Ankle Segmentation**: Detects left and right feet, rejects images where feet are cut off or touch the bottom image boundary.
- **Pants Hem Preservation**: Segments lower hem of trousers and renders shoes behind the hemline.
- **Floor Contact Shadow**: Automatically extracts the footwear contact shadow and composites it onto the floor beneath the new shoes.

### C. Glasses & Eyewear
- **MediaPipe FaceMesh 3D**: Detects 468 facial landmarks to compute exact 3D pitch, roll, and yaw angles.
- **Perspective Warp**: Maps glasses frames to the temple-to-temple and ear-hinge landmarks.
- **Reflection Elimination**: Removes studio floor/table reflections underneath glasses frames.
- **Lens Blending**: Adds realistic translucency and eye visibility through clear/tinted lenses.

---

## 4. Automated Quality Gate

Every inference passes through an automated verification suite before returning to the storefront:
- **Outside-Mask Drift**: Verifies that pixels outside the target region have mean difference $< 4.0$ (no face or background alterations).
- **Target Region Overlap**: Confirms the new garment/accessory covers $\ge 60\%$ of the target agnostic mask.
- **Single Auto-Retry**: If drift or coverage fails, a single retry automatically executes with adjusted denoising steps (+5) and guidance scale (+0.5).
- **Audit Headers**: Responses return `X-Quality-Score` and `X-Quality-Warning` headers.

---

## 5. Performance Benchmarks on NVIDIA RTX 5080

| Category / Operation | End-to-End Latency | Quality Gate Score |
| :--- | :--- | :--- |
| **Glasses (MediaPipe 3D)** | **`0.25s – 1.14s`** | **`1.00 (Pass)`** |
| **Shoes (Foot & Shadow Composite)** | **`0.55s – 0.66s`** | **`1.00 (Pass)`** |
| **Clothing (IDM-VTON Tops - 30 steps)** | **`18.0s – 19.1s`** | **`1.00 (Pass)`** |
| **Clothing (IDM-VTON Bottoms)** | **`18.5s`** | **`1.00 (Pass)`** |
| **Storefront Vercel API (Roundtrip)** | **`10.7s – 12.4s`** | **`1.00 (Pass)`** |

---

## 6. API Reference

### `POST /infer`
Multipart Form-Data or JSON request.

**Headers**:
- `X-Inference-Key`: `sk_tryvtri_inference_2026_rtx5080`

**Fields**:
- `person_image`: Image file or base64 data URI
- `garment_image`: Image file or base64 data URI
- `category`: `tops` | `bottoms` | `one-pieces` | `shoes` | `glasses` | `auto`

### `GET /health`
Returns GPU status, VRAM allocation, and supported categories.
