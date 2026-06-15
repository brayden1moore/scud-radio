from PIL import Image
import numpy as np

img = Image.open('assets/scud_splash_1.png').convert('RGB').resize((320, 240))
arr = np.asarray(img)

pix = np.zeros((240, 320, 2), dtype=np.uint8)
pix[...,0] = (arr[...,0] & 0xF8) | (arr[...,1] >> 5)
pix[...,1] = ((arr[...,1] << 3) & 0xE0) | (arr[...,2] >> 3)
pix.tofile('assets/scud_splash_1.raw')

import os
print("wrote", os.path.getsize('assets/scud_splash_1.raw'), "bytes")