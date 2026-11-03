# On-Demand Lium GPU Deployment (NVIDIA RTX 5080)

This document provides instructions for deploying the standalone FASHN VTON 1.5 inference service on an on-demand Lium GPU instance.

---

## 1. Hardware & Cost Specification

| Parameter | Value |
|-----------|-------|
| GPU Model | NVIDIA GeForce RTX 5080 |
| VRAM | 16 GB GDDR7 |
| Estimated Cost | ~$0.36 / hour |
| Precision | bfloat16 / fp16 |
| Idle Auto-Shutdown | 10 minutes (600 seconds) |

---

## 2. Architecture & Lifecycle Overview

1. **Independent FastAPI Backend**:
   - The FastAPI backend runs 24/7 on ordinary CPU hosting (e.g. Railway, Render, VPS).
   - Customers browsing the Shopify store never start the GPU.

2. **On-Demand Wakeup**:
   - When a customer uploads a photo and clicks **Try On**, the backend checks their quota in Supabase.
   - If eligible, the backend calls Lium's API to launch an RTX 5080 pod.
   - The backend polls `/health` until the inference container is healthy.

3. **Concurrency & Mutex Protection**:
   - An `asyncio.Lock` ensures that parallel requests share the existing running pod instead of launching duplicate billable GPU instances.
   - Requests queue cleanly while the GPU is processing.

4. **10-Minute Idle Shutdown**:
   - When active requests drop to zero, a 10-minute countdown starts.
   - If no new requests arrive within 600 seconds, the backend automatically calls Lium's API to terminate the pod.
   - The GPU never shuts down while an inference request is running.

---

## 3. Lium Inference Container Setup

### Dockerfile (`tryon_service/Dockerfile`)

```dockerfile
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip python3-dev git curl ffmpeg libsm6 libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install PyTorch with CUDA 12.4 support
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu124

# Install repository and inference dependencies
COPY tryon_service/requirements-gpu.txt .
RUN pip install --no-cache-dir -r requirements-gpu.txt

# Copy model code
COPY src/ /workspace/src/
RUN pip install --no-cache-dir -e /workspace

# Download model weights (~2 GB)
COPY scripts/ /workspace/scripts/
RUN python3 scripts/download_weights.py --weights-dir /workspace/weights

# Copy inference server
COPY tryon_service/app.py /workspace/app.py

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 4. Environment Variables on the Backend

Configure in `.env`:

```env
LIUM_API_KEY=your_lium_api_key_here
LIUM_API_BASE=https://lium.io/api
LIUM_GPU_TYPE=RTX 5080
LIUM_MAX_PRICE_PER_GPU_HOUR=0.36
LIUM_TEMPLATE_ID=your_saved_template_id
GPU_IDLE_SHUTDOWN_SECONDS=600
GPU_DAILY_SPEND_CAP_USD=10.0
```

> [!NOTE]
> When `LIUM_API_KEY` is omitted, the backend runs in mock mode for testing without generating charges.
