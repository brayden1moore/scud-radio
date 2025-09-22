import driver as LCD_2inch
from PIL import Image, ImageDraw, ImageFont, ImageSequence
import subprocess
import spidev as SPI
import time

# 2 inch
RST = 27
DC = 25
BL = 23
bus = 0 
device = 0 
MAX_BL = 100
SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

disp = LCD_2inch.LCD_2inch()
disp.Init()
disp.clear()
disp.bl_DutyCycle(MAX_BL)

def display_goodbye():
    image = Image.new('RGBA', (SCREEN_WIDTH, SCREEN_HEIGHT))
    for i in 'goodbye':
            
        bg = Image.open(f'assets/scud_{i}.png') 
        image.paste(bg, (0, 0))
        disp.ShowImage(image)
        time.sleep(0.05)

    bg = Image.open(f'assets/scud_splash_2.png') 
    image.paste(bg, (0, 0))
    disp.ShowImage(image)
    time.sleep(1)

display_goodbye()

subprocess.run(['sudo','shutdown','-h','now'])