#!/usr/bin/python3
import time
start = time.time()

from PIL import Image
print(f"[{time.time()-start:.2f}s] PIL imported", flush=True)

import driver as LCD_2inch
print(f"[{time.time()-start:.2f}s] Driver imported", flush=True)

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

disp = LCD_2inch.LCD_2inch()
print(f"[{time.time()-start:.2f}s] LCD object created", flush=True)

disp.Init()
print(f"[{time.time()-start:.2f}s] LCD initialized", flush=True)

disp.clear()
disp.bl_DutyCycle(100)
print(f"[{time.time()-start:.2f}s] LCD cleared", flush=True)

image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))
bg = Image.open('assets/scud_splash_1.png')
image.paste(bg, (0, 0))
print(f"[{time.time()-start:.2f}s] Image loaded", flush=True)

disp.ShowImage(image)
print(f"[{time.time()-start:.2f}s] Image displayed!", flush=True)

while True:
    time.sleep(1)