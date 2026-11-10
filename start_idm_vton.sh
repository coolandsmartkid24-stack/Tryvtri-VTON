#!/bin/bash
export INFERENCE_API_KEY="sk_tryvtri_inference_2026_rtx5080"
export PORT=8888
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
pkill -9 -f "main.py" || true
sleep 1
nohup python3 /root/IDM-VTON/api/main.py > /root/IDM-VTON/api_server.log 2>&1 &
echo "Started IDM-VTON API server PID $!"
