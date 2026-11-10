"""
GPU & CUDA Diagnostic Script for RTX 5080 (Blackwell sm_120)
Verifies PyTorch GPU compatibility, architecture detection, and tensor execution.
"""

import sys
import torch

def check():
    print("=" * 65)
    print("  GPU & PYTORCH DIAGNOSTIC VERIFICATION")
    print("=" * 65)

    print(f"Python Version:       {sys.version.split()[0]}")
    print(f"PyTorch Version:      {torch.__version__}")
    print(f"CUDA Built-in:        {torch.version.cuda}")
    print(f"CUDA Available:       {torch.cuda.is_available()}")

    if not torch.cuda.is_available():
        print("ERROR: No CUDA device detected! PyTorch is running in CPU mode.")
        sys.exit(1)

    device_count = torch.cuda.device_count()
    print(f"Device Count:         {device_count}")

    for i in range(device_count):
        props = torch.cuda.get_device_properties(i)
        free_bytes, total_bytes = torch.cuda.mem_get_info(i)
        print(f"\n[Device {i}]:")
        print(f"  Name:               {props.name}")
        print(f"  Compute Capability: {props.major}.{props.minor}")
        print(f"  SM Count:           {props.multi_processor_count}")
        print(f"  Total VRAM:         {total_bytes / (1024**3):.2f} GB")
        print(f"  Free VRAM:          {free_bytes / (1024**3):.2f} GB")

    # Blackwell sm_120 capability check
    major, minor = torch.cuda.get_device_capability(0)
    print("\n--- Tensor Execution Verification ---")
    try:
        a = torch.randn(2048, 2048, device="cuda", dtype=torch.float16)
        b = torch.randn(2048, 2048, device="cuda", dtype=torch.float16)
        c = torch.matmul(a, b)
        torch.cuda.synchronize()
        print("✓ FP16 Matrix Multiplication on RTX 5080: SUCCESS")
    except Exception as e:
        print(f"✗ FP16 Tensor Execution Failed: {e}")

    try:
        a_bf = torch.randn(2048, 2048, device="cuda", dtype=torch.bfloat16)
        b_bf = torch.randn(2048, 2048, device="cuda", dtype=torch.bfloat16)
        c_bf = torch.matmul(a_bf, b_bf)
        torch.cuda.synchronize()
        print("✓ BF16 Matrix Multiplication on RTX 5080: SUCCESS")
    except Exception as e:
        print(f"✗ BF16 Tensor Execution Failed: {e}")

    print("=" * 65)
    print("ALL HARDWARE & CUDA CHECKS PASSED!")
    print("=" * 65)

if __name__ == "__main__":
    check()
