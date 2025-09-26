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
    bg = Image.open(f'assets/goodbye.png') 
    image.paste(bg, (0, 0))
    disp.ShowImage(image)
    time.sleep(2)
    disp.bl_DutyCycle(0)
    disp.clear()

display_goodbye()

def restart():
    image = Image.new('RGBA', (SCREEN_WIDTH, SCREEN_HEIGHT))
    bg = Image.open(f'assets/scud_splash_1.png') 
    image.paste(bg, (0, 0))
    disp.ShowImage(image)
    subprocess.run(['sudo','systemctl','restart','radio'])

from gpiozero import RotaryEncoder, Button

click_button = Button(26, bounce_time=0.05)
click_button.when_pressed = restart
click_button.when_held = restart
click_button.when_released = restart

CLK_PIN = 5 
DT_PIN = 6   
rotor = RotaryEncoder(CLK_PIN, DT_PIN)
rotor.when_rotated_counter_clockwise = restart
rotor.when_rotated_clockwise = restart

while True:
    time.sleep(1)
    pass