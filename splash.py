#!/usr/bin/python3
import time
start = time.time()

# Log to file so we can see what's happening
with open('/tmp/splash-boot.log', 'w') as f:
    f.write(f"Script started at boot time: {time.time()}\n")
    f.write(f"[{time.time()-start:.2f}s] Starting imports\n")

from PIL import Image
import driver as LCD_2inch

with open('/tmp/splash-boot.log', 'a') as f:
    f.write(f"[{time.time()-start:.2f}s] Imports done\n")

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

disp = LCD_2inch.LCD_2inch()
disp.Init()
disp.clear()
disp.bl_DutyCycle(100)

image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))
bg = Image.open('assets/scud_splash_1.png')
image.paste(bg, (0, 0))

with open('/tmp/splash-boot.log', 'a') as f:
    f.write(f"[{time.time()-start:.2f}s] About to display\n")

disp.ShowImage(image)

with open('/tmp/splash-boot.log', 'a') as f:
    f.write(f"[{time.time()-start:.2f}s] DISPLAYED!\n")

while True:
    time.sleep(1)