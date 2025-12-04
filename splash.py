from PIL import Image
import driver as LCD_2inch
import logging

logging.basicConfig(level=logging.INFO)

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

# 2 inch display config
RST = 27
DC = 25
BL = 23
bus = 0 
device = 0 
MAX_BL = 100

disp = LCD_2inch.LCD_2inch()
disp.Init()
disp.clear()
disp.bl_DutyCycle(MAX_BL)

logging.info('Displaying splash screen')
image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))
bg = Image.open('assets/scud_splash_1_black.png')
image.paste(bg, (0, 0))
disp.ShowImage(image)

logging.info('Splash displayed')
