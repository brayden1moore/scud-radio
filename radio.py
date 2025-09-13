from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont, ImageSequence
from datetime import date, datetime, timezone, timedelta
from subprocess import Popen, run
import driver as LCD_2inch
from pathlib import Path
from io import BytesIO
import spidev as SPI
import numpy as np
import subprocess
import threading
import requests
import platform
import logging
import random
import pickle
import signal
import pytz
import time
import math
import html
import sys
import re
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

## constants and variables

# 2 inch
RST = 27
DC = 25
BL = 23
bus = 0 
device = 0 
MAX_BL = 80
disp = LCD_2inch.LCD_2inch()
disp.Init()
disp.clear()
disp.bl_DutyCycle(MAX_BL)

mpv_process = None
stream = None
readied_stream = None
last_rotation = None
screen_on = True
current_image = None
saved_image_while_paused = None
play_status = 'pause'
last_input_time = time.time()
first_display = True
current_volume = 65
volume_step = 5  
button_press_time = 0
rotated = False
battery = None
charging = False
restarting = False
held = False
user_tz = 'UTC'
wifi_strength = None

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240
FONT_SIZE = 6

WHITE = (255,255,255)
BLACK = (0,0,0)
YELLOW = (255,255,0)
BLUE = (0,187,255)
GREEN = (0,231,192)
GREY = (100,100,100)
ORANGE = (255,128,0)
PURPLE = (134,97,245)
RED = (255,71,71)

BORDER_COLOR = BLACK
TEXT_COLOR = BLACK
TEXT_COLOR_2 = BLACK
BACKGROUND_COLORS = []
BACKGROUND_COLOR = WHITE
SLIDER_BG = WHITE
SLIDER_COLOR = BLACK
BORDER_SIZE = 2

LOGO_SIZE = 120
LOGO_Y = 0
LOGO_X = round(SCREEN_WIDTH/2) - round(LOGO_SIZE/2)

READIED_LOGO_SIZE = 90
READIED_LOGO_Y = LOGO_Y + round((LOGO_SIZE-READIED_LOGO_SIZE) / 2) - 10
READIED_LOGO_X = round(SCREEN_WIDTH/2) - round(READIED_LOGO_SIZE/2)

SMALL_LOGO_SIZE = 70
SMALL_LOGO_Y = LOGO_Y + round(LOGO_SIZE/2) - round(SMALL_LOGO_SIZE/2)
PREV_LOGO_X = LOGO_X - round(SMALL_LOGO_SIZE) + 15 - BORDER_SIZE
NEXT_LOGO_X = LOGO_X + LOGO_SIZE - 15 + BORDER_SIZE

SMALLEST_LOGO_SIZE = 50
SMALLEST_LOGO_Y = LOGO_Y + round(LOGO_SIZE/2) - round(SMALLEST_LOGO_SIZE/2) + 10
DOUBLE_PREV_LOGO_X = PREV_LOGO_X - round(SMALLEST_LOGO_SIZE) + 15 - BORDER_SIZE
DOUBLE_NEXT_LOGO_X = NEXT_LOGO_X + SMALL_LOGO_SIZE - 15 + BORDER_SIZE

TITLE_Y = LOGO_SIZE + LOGO_Y - 13
LOCATION_Y = TITLE_Y + 31
SUBTITLE_Y = LOCATION_Y + 45

STATUS_SIZE = 25
STATUS_LOCATION = (LOGO_X+round(LOGO_SIZE/2)-round(STATUS_SIZE/2), LOGO_Y+round(LOGO_SIZE/2)-round(STATUS_SIZE/2))

#SMALL_FONT = ImageFont.truetype("assets/Silkscreen-Regular.ttf", 10)
#MEDIUM_FONT = ImageFont.truetype("assets/Silkscreen-Regular.ttf", 20)
#LARGE_FONT = ImageFont.truetype("assets/Silkscreen-Regular.ttf",28)

#SMALL_FONT = ImageFont.truetype("assets/andalemono.ttf", 10)
#MEDIUM_FONT = ImageFont.truetype("assets/andalemono.ttf", 20)
#LARGE_FONT = ImageFont.truetype("assets/Arial Black.ttf",28)
#BIGGEST_FONT = ImageFont.truetype("assets/Arial Black.ttf",28)

SMALL_FONT = ImageFont.truetype("assets/Archivo-Light.ttf", 10)
MEDIUM_FONT = ImageFont.truetype("assets/Archivo-Light.ttf", 20)
LARGE_FONT = ImageFont.truetype("assets/Archivo-ExtraBold.ttf",28)
BIGGEST_FONT = LARGE_FONT

PAUSE_IMAGE = (Image.open('assets/pause.png').convert('RGBA').resize((LOGO_SIZE+BORDER_SIZE*2, LOGO_SIZE+BORDER_SIZE*2)))

unfavorite = Image.open('assets/unfavorited.png').convert('RGBA')
favorite_images = [Image.open('assets/favorited1.png').convert('RGBA'), 
                   Image.open('assets/favorited2.png').convert('RGBA'), 
                   Image.open('assets/favorited3.png').convert('RGBA'), 
                   Image.open('assets/favorited4.png').convert('RGBA'),
                   Image.open('assets/favorited5.png').convert('RGBA')]

star_smallest = Image.open('assets/star_smallest.png').convert('RGBA')
star_small = Image.open('assets/star_small.png').convert('RGBA')
star_readied = Image.open('assets/star_readied.png').convert('RGBA')

live_smallest = Image.open('assets/live_smallest.png').convert('RGBA')
live_small = Image.open('assets/live_small.png').convert('RGBA')
live_readied = Image.open('assets/live_readied.png').convert('RGBA')
live_banner = Image.open('assets/live_banner.png').convert('RGBA')

ONE_LOGO_X = 15
ONE_LOGO_Y = 18 + 16
ONE_NAME_X = 77
ONE_NAME_Y = 12 + 16 + 2
ONE_LOC_X = ONE_NAME_X
ONE_LOC_Y = ONE_NAME_Y + 31 
TOP_DIVIDER_X = 11
TOP_DIVIDER_Y = 80 + 3 + 12
BOTTOM_DIVIDER_X = TOP_DIVIDER_X
BOTTOM_DIVIDER_Y = 175
SHOW_ROW_1_X = TOP_DIVIDER_X
SHOW_ROW_1_Y = TOP_DIVIDER_Y
BOTTOM_DIVIDER_X = TOP_DIVIDER_X
BOTTOM_DIVIDER_Y = 170
SHOW_INFO_X = TOP_DIVIDER_X
SHOW_INFO_ROW_1_Y = 187

LIB_PATH = "/var/lib/scud-radio"

def get_favorites():
    fav_path = Path(LIB_PATH)
    fav_path.mkdir(parents=True, exist_ok=True)
    
    favorites_file = fav_path / 'favorites.txt'
    if not favorites_file.exists():
        favorites_file.touch() 
        return []
    
    with open(favorites_file, 'r') as f:
        favorites = f.readlines()
    return [fav.strip() for fav in favorites]

def set_favorites(favorites):
    fav_path = Path(LIB_PATH)
    fav_path.mkdir(parents=True, exist_ok=True)
    
    with open(fav_path / 'favorites.txt', 'w') as f:
        f.write('\n'.join(favorites))

favorites = get_favorites()

def get_last_volume():
    vol_path = Path(LIB_PATH)
    vol_path.mkdir(parents=True, exist_ok=True)
    
    volume_file = vol_path / 'volume.txt'
    if not volume_file.exists():
        volume_file.touch() 
        return 65
    
    try:
        with open(volume_file, 'r') as f:
            vol = int(f.read())
        return vol
    except:
        return 65

def set_last_volume(vol):
    vol_path = Path(LIB_PATH)
    vol_path.mkdir(parents=True, exist_ok=True)

    with open(vol_path / 'volume.txt', 'w') as f:
        f.write(vol)

current_volume = get_last_volume()

def safe_display(image):
    global current_image
    if screen_on & (image != current_image):
        disp.ShowImage(image)
    current_image = image.copy()
    

def write_to_tmp_os_path(name):
    file_path = os.path.join("/tmp", "scud_last_played.txt")
    
    with open(file_path, 'w') as file:
        file.write(name)


def read_last_played():
    file_path = os.path.join("/tmp", "scud_last_played.txt")

    try:
        with open(file_path, 'r') as file:
            last_played = file.read()
        
        return last_played
    except:
        return None
    
def get_battery():
    global battery, charging

    try:
        result = subprocess.run(['nc', '-q', '1', '127.0.0.1', '8423'], 
                                input='get battery_charging\nget battery\n', 
                                stdout=subprocess.PIPE, text=True, timeout=2)
        
        lines = result.stdout.strip().split('\n')
        if 'battery' not in lines[0]:
            lines = lines[1:]

        #logging.info(lines)
        
        charging_line = lines[0].strip().split(': ')[1] 
        charging = charging_line == 'true'
        
        battery_line = lines[1].strip().split(': ')[1] 
        battery = int(float(battery_line))
    except Exception as e:
        #logging.info(e)
        return battery, charging

    return battery, charging

def get_timezone_from_ip():
    try:
        response = requests.get('http://ip-api.com/json/')
        data = response.json()
        return data['timezone']
    except:
        return 'UTC' 

def display_scud():
    '''
    image = Image.new('RGBA', (SCREEN_WIDTH, SCREEN_HEIGHT))
    rotations = 0
    max_rotations = 2
    while rotations <max_rotations:
        for i in [2,3,4,5,6,7,1]:
             
            bg = Image.open(f'assets/gif/{i}.png') 
            image.paste(bg, (0, 0))
            safe_display(image)  

            if i==1 and rotations==max_rotations-1:
                time.sleep(0)
            else:
                time.sleep(0.01)

        rotations += 1

    bg = Image.open(f'assets/gif/1.png') 
    image.paste(bg, (0, 0))
    safe_display(image)  
    '''

    global user_tz

    timezone_name = get_timezone_from_ip()
    user_tz = pytz.timezone(timezone_name)
    now = time.time()
    current_time = datetime.fromtimestamp(now, tz=user_tz)
    current_hour = current_time.hour

    greeting = 'Hello'
    size = 192
    bbox = [64, 120, 64 + size, 120 + size]
    color = PURPLE

    if 5 <= current_hour < 12:
        greeting = 'Good Morning'
        bbox = [160, 24, 160 + size, 24 + size]
        color = RED
    elif 12 <= current_hour < 17: 
        greeting = 'Good Afternoon'
        bbox = [64, -59, 64 + size, -50 + size]
        color = YELLOW
    elif 17 <= current_hour < 22:
        greeting = 'Good Evening'
        bbox = [-32, 24, -32 + size, 24 + size]
        color = BLUE
    
    last_played = read_last_played()
    volume = round((get_last_volume()/150)*100)
    get_battery()

    '''
    frames = os.listdir('assets/splash')
    for i in range(0,103): # might make 52

        image = Image.new('RGBA', (SCREEN_WIDTH, SCREEN_HEIGHT), color=color)
        draw = ImageDraw.Draw(image)
        
        #draw.ellipse(bbox, fill=color, outline=BLACK, width=1)

        draw.text((10, 0), greeting + ",", font=LARGE_FONT, fill=BLACK) 
        draw.text((10, 23),  "Friend.", font=LARGE_FONT, fill=BLACK) 

        draw.text((10, 193), f'Last Played: {last_played}', font=SMALL_FONT, fill=BLACK)
        draw.text((10, 203), f'Internet: Connected', font=SMALL_FONT, fill=BLACK)
        draw.text((10, 213), f'Battery: {battery}%', font=SMALL_FONT, fill=BLACK)
        draw.text((10, 223), f'Volume: {volume}%', font=SMALL_FONT, fill=BLACK)

        frame_num = str(i).zfill(3)
        frame = Image.open(f'assets/splash/frame_{frame_num}_delay-0.03s.gif').convert('RGBA')
        image.paste(frame, (40, 0), frame)
        safe_display(image) 
    '''


def backlight_on():
    if disp:
        if current_image:
            safe_display(current_image)
        else:
            display_scud()
        disp.bl_DutyCycle(MAX_BL)

def backlight_off():
    if disp:
        disp.bl_DutyCycle(0)
        disp.clear()

display_scud()

mpv_process = Popen([
    "mpv",
    "--idle=yes",
    "--no-video",
    f"--volume={current_volume}",
    "--volume-max=150",
    "--input-ipc-server=/tmp/mpvsocket",
    "--msg-level=all=info", 
    "--msg-level=ipc=no",
    "--log-file=/tmp/mpv_debug.log" 
], stdout=None, stderr=None)

while not os.path.exists("/tmp/mpvsocket"):
    time.sleep(0.1)

from gpiozero import Button
import socket
import json

def send_mpv_command(cmd, max_retries=5, retry_delay=0.5):
    for attempt in range(max_retries):
        try:
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(2)
                s.connect("/tmp/mpvsocket")
                s.sendall((json.dumps(cmd) + '\n').encode())
                #logging.info(f"Sent MPV command: {cmd}")
                return True
        except (ConnectionRefusedError, FileNotFoundError, socket.timeout) as e:
            if attempt < max_retries - 1:
                logging.warning(f"MPV command failed (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(retry_delay)
            else:
                logging.error(f"MPV command failed after {max_retries} attempts: {e}")
                return False
    return False

def fetch_logo(name, url):
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    return name, BytesIO(resp.content)

def get_streams():
    global streams

    info = requests.get('https://internetradioprotocol.org/info').json()
    active = {n: v for n, v in info.items() if v['status']=="Online" and v['hidden']!=True}
    
    # clean text
    for name, _ in active.items():
        active[name]['oneLiner'] = html.unescape(active[name]['oneLiner'])
    
    # see if cached image exists. if so, read into dict. if not, add to queue.
    need_imgs = []
    for name, _ in active.items():
        full_img_path = Path(LIB_PATH) / f'{name}_logo_full.pkl'
        if not full_img_path.exists():
            need_imgs.append(name)
        else:
            file_stat = full_img_path.stat()
            file_age_seconds = time.time() - file_stat.st_mtime
            file_age_days = file_age_seconds / (24 * 3600) 

            if file_age_days > 7:  # refresh if older than 7 days
                need_imgs.append(name)
            else:
                for i in ['full','readied','small','smallest']:
                    with open(Path(LIB_PATH) / f'{name}_logo_{i}.pkl', 'rb') as f:
                        active[name][f'logo_{i}'] = pickle.load(f)

    with ThreadPoolExecutor(max_workers=8) as exe:
        futures = [
            exe.submit(fetch_logo, name, v['logo'])
            for name, v in active.items() if name in need_imgs
        ]
        for f in as_completed(futures):
            name, buf = f.result()
            active[name]['logoBytes'] = buf

            img = Image.open(buf).convert('RGB')

            # crop images
            full_img = img.resize((LOGO_SIZE,  LOGO_SIZE))
            readied_img = img.resize((READIED_LOGO_SIZE,  READIED_LOGO_SIZE))
            small_img = img.resize((SMALL_LOGO_SIZE, SMALL_LOGO_SIZE))
            smallest_img = img.resize((SMALLEST_LOGO_SIZE, SMALLEST_LOGO_SIZE))
    
            # save images to dict
            active[name]['logo_full'] = full_img
            active[name]['logo_readied']  = readied_img
            active[name]['logo_small'] = small_img
            active[name]['logo_smallest'] = smallest_img

            # save images to lib
            for i in ['full','readied','small','smallest']:
                entire_path = Path(LIB_PATH) / f'{name}_logo_{i}.pkl'
                if not entire_path.exists():
                    entire_path.touch() 

                with open(entire_path, 'wb') as f:
                    pickle.dump(active[name][f'logo_{i}'], f)

    return active

reruns = []
def get_stream_list(streams):
    global reruns 
    stream_list = list(streams.keys())
    reruns = [i for i in stream_list if any(j in streams[i]['oneLiner'].lower() for j in ['(r)','re-run','re-wav','restream','playlist','auto dj','night moves']) or i=='Monotonic Radio' or ' ARCHIVE' in streams[i]['oneLiner']]
    stream_list = sorted([i for i in stream_list if i in favorites]) + sorted([i for i in stream_list if i not in favorites])
    return stream_list

streams = get_streams()
stream_list = get_stream_list(streams)

# hat
'''
disp = st7789.ST7789(
    rotation=180,     # Needed to display the right way up on Pirate Audio
    port=0,          # SPI port
    cs=1,            # SPI port Chip-select channel
    dc=9,            # BCM pin used for data/command
    backlight=13,  # 13 for Pirate-Audio; 18 for back BG slot, 19 for front BG slot.
)
disp.begin()
'''


def width(string, font):
    left, top, right, bottom = font.getbbox(string)
    text_width = right - left
    return text_width

def height(string, font):
    left, top, right, bottom = font.getbbox(string)
    text_height =  bottom - top
    return text_height

def x(string, font):
    text_width = width(string,font)
    return max((SCREEN_WIDTH - text_width) // 2, 5)

def s(number):
    if number == 1:
        return ''
    else:
        return 's'
    

def pause(show_icon=False):
    global play_status, saved_image_while_paused, current_image
    #send_mpv_command({"command": ["stop"]})
    #send_mpv_command({"command": ["set_property", "volume", 0]})

    if show_icon and current_image:
        saved_image_while_paused = current_image.copy()
        img = current_image.convert('RGBA')
        img.paste(PAUSE_IMAGE, (LOGO_X, LOGO_Y), PAUSE_IMAGE)
        safe_display(img.convert('RGB'))

    play_status = 'pause'


def play(name, toggled=False):
    global play_status, stream
    play_status = 'play'
    stream = name

    if toggled:
        safe_display(saved_image_while_paused)
        send_mpv_command({"command": ["set_property", "volume", current_volume]})
    else:
        #logging.info(f'attempting to play {name}')
        stream_url = streams[name]['streamLink']
        send_mpv_command({"command": ["loadfile", stream_url, "replace"]})
        send_mpv_command({"command": ["set_property", "volume", current_volume]})

    write_to_tmp_os_path(name)


def play_random():
    global stream, play_status
    pause()
    available_streams = [i for i in stream_list if i != stream]
    chosen = random.choice(available_streams)
    display_everything(chosen)
    play(chosen)
    stream = chosen
    play_status = 'play'


def calculate_text(text, font, max_width, lines):
    text = text.strip()

    if width(text, font) <= max_width:
        return [text]
    
    else:
        current_width = 0
        characters = ''
        line_list = []
        current_line = 1
        dots_width = width('...', font)
        
        if lines > 1:
            text = text.split(' ')

        for idx, i in enumerate(text):

            if lines > 1:
                i = i + ' '

            if current_line == lines:
                if width(characters + i, font) >= max_width-dots_width: # if width exceeds max - dots, return
                    characters += '...'
                    line_list.append(characters)
                    return line_list
                else:
                    characters += i
                    current_width = width(characters, font)
            else:
                if width(characters + i, font) >= max_width: # if current line exceeds max width and is not last line
                    if i in [')']:
                        characters += i
                    else:
                        current_line += 1
                        line_list.append(characters)
                        if i not in [' ','-','/',':']:
                            characters = i
                        else:
                            characters = ''
                        current_width = 0
                else:
                    characters += i
                    current_width = width(characters, font)
        if characters:  # if there are remaining characters
            line_list.append(characters)
        return line_list
    

def display_everything(name, update=False, readied=False):
    global streams, play_status, first_display

    highlight_color = BLUE #if name in favorites else BLUE if name not in reruns else GREEN
    
    if readied and not restarting:
        first_display = False

        prev_stream = stream_list[stream_list.index(name)-1]
        double_prev_stream = stream_list[stream_list.index(prev_stream)-1]
        try:
            next_stream = stream_list[stream_list.index(name)+1]
            double_next_stream = stream_list[stream_list.index(next_stream)+1]
        except:
            try: # just wrap around the double next
                next_stream = stream_list[stream_list.index(name)+1]
                double_next_stream = stream_list[0]
            except: # wrap around both
                next_stream = stream_list[0]
                double_next_stream = stream_list[1]

        bg_color = WHITE #BLUE if name in favorites else WHITE 
        image = Image.new('RGBA', (SCREEN_WIDTH, SCREEN_HEIGHT), color=bg_color)
        draw = ImageDraw.Draw(image)

        yellow_band_height = 55

        draw.rectangle([0, 0, SCREEN_WIDTH, SCREEN_HEIGHT/2], fill=BLACK)
        draw.rectangle([0, SCREEN_HEIGHT/2-21, SCREEN_WIDTH, SCREEN_HEIGHT/2 + yellow_band_height], fill=highlight_color)

        draw.rectangle([0, SCREEN_HEIGHT/2 + yellow_band_height, SCREEN_WIDTH, SCREEN_HEIGHT/2 + yellow_band_height + 1], fill=BLACK)

        logo = streams[name]['logo_full']
        readied_logo = streams[name]['logo_readied']
        prev = streams[prev_stream]['logo_small']
        next = streams[next_stream]['logo_small']
        double_prev = streams[double_prev_stream]['logo_smallest']
        double_next = streams[double_next_stream]['logo_smallest']

        # double prev and next borders
        border3 = Image.new('RGB', (SMALLEST_LOGO_SIZE+BORDER_SIZE*2, SMALLEST_LOGO_SIZE+BORDER_SIZE*2), color=BLACK)

        # double prev
        image.paste(border3, (DOUBLE_PREV_LOGO_X, SMALLEST_LOGO_Y))

        # double next
        image.paste(border3, (DOUBLE_NEXT_LOGO_X, SMALLEST_LOGO_Y))

        # paste
        image.paste(double_prev, (DOUBLE_PREV_LOGO_X+BORDER_SIZE, SMALLEST_LOGO_Y+BORDER_SIZE))
        image.paste(double_next, (DOUBLE_NEXT_LOGO_X+BORDER_SIZE, SMALLEST_LOGO_Y+BORDER_SIZE))
        if double_prev_stream in favorites:
            image.paste(star_smallest, (DOUBLE_PREV_LOGO_X+BORDER_SIZE, SMALLEST_LOGO_Y+BORDER_SIZE), star_smallest)
        if double_next_stream in favorites:
            image.paste(star_smallest, (DOUBLE_NEXT_LOGO_X+BORDER_SIZE, SMALLEST_LOGO_Y+BORDER_SIZE), star_smallest)
        if double_prev_stream not in reruns:
            image.paste(live_smallest, (DOUBLE_PREV_LOGO_X+BORDER_SIZE, SMALLEST_LOGO_Y+BORDER_SIZE), live_smallest)
        if double_next_stream not in reruns:
            image.paste(live_smallest, (DOUBLE_NEXT_LOGO_X+BORDER_SIZE, SMALLEST_LOGO_Y+BORDER_SIZE), live_smallest)


        # prev and next borders
        border3 = Image.new('RGB', (SMALL_LOGO_SIZE+BORDER_SIZE*2, SMALL_LOGO_SIZE+BORDER_SIZE*2), color=BLACK)

        # prev
        image.paste(border3, (PREV_LOGO_X, SMALL_LOGO_Y))

        # next
        image.paste(border3, (NEXT_LOGO_X, SMALL_LOGO_Y))

        # paste
        image.paste(prev, (PREV_LOGO_X+BORDER_SIZE, SMALL_LOGO_Y+BORDER_SIZE))
        image.paste(next, (NEXT_LOGO_X+BORDER_SIZE, SMALL_LOGO_Y+BORDER_SIZE))
        if prev_stream in favorites:
            image.paste(star_small, (PREV_LOGO_X+BORDER_SIZE, SMALL_LOGO_Y+BORDER_SIZE), star_small)
        if next_stream in favorites:
            image.paste(star_small, (NEXT_LOGO_X+BORDER_SIZE, SMALL_LOGO_Y+BORDER_SIZE), star_small)
        if prev_stream not in reruns:
            image.paste(live_small, (PREV_LOGO_X+BORDER_SIZE, SMALL_LOGO_Y+BORDER_SIZE), live_small)
        if next_stream not in reruns:
            image.paste(live_small, (NEXT_LOGO_X+BORDER_SIZE, SMALL_LOGO_Y+BORDER_SIZE), live_small)

        if readied:
            border1 = Image.new('RGB', (READIED_LOGO_SIZE+BORDER_SIZE*6, READIED_LOGO_SIZE+BORDER_SIZE*6), color=BLACK)
            border2 = Image.new('RGB', (READIED_LOGO_SIZE+BORDER_SIZE*4, READIED_LOGO_SIZE+BORDER_SIZE*4), color=highlight_color)
            border3 = Image.new('RGB', (READIED_LOGO_SIZE+BORDER_SIZE*2, READIED_LOGO_SIZE+BORDER_SIZE*2), color=BLACK)
            image.paste(border1, (READIED_LOGO_X-BORDER_SIZE*2, READIED_LOGO_Y-BORDER_SIZE*2))
            image.paste(border2, (READIED_LOGO_X-BORDER_SIZE, READIED_LOGO_Y-BORDER_SIZE))
            image.paste(border3, (READIED_LOGO_X, READIED_LOGO_Y))

            draw.rectangle([0, SCREEN_HEIGHT/2-21, SCREEN_WIDTH, SCREEN_HEIGHT/2-21+10], fill=highlight_color)
            image.paste(readied_logo, (READIED_LOGO_X+BORDER_SIZE, READIED_LOGO_Y+BORDER_SIZE))
            if name in favorites:
                image.paste(star_readied, (READIED_LOGO_X+BORDER_SIZE, READIED_LOGO_Y+BORDER_SIZE), star_readied)
            if name not in reruns:
                image.paste(live_readied, (READIED_LOGO_X+BORDER_SIZE, READIED_LOGO_Y+BORDER_SIZE), live_readied)                
        else:
            border3 = Image.new('RGB', (LOGO_SIZE+BORDER_SIZE*3, LOGO_SIZE+BORDER_SIZE*3), color=BORDER_COLOR)
            image.paste(border3, (LOGO_X, LOGO_Y))
            image.paste(logo, (LOGO_X+BORDER_SIZE, LOGO_Y+BORDER_SIZE))

        location = streams[name]['location']
        name_line = calculate_text(name, LARGE_FONT, 300, 1)
        title_lines = calculate_text(streams[name]['oneLiner'].replace('&amp;','&'), MEDIUM_FONT, 300, 2)

        draw.text((SHOW_INFO_X, TITLE_Y), name_line[0], font=LARGE_FONT, fill=BLACK)
        draw.text((SHOW_INFO_X, LOCATION_Y), location, font=MEDIUM_FONT, fill=BLACK)

        y_offset = 0
        for i in title_lines:
            draw.text((SHOW_INFO_X, SUBTITLE_Y + y_offset), i, font=MEDIUM_FONT, fill=BLACK)
            y_offset += 20

        '''
        show_logo_url = streams[name]['showLogo']
        if show_logo_url:
            try:
                show_logo = Image.open(BytesIO(requests.get(show_logo_url).content)).resize((LOGO_SIZE, LOGO_SIZE))
                border = Image.new('RGB', (LOGO_SIZE+BORDER_SIZE*2, LOGO_SIZE+BORDER_SIZE*2), color=BORDER_COLOR)
                image.paste(border, (LOGO_X, LOGO_Y))
                image.paste(show_logo, (LOGO_X+BORDER_SIZE, LOGO_Y+BORDER_SIZE))
            except:
                pass
        '''

        # battery
        #display_battery(draw)

        safe_display(image) # display 
    
    else:
        if not restarting:
            display_one(name)

    
def display_one(name):
    highlight_color = BLUE #WHITE#BLUE #if name in favorites else BLUE if name not in reruns else GREEN

    bg_color = WHITE #BLUE if name in favorites else WHITE 
    image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT), color=bg_color)
    draw = ImageDraw.Draw(image)

    draw.rectangle([
            0, 0, 
            SCREEN_WIDTH, TOP_DIVIDER_Y
                        ], fill=highlight_color)

    # top header
    draw.rectangle([
        0, 0, 
        SCREEN_WIDTH, 17
        ], fill=YELLOW)   
    draw.rectangle([
        0, 17, 
        SCREEN_WIDTH, 17 + 1
        ], fill=BLACK)     

    # logo
    logo = streams[name]['logo_smallest']
    border = Image.new('RGB', (SMALLEST_LOGO_SIZE+BORDER_SIZE*2, SMALLEST_LOGO_SIZE+BORDER_SIZE*2), color=BORDER_COLOR)
    image.paste(border, (ONE_LOGO_X-BORDER_SIZE*2, ONE_LOGO_Y-BORDER_SIZE*2))
    image.paste(logo, (ONE_LOGO_X-BORDER_SIZE, ONE_LOGO_Y-BORDER_SIZE))
    if name in favorites:
        image.paste(star_smallest, (ONE_LOGO_X-BORDER_SIZE, ONE_LOGO_Y-BORDER_SIZE), star_smallest)
    if name not in reruns:
        image.paste(live_banner, (0,0), live_banner)

    # name
    draw.text((ONE_NAME_X, ONE_NAME_Y), calculate_text(name, font=LARGE_FONT, max_width=223, lines=1)[0], font=LARGE_FONT, fill=TEXT_COLOR)

    # location
    draw.text((ONE_LOC_X, ONE_LOC_Y), calculate_text(streams[name]['location'], font=MEDIUM_FONT, max_width=223, lines=1)[0], font=MEDIUM_FONT, fill=TEXT_COLOR_2)    

    # top divider
    divider = Image.new('RGB', (SCREEN_WIDTH,BORDER_SIZE), color=BORDER_COLOR)
    image.paste(divider, (0, TOP_DIVIDER_Y))

    # now playing
    y_offset = 0
    num_title_lines = 2
    info = streams[name]['oneLiner'].replace('&amp;','&').split(' - ')
    info = [i for i in info if i in list(set(info))]

    if len(info) == 1:
        num_title_lines = 4
    elif len(info) == 2:
        num_title_lines = 3

    title_lines = [i for i in calculate_text(info[0], font=BIGGEST_FONT, max_width=290, lines=num_title_lines) if i != '']

    if len(title_lines) == 3:
        num_info_lines = 1
    elif len(title_lines) == 1: 
        num_info_lines = 4
    else:
        num_info_lines = 2
    
    info_lines = [i for i in calculate_text(' - '.join(info[1:]), font=MEDIUM_FONT, max_width=290, lines=num_info_lines) if i != '']

    anchor = get_anchor(title_lines, info_lines, name not in reruns)
    avg_title_height = np.mean([height(i, LARGE_FONT) for i in title_lines])
    avg_info_height = np.mean([height(i, MEDIUM_FONT) for i in info_lines])

    for i in title_lines:
        draw.text((SHOW_INFO_X, anchor), i, font=LARGE_FONT, fill=BLACK)
        anchor += avg_title_height + 6

    anchor += 5

    if info_lines:
        for i in info_lines:
            draw.text((SHOW_INFO_X, anchor), i, font=MEDIUM_FONT, fill=BLACK)
            anchor += avg_info_height + 6

    # battery
    display_battery(draw)

    # time
    now = time.time()
    current_time = datetime.fromtimestamp(now, tz=user_tz)
    formatted_time = current_time.strftime("%a %b %d %I:%M %p").replace(' 0', '  ').lstrip('0')
    
    draw.text((13,3), formatted_time, font=SMALL_FONT, fill=BLACK)

    # wifi    
    display_wifi(image)

    safe_display(image)


def get_anchor(title, info, live):
    size = 0
    for line in title:
        size += height(line, LARGE_FONT) + 6
    if info:
        size += 5
        for line in info:
            size += height(line, MEDIUM_FONT) + 6

    section_height = SCREEN_HEIGHT - 16 - TOP_DIVIDER_Y if live else SCREEN_HEIGHT - TOP_DIVIDER_Y
    return TOP_DIVIDER_Y + round((section_height - size) // 2)


def display_battery(draw):
    if not battery:
        get_battery()
    if battery:
        battery_y = 4
        outer_sq = draw.rectangle([278, battery_y, 303, battery_y + 10], fill=BLACK)
        nipple = draw.rectangle([304, battery_y + 3, 305, battery_y + 7], fill=BLACK)
        battery_color = YELLOW if charging else WHITE
        inner_sq_bg = draw.rectangle([280, battery_y + 2, 277 + 24, battery_y + 8], fill=BLACK) 
        inner_sq = draw.rectangle([280, battery_y + 2, 277 + round(24*battery/100), battery_y + 8], fill=battery_color) 
        '''
        if battery == 100:
            draw.text((282, battery_y + 1), str(battery), font=SMALL_FONT, fill=BLACK)
        else:
            draw.text((286, battery_y + 1), str(battery), font=SMALL_FONT, fill=BLACK)
        '''

def get_wifi_strength():
    global wifi_strength, wifi_ssid
    try:
        result = subprocess.run(['iwconfig', 'wlan0'], 
                            stdout=subprocess.PIPE, text=True, timeout=2)
        result_lines = result.stdout.strip().split('\n')
        wifi_ssid = [i.split('ESSID:')[1].replace('"','').strip() for i in result_lines if 'ESSID:' in i][0]
        signal_strength = [i.split('Link Quality=')[1].split('/')[0] for i in result_lines if 'Link Quality=' in i][0]
        wifi_strength = int((float(signal_strength) / 70) * 100)
    except Exception as e:
        logging.info(e)
        wifi_ssid = "Not Found"
        wifi_strength = 0

def display_wifi(image):
    if not wifi_strength:
        get_wifi_strength()
    strength = 'low' if wifi_strength < 20 else 'med' if wifi_strength <= 50 else 'high'
    signal = Image.open(f'assets/wifi_{strength}.png').convert('RGBA')
    image.paste(signal, (260, 4), signal)
    logging.info(wifi_strength)

def toggle_stream(name):
    global play_status
    if name:
        if play_status == 'play':
            pause(show_icon=True)
        else:
            play(name, toggled=True)

def seek_stream(direction):
    global readied_stream 

    idx = stream_list.index(stream)
    
    if (readied_stream == None):
        readied_stream = stream
    else:
        idx = stream_list.index(readied_stream)
        if (direction == 1) and (idx==len(stream_list)-1):
            readied_stream = stream_list[0]
        elif (direction == -1) and (idx==0):
            readied_stream = stream_list[-1]
        else:
            readied_stream = stream_list[idx + direction]

    display_everything(readied_stream, readied=True)

def confirm_seek():
    global readied_stream, stream
    if readied_stream:
        if stream != readied_stream:
            #pause()
            stream = readied_stream
            play(stream)
        display_everything(stream)
        readied_stream = None

def show_volume_overlay(volume):
    global current_image

    if current_image:
        img = current_image.copy()
        draw = ImageDraw.Draw(img)
        
        total_bar_height = SCREEN_HEIGHT - TOP_DIVIDER_Y - 2
        volume_bar_end = TOP_DIVIDER_Y + 2 + total_bar_height * ((150-volume)/150)

        #logging.info(f'from {SCREEN_HEIGHT} to {volume_bar_end}')

        draw.rectangle([
            SCREEN_WIDTH-9, TOP_DIVIDER_Y+2, 
            SCREEN_WIDTH, SCREEN_HEIGHT
                        ], fill=BLACK)
        
        draw.rectangle([
            SCREEN_WIDTH-7, TOP_DIVIDER_Y+2, 
            SCREEN_WIDTH, SCREEN_HEIGHT
                        ], fill=BLACK)
        
        draw.rectangle([
            SCREEN_WIDTH-7, volume_bar_end, 
            SCREEN_WIDTH, SCREEN_HEIGHT
                        ], fill=YELLOW)
        
        safe_display(img)

def safe_restart():
    global restarting
    restarting = True
    image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))
    bg = Image.open(f'assets/updating.png') 
    image.paste(bg, (0, 0))
    safe_display(image)
    run(['sudo', '-u','scud','git', 'pull'], cwd='/home/scud/scud-radio')
    time.sleep(4)  
    backlight_off()
    run(['sudo','systemctl', 'restart','radio'])

def on_button_pressed():
    global button_press_time, rotated, button_press_times, held
    button_press_time = time.time()
    if readied_stream:
        confirm_seek()
    held = True
    rotated = False

button_press_times = []
def on_button_released():
     
    global button_press_times, rotated, held
    held = False
    current_time = time.time()
    if not readied_stream:
        set_last_volume(str(current_volume))

        button_press_times.append(current_time)
        button_press_times = [t for t in button_press_times if current_time - t <= 3.0]
        
        if len(button_press_times) >= 5:
            button_press_times = [] 
            safe_restart()
            return    

def toggle_favorite():
    global favorites, stream_list
    now = time.time()
    if not rotated:
        img = current_image.convert('RGBA')
        
        if stream in favorites:
            favorites = [i for i in favorites if i != stream]
            for i in list(reversed(favorite_images)):
                img.paste(i, (0, 0), i)
                disp.ShowImage(img)  
                img = current_image.convert('RGBA')
            img.paste(unfavorite, (0, 0), unfavorite)
            disp.ShowImage(img)
            set_favorites(favorites)
        else:
            favorites.append(stream)
            favorites = list(set(favorites))
            set_favorites(favorites)
            img.paste(unfavorite, (0, 0), unfavorite)
            disp.ShowImage(img)
            for i in favorite_images:
                img.paste(i, (0, 0), i)
                disp.ShowImage(img)           

        stream_list = stream_list = sorted([i for i in stream_list if i in favorites]) + sorted([i for i in stream_list if i not in favorites])
        time.sleep(0.3)
        display_one(stream)


def handle_rotation(direction):
    global rotated, current_volume, button_press_time, last_rotation
    rotated = True

    if click_button.is_pressed:
        if direction == 1: 
            current_volume = min(150, current_volume + volume_step)
        else: 
            current_volume = max(0, current_volume - volume_step)

        send_mpv_command({"command": ["set_property", "volume", current_volume]})
        #logging.info(f'volume: {current_volume}')
        show_volume_overlay(current_volume)

    else:
        if (time.time() - button_press_time > 1):
            last_rotation = time.time()
            seek_stream(direction)

failed_fetches = 0
def periodic_update():
    global screen_on, failed_fetches

    if screen_on and (time.time() - last_input_time > 120):
        screen_on = False
        backlight_off()
        pass
    else:
        try:
            info = requests.get('https://internetradioprotocol.org/info').json()
            for name, v in info.items():
                if name in streams:
                    streams[name].update(v)
            stream_list = get_stream_list(streams)
            failed_fetches = 0

            if not held and not readied_stream:
                display_everything(stream, update=True)
                
        except Exception as e:
            failed_fetches += 1
            if failed_fetches == 3:
                disp.clear()
                disp.reset()
                disp.close()
                subprocess.run(['sudo','systemctl','restart','radio'])
                sys.exit(0)
            pass
    
    threading.Timer(10, periodic_update).start()


def wake_screen():
    global screen_on, last_input_time, current_image
    last_input_time = time.time()
    if not screen_on:
        screen_on = True
        backlight_on()
        if current_image:
            #disp.display(current_image)
            disp.ShowImage(current_image) # for 2 inch
        else:
            display_scud()
        return True
    return False

def wrapped_action(func):
    def inner():
        if not wake_screen():
            func()
    return inner


def restart():
    backlight_off()
    run([
        'sudo',
        'systemctl',
        'stop',
        'radio'
    ])

from gpiozero import RotaryEncoder, Button

click_button = Button(26, bounce_time=0.05)
click_button.hold_time = 2
click_button.when_pressed = wrapped_action(lambda: on_button_pressed())
click_button.when_held = toggle_favorite
click_button.when_released = on_button_released

CLK_PIN = 5 
DT_PIN = 6   
rotor = RotaryEncoder(CLK_PIN, DT_PIN)
rotor.when_rotated_counter_clockwise = wrapped_action(lambda: handle_rotation(-1))
rotor.when_rotated_clockwise = wrapped_action(lambda: handle_rotation(1))

last_played = read_last_played()
if last_played in stream_list:
    play(last_played)
else:
    play_random()

periodic_update()

time_since_battery_check = 0
try:
    while True:
        if time_since_battery_check == 10:
            get_battery()
            time_since_battery_check = 0

        if screen_on and stream and readied_stream == None and restarting == False and rotated == False and held == False:
            #display_everything(stream)
            pass

        if readied_stream and last_rotation and (time.time() - last_rotation > 5) and restarting == False and held == False:
            readied_stream = None
            if screen_on and stream:
                display_everything(stream)
        
        time.sleep(1)
        time_since_battery_check += 1

except KeyboardInterrupt:
    if mpv_process:
        mpv_process.terminate()

    WIDTH = disp.width
    HEIGHT = disp.height
    img = Image.new("RGB", (320, 240), color="black")
    draw = ImageDraw.Draw(img)
    #disp.display(img)
    disp.ShowImage(img) # for 2 inch
