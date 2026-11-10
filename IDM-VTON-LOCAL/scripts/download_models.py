"""
Automated Model Weights Downloader for IDM-VTON
Downloads complete pretrained diffusion weights and auxiliary computer vision models.
"""

import os
from huggingface_hub import snapshot_download, hf_hub_download

def download():
    print("=" * 65)
    print("  DOWNLOADING IDM-VTON PRETRAINED CHECKPOINTS")
    print("=" * 65)

    base_repo = "yisol/IDM-VTON"
    print(f"Downloading main pipeline snapshot from {base_repo}...")
    snapshot_download(
        repo_id=base_repo,
        repo_type="model",
        resume_download=True
    )
    print("✓ Main pipeline checkpoints downloaded.")

    # Auxiliary weights
    aux_files = [
        ("densepose/model_final_162be9.pkl", "ckpt/densepose/model_final_162be9.pkl"),
        ("humanparsing/parsing_atr.onnx", "ckpt/humanparsing/parsing_atr.onnx"),
        ("humanparsing/parsing_lip.onnx", "ckpt/humanparsing/parsing_lip.onnx"),
        ("openpose/ckpts/body_pose_model.pth", "ckpt/openpose/ckpts/body_pose_model.pth"),
    ]

    for remote_path, local_rel in aux_files:
        os.makedirs(os.path.dirname(local_rel), exist_ok=True)
        print(f"Downloading {remote_path} from Space...")
        fpath = hf_hub_download(
            repo_id=base_repo,
            repo_type="space",
            filename=f"ckpt/{remote_path}"
        )
        if not os.path.exists(local_rel):
            try:
                os.symlink(fpath, local_rel)
            except Exception:
                import shutil
                shutil.copyfile(fpath, local_rel)
        print(f"✓ Saved {local_rel}")

    print("=" * 65)
    print("ALL CHECKPOINTS READY FOR INFERENCE!")
    print("=" * 65)

if __name__ == "__main__":
    download()
