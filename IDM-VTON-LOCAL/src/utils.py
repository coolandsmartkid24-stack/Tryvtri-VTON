"""
Utility Functions for IDM-VTON Pipeline
Handles image formatting, EXIF rotation correction, base64 conversions, and file I/O.
"""

import io
import os
import base64
from PIL import Image, ImageOps

def load_image(image_input) -> Image.Image:
    """Loads an image from file path, URL, bytes, or returns RGB PIL Image."""
    if isinstance(image_input, Image.Image):
        img = image_input
    elif isinstance(image_input, str):
        if image_input.startswith("data:image"):
            # Base64 string
            header, encoded = image_input.split(",", 1)
            data = base64.b64decode(encoded)
            img = Image.open(io.BytesIO(data))
        elif os.path.exists(image_input):
            img = Image.open(image_input)
        else:
            raise ValueError(f"Invalid image path or format: {image_input}")
    elif isinstance(image_input, bytes):
        img = Image.open(io.BytesIO(image_input))
    else:
        raise ValueError(f"Unsupported image type: {type(image_input)}")

    # Correct EXIF rotation
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")

def pil_to_base64(image: Image.Image, format: str = "PNG") -> str:
    """Converts a PIL Image into base64 data URL string."""
    buffered = io.BytesIO()
    image.save(buffered, format=format)
    b64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    mime = "image/png" if format.upper() == "PNG" else "image/jpeg"
    return f"data:{mime};base64,{b64_str}"

def save_result(image: Image.Image, output_dir: str = "outputs", filename: str = None) -> str:
    """Saves output try-on image and returns the absolute file path."""
    os.makedirs(output_dir, exist_ok=True)
    if filename is None:
        filename = f"tryon_{int(os.times().system * 1000)}.png"
    filepath = os.path.join(output_dir, filename)
    image.save(filepath)
    return os.path.abspath(filepath)
