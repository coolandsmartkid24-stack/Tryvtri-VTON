
import time
import urllib.request
from pathlib import Path

import torch
from PIL import Image
from fashn_vton import TryOnPipeline

GARMENT_URL = "https://cougar.com.pk/products/two-toned-framed-sunglasses-sgs616-blk"

PERSON_URL = "https://cdn.shopify.com/s/files/1/0268/9715/4090/files/2N0A5093copy_27ba77a9-d395-4913-b0ca-5a4929249335.webp?v=1784975387&width=1000&height=1499&crop=center"

torch.set_num_threads(4)

def download(url, filename):
    if not Path(filename).exists():
        print("Downloading:", filename)
        urllib.request.urlretrieve(url, filename)
    else:
        print("Already downloaded:", filename)

total_start = time.perf_counter()

print("\n========== FASHN VTON CPU TEST ==========")
print("CUDA:", torch.cuda.is_available())
print("Device: CPU")

# Download images
start = time.perf_counter()

download(GARMENT_URL, "garment.jpg")
download(PERSON_URL, "person.jpg")

print("Download time:", round(time.perf_counter() - start, 2), "seconds")

# Load images
person = Image.open("person.jpg").convert("RGB")
garment = Image.open("garment.jpg").convert("RGB")

print("Person dimensions:", person.size)
print("Garment dimensions:", garment.size)

# Load model
print("\nLoading model...")
start = time.perf_counter()

pipeline = TryOnPipeline(weights_dir="./weights")

load_time = time.perf_counter() - start

print("Model loading:", round(load_time, 2), "seconds")

# Generate try-on
print("\nGenerating virtual try-on...")
start = time.perf_counter()

result = pipeline(
    person_image=person,
    garment_image=garment,
    category="tops"
)

inference_time = time.perf_counter() - start

# Save result
result.images[0].save("tryon_result.png")

total_time = time.perf_counter() - total_start

print("\n========== RESULTS ==========")
print("Output: tryon_result.png")
print("Model loading:", round(load_time, 2), "seconds")
print("Generation:", round(inference_time, 2), "seconds")
print("Total:", round(total_time, 2), "seconds")
print("=============================")
