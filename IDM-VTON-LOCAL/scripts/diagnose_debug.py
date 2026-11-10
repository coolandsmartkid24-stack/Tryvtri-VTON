import os
import glob
import json

paths = sorted(glob.glob('/root/IDM-VTON/logs/debug/*/metadata.json'))
print(f'Total debug requests logged: {len(paths)}')
for p in paths[-20:]:
    try:
        with open(p, 'r') as f:
            data = json.load(f)
        req = os.path.basename(os.path.dirname(p))
        cat = data.get('category')
        psize = data.get('product_size')
        score = data.get('quality_score')
        warn = data.get('quality_warning')
        print(f'{req} | cat: {cat} | prod_size: {psize} | score: {score} | warn: {warn}')
    except Exception as e:
        print(f'Error reading {p}: {e}')
