"""
Professional Gradio Web Interface for IDM-VTON
Provides interactive virtual try-on with automated preprocessing and live GPU metrics.
"""

import os
import sys
import random
import time
import gradio as gr
from PIL import Image

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.inference import run_tryon
from src.model_loader import get_gpu_info, load_pipeline

# Initialize pipeline on startup
print("Initializing IDM-VTON pipeline for Gradio web service...")
try:
    load_pipeline()
except Exception as e:
    print(f"Warning: Deferred pipeline loading: {e}")

def gradio_predict(
    person_img,
    garment_img,
    garment_desc,
    category,
    denoise_steps,
    guidance_scale,
    seed,
    randomize_seed
):
    if person_img is None:
        raise gr.Error("Please upload a person/model image.")
    if garment_img is None:
        raise gr.Error("Please upload a garment image.")

    if randomize_seed:
        actual_seed = random.randint(0, 2147483647)
    else:
        actual_seed = int(seed)

    desc = garment_desc.strip() if garment_desc and garment_desc.strip() else "clothing garment"

    result = run_tryon(
        person_image=person_img,
        garment_image=garment_img,
        garment_description=desc,
        category=category,
        denoise_steps=int(denoise_steps),
        guidance_scale=float(guidance_scale),
        seed=actual_seed
    )

    metrics = result["metrics"]
    stats_md = f"""
### Inference Metrics
- **Total Latency**: `{metrics['total_seconds']}s`
- **Preprocessing Latency**: `{metrics['preprocessing_seconds']}s`
- **Diffusion Latency (UNet)**: `{metrics['inference_seconds']}s`
- **Output Resolution**: `{metrics['resolution']}`
- **GPU Accelerated**: `{metrics['gpu_name']}`
- **Peak VRAM Allocated**: `{metrics['vram_allocated_gb']} GB`
- **Seed**: `{metrics['seed']}`
"""
    return result["result_image"], result["mask_image"], result["pose_image"], stats_md

def create_ui():
    gpu = get_gpu_info()
    header_desc = f"""
# TryVtri — IDM-VTON Virtual Try-On
**High-Fidelity Virtual Try-On Powered by Official IDM-VTON & NVIDIA RTX 5080**
*Device: {gpu.get('name', 'NVIDIA GPU')} | Compute: {gpu.get('compute_capability', '12.0')} | Total VRAM: {gpu.get('vram_total_gb', 16.0)} GB*
"""
    custom_css = """
    .gradio-container { max-width: 1200px !important; margin: auto; }
    .action-btn { background: #2563eb !important; color: white !important; font-weight: bold; font-size: 16px; }
    """

    with gr.Blocks(title="TryVtri IDM-VTON", css=custom_css, theme=gr.themes.Soft()) as demo:
        gr.Markdown(header_desc)

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 1. Inputs")
                person_input = gr.Image(type="pil", label="Model / Human Photo (768x1024)")
                garment_input = gr.Image(type="pil", label="Garment Photo")

                with gr.Accordion("Advanced Settings", open=True):
                    garment_desc = gr.Textbox(
                        label="Garment Description",
                        value="casual short sleeve top",
                        placeholder="e.g. black cotton t-shirt, floral summer dress"
                    )
                    category = gr.Radio(
                        choices=["upper_body", "lower_body", "dresses"],
                        value="upper_body",
                        label="Garment Category"
                    )
                    denoise_steps = gr.Slider(
                        minimum=15, maximum=50, value=30, step=1,
                        label="Diffusion Denoising Steps"
                    )
                    guidance_scale = gr.Slider(
                        minimum=1.0, maximum=5.0, value=2.0, step=0.1,
                        label="CFG Guidance Scale"
                    )
                    with gr.Row():
                        seed = gr.Number(value=42, label="Seed", precision=0)
                        randomize_seed = gr.Checkbox(label="Randomize Seed", value=False)

                run_btn = gr.Button("Generate Virtual Try-On", elem_classes=["action-btn"])

            with gr.Column(scale=1):
                gr.Markdown("### 2. Try-On Result")
                result_output = gr.Image(type="pil", label="Generated High-Definition Result")
                metrics_output = gr.Markdown()

                with gr.Accordion("Generated Masks & Geometry", open=False):
                    with gr.Row():
                        mask_output = gr.Image(type="pil", label="Agnostic Mask")
                        pose_output = gr.Image(type="pil", label="DensePose Geometry")

        run_btn.click(
            fn=gradio_predict,
            inputs=[
                person_input,
                garment_input,
                garment_desc,
                category,
                denoise_steps,
                guidance_scale,
                seed,
                randomize_seed
            ],
            outputs=[
                result_output,
                mask_output,
                pose_output,
                metrics_output
            ]
        )

    return demo

if __name__ == "__main__":
    demo = create_ui()
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)
