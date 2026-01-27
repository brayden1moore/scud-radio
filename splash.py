from PIL import Image
import driver as LCD_2inch
import logging
import time

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

disp = LCD_2inch.LCD_2inch()
disp.Init()
disp.clear()
disp.bl_DutyCycle(100)

image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))
bg = Image.open('assets/scud_splash_1.png')
image.paste(bg, (0, 0))
disp.ShowImage(image)

while True:
    time.sleep(0.1)
    pass