import os
import glob
import cv2
import numpy as np
from PIL import Image

def get_foreground_info(img: Image.Image):
    arr = np.array(img.convert('RGB'))
    corners = [arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]]
    bg_color = np.median(corners, axis=0)
    diff = np.max(np.abs(arr.astype(np.float32) - bg_color), axis=2)
    fg_mask = diff > 20

    coords = np.argwhere(fg_mask)
    if coords.size == 0:
        return 0, 0, img.width, img.height, img.width / float(img.height), 0.0
    y1, x1 = coords.min(axis=0)
    y2, x2 = coords.max(axis=0)
    w = max(1, x2 - x1)
    h = max(1, y2 - y1)
    aspect = w / float(h)
    coverage = coords.shape[0] / float(img.width * img.height)
    return x1, y1, x2, y2, aspect, coverage

base = '/root/IDM-VTON/inputs/test_set'
if not os.path.exists(base):
    base = 'E:/VTON_GARMENTS/IDM-VTON-LOCAL/inputs/test_set'

for cat in ['glasses', 'shoes', 'hats', 'clothing']:
    print(f'=== Category: {cat} ===')
    files = glob.glob(f'{base}/{cat}/*.*')
    for f in sorted(files):
        name = os.path.basename(f)
        try:
            im = Image.open(f)
            x1, y1, x2, y2, aspect, cov = get_foreground_info(im)
            print(f'{name:28s} | size: {im.size} | fg_aspect (W/H): {aspect:.2f} | coverage: {cov:.2f}')
        except Exception as e:
            print(f'{name:28s} | error: {e}')
