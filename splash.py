from PIL import Image, ImageDraw, ImageFont, ImageSequence
from gpiozero import Device
import driver as LCD_2inch
import subprocess
import sys
import time
import threading
import logging
import os

subprocess.run(['sudo','iwconfig','wlan0','power','off'])
subprocess.run(['sudo','iw','dev','wlan0','set','power_save','off'])

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

wifi_waiting = False

# 2 inch
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


def display_splash():

    image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))

    # splash one
    bg = Image.open(f'assets/scud_splash_1.png')
    image.paste(bg, (0, 0))
    disp.ShowImage(image)
    time.sleep(2)

def wait_for_wifi_interface(timeout=60):
    """Wait for WiFi interface to be available"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            result = subprocess.run(['nmcli', 'device', 'status'], 
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, timeout=5)
            if 'wifi' in result.stdout.lower():
                return True
        except subprocess.TimeoutExpired:
            pass
        time.sleep(1)
    return False

def display_wifi_waiting():
    """Display WiFi waiting animation in sequence"""
    wifi_images = ['scud_wifi_3.png', 'scud_wifi_1.png', 'scud_wifi_2.png']
    
    while wifi_waiting:  
        for img in wifi_images:
            if not wifi_waiting:  
                break
            try:
                image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))
                bg = Image.open(f'assets/{img}')
                image.paste(bg, (0, 0))
                disp.ShowImage(image)
                time.sleep(1)
            except:
                pass

display_splash()

wifi_waiting = True

if not wait_for_wifi_interface():
    wifi_waiting = False
    logging.error("WiFi interface not available")
    sys.exit(1)
    
subprocess.run(['sudo','systemctl','start','radio'])