#!/usr/bin/python3
import time
start = time.time()

with open('/tmp/splash-boot.log', 'w') as f:
    f.write(f"Script started at boot time: {time.time()}\n")

from PIL import Image
import driver as LCD_2inch

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

disp = LCD_2inch.LCD_2inch()
disp.Init()
disp.bl_DutyCycle(100)
disp.clear()

image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))
bg = Image.open('assets/scud_splash_1.png')
image.paste(bg, (0, 0))

disp.ShowImage(image)

with open('/tmp/splash-boot.log', 'a') as f:
    f.write(f"[{time.time()-start:.2f}s] First display\n")

for i in range(20):
    time.sleep(1)
    disp.ShowImage(image)
    with open('/tmp/splash-boot.log', 'a') as f:
        f.write(f"[{time.time()-start:.2f}s] Redraw {i}\n")

while True:
    time.sleep(1)