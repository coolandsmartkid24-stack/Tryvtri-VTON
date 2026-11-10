import numpy as np
from PIL import Image
from preprocess.humanparsing.run_parsing import Parsing

parser = Parsing(gpu_id=0)
for f in ['feet_1_front.jpg', 'feet_2_street.jpg', 'feet_3_fashion.jpg']:
    path = f'/root/IDM-VTON/inputs/test_set/shoes/{f}'
    im = Image.open(path)
    atr, lip = parser(im.resize((384, 512)))
    print(f, 'size:', im.size)
    print(f, 'ATR:', np.unique(atr))
    print(f, 'LIP:', np.unique(lip))
