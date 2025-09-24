from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont, ImageSequence, ImageOps
from datetime import date, datetime, timezone, timedelta
from subprocess import Popen, run
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

import driver as LCD_2inch

# 2 inch
RST = 27
DC = 25
BL = 23
bus = 0 
device = 0 
current_bl = 100
disp = LCD_2inch.LCD_2inch()
disp.Init()
disp.clear()
disp.bl_DutyCycle(current_bl)

mpv_process = None
stream = None
readied_stream = None
last_rotation = None
screen_on = True
screen_dim = False
current_image = None
saved_image_while_paused = None
play_status = 'pause'
last_input_time = time.time()
first_display = True
current_volume = 60
volume_step = 10
button_press_time = 0
rotated = False
battery = None
charging = False
restarting = False
held = False
user_tz = 'UTC'
wifi_strength = None
first_boot = True
selector = 'red'
has_displayed_once = False
volume_overlay_showing = False

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

WHITE = (255,255,255)
BLACK = (0,0,0)
YELLOW = (255,255,0)
BLUE = (0,187,255)
GREEN = (0,231,192)
GREY = (100,100,100)
ORANGE = (255,128,0)
PURPLE = (134,97,245)
RED = (255,71,71)

SMALL_FONT = ImageFont.truetype("assets/Archivo-Light.ttf", 13)
MEDIUM_FONT = ImageFont.truetype("assets/Archivo-Light.ttf", 18)
LARGE_FONT = ImageFont.truetype("assets/Archivo-Bold.ttf",28)

unfavorite = Image.open('assets/unfavorited.png').convert('RGBA')
favorite_images = [Image.open('assets/favorited1.png').convert('RGBA'), 
                   Image.open('assets/favorited2.png').convert('RGBA'), 
                   Image.open('assets/favorited3.png').convert('RGBA'), 
                   Image.open('assets/favorited4.png').convert('RGBA'),
                   Image.open('assets/favorited5.png').convert('RGBA')]

star_60 = Image.open('assets/star_60.png').convert('RGBA')
star_96 = Image.open('assets/star_96.png').convert('RGBA')
star_25 = Image.open('assets/star_25.png').convert('RGBA')

live_60 = Image.open('assets/live_60.png').convert('RGBA')
live_96 = Image.open('assets/live_96.png').convert('RGBA')
live_25 = Image.open('assets/live_25.png').convert('RGBA')

#selector_list = ['red','orange','purple','white','green','yellow']
#selectors = {}
#for i in selector_list:
#    selectors[i] = Image.open(f'assets/selector_{i}.png').convert('RGBA')

mainview = Image.open('assets/mainview.png').convert('RGBA')
logoview = Image.open('assets/logoview.png').convert('RGBA')
live_overlay_1 = Image.open('assets/liveoverlay1.png').convert('RGBA')
charging_overlay = Image.open('assets/chargingoverlay.png').convert('RGBA')
#live_overlay_2 = Image.open('assets/liveoverlay2.png').convert('RGBA')
selector_bg = Image.open(f'assets/selector.png').convert('RGBA')
selector_live_overlay = Image.open('assets/selectorliveoverlay.png').convert('RGBA')

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
        return 60
    
    try:
        with open(volume_file, 'r') as f:
            vol = int(f.read())
        return vol
    except:
        return 60

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
    scud_path = Path(LIB_PATH)
    scud_path.mkdir(parents=True, exist_ok=True)
    
    played_file = scud_path / 'last_played.txt'

    if not played_file.exists():
        played_file.touch() 
        
    with open(played_file, 'w') as file:
        file.write(name)


def read_last_played():
    scud_path = Path(LIB_PATH)
    scud_path.mkdir(parents=True, exist_ok=True)
    
    played_file = scud_path / 'last_played.txt'
    if not played_file.exists():
        played_file.touch() 
        return None
    try:
        with open(played_file, 'r') as f:
            last_played = f.read()
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

    image = Image.new('RGBA', (SCREEN_WIDTH, SCREEN_HEIGHT))
    bg = Image.open(f'assets/scud_splash_1.png') 
    image.paste(bg, (0, 0))
    safe_display(image)  

    '''
    for i in 'welcome':
            
        bg = Image.open(f'assets/scud_{i}.png') 
        image.paste(bg, (0, 0))
        safe_display(image)  
        time.sleep(0.05)


    #time.sleep(1)
    '''

    #bg = Image.open(f'assets/scud_splash_1_black.png') 
    #image.paste(bg, (0, 0))
    #safe_display(image)  

    global user_tz

    timezone_name = get_timezone_from_ip()
    user_tz = pytz.timezone(timezone_name)
    now = time.time()
    current_time = datetime.fromtimestamp(now, tz=user_tz)
    current_hour = current_time.hour

    last_played = read_last_played()
    volume = round((get_last_volume()/150)*100)
    get_battery()

    '''

    greeting = 'Hello'
    size = 192
    bbox = [64, 120, 64 + size, 120 + size]

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

    draw = ImageDraw.Draw(image)
    draw.text((10, 0), greeting + ",", font=LARGE_FONT, fill=WHITE) 
    draw.text((10, 23),  "Friend.", font=LARGE_FONT, fill=WHITE) 
    draw.text((10, 193), f'Last Played: {last_played}', font=SMALL_FONT, fill=WHITE)
    draw.text((10, 203), f'Internet: Connected', font=SMALL_FONT, fill=WHITE)
    draw.text((10, 213), f'Battery: {battery}%', font=SMALL_FONT, fill=WHITE)
    draw.text((10, 223), f'Volume: {volume}%', font=SMALL_FONT, fill=WHITE)
    safe_display(image)
    '''


def backlight_on():
    if disp:
        if current_image:
            safe_display(current_image)
        else:
            display_scud()
        disp.bl_DutyCycle(100)

def backlight_off():
    if disp:
        disp.bl_DutyCycle(0)
        disp.clear()

def backlight_dim():
    if disp:
        disp.bl_DutyCycle(20)

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

def send_mpv_command(cmd, max_retries=10, retry_delay=1):
    for attempt in range(max_retries):
        try:
            logging.info(f"Sending MPV command: {cmd}")
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(2)
                s.connect("/tmp/mpvsocket")
                s.sendall((json.dumps(cmd) + '\n').encode())
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
        full_img_path = Path(LIB_PATH) / f'{name}_logo_176.pkl'
        if not full_img_path.exists():
            need_imgs.append(name)
        else:
            file_stat = full_img_path.stat()
            file_age_seconds = time.time() - file_stat.st_mtime
            file_age_days = file_age_seconds / (24 * 3600) 

            if file_age_days > 7:  # refresh if older than 7 days
                need_imgs.append(name)
            else:
                for i in ['25','60','96','176']:
                    with open(Path(LIB_PATH) / f'{name}_logo_{i}.pkl', 'rb') as f:
                        image = pickle.load(f).convert('RGBA')
                        
                        active[name][f'logo_{i}'] = image

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
            logo_96 = img.resize((96,  96)).convert('RGBA')#.convert('LA')
            logo_60 = img.resize((60,  60)).convert('RGBA')#.convert('LA')
            logo_25 = img.resize((25,  25)).convert('RGBA')#.convert('LA')
            logo_176 = img.resize((176, 176)).convert('RGBA')

            # save images to dict
            active[name]['logo_96'] = logo_96
            active[name]['logo_60']  = logo_60
            active[name]['logo_25'] = logo_25
            active[name]['logo_176'] = logo_176

            # save images to lib
            for i in ['96','60','25','176']:
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

    play_status = 'pause'

def play(name, toggled=False):
    global play_status, stream, first_boot
    play_status = 'play'
    stream = name

    if toggled:
        safe_display(saved_image_while_paused)
        send_mpv_command({"command": ["set_property", "volume", current_volume]})
    else:
        #logging.info(f'attempting to play {name}')
        stream_url = streams[name]['streamLink']
        if first_boot:
            send_mpv_command({"command": ["loadfile", stream_url]})
            first_boot = False
        else:
            send_mpv_command({"command": ["loadfile", stream_url, 'replace']})
        send_mpv_command({"command": ["set_property", "volume", current_volume]})

    write_to_tmp_os_path(name)


def play_random():
    global stream, play_status
    available_streams = [i for i in stream_list if i != stream]
    chosen = random.choice(available_streams)
    display_everything(0, chosen)
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
    

def draw_angled_text(text, font, angle, image, coords, color):
    temp_img = Image.new('L', (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)
    bbox = temp_draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    txt = Image.new('L', (text_width, text_height))
    d = ImageDraw.Draw(txt)
    d.text((-bbox[0], -bbox[1]), text, font=font, fill=255)
    
    w = txt.rotate(angle, expand=1)
    image.paste(ImageOps.colorize(w, (0,0,0), color), coords, w)


def display_everything(direction, name, update=False, readied=False, pushed=False):
    global streams, play_status, first_display, selector
    
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

        image = selector_bg.copy()
        draw = ImageDraw.Draw(image)  

        location = streams[name]['location']
        name_line = calculate_text(name, LARGE_FONT, 275, 1)
        title_lines = calculate_text(streams[name]['oneLiner'].replace('&amp;','&'), MEDIUM_FONT, 250, 2)

        # draw name and underline
        draw.text((38, 12 - 7), name_line[0], font=LARGE_FONT, fill=WHITE)
        draw.rectangle([38, 38, 38 + width(name_line[0], LARGE_FONT), 38], fill=WHITE)

        # draw location
        draw.text((38, 43), location, font=MEDIUM_FONT, fill=WHITE)

        # draw info
        y_offset = 0
        for i in title_lines:
            draw.text((54, 70 + y_offset), i, font=MEDIUM_FONT, fill=WHITE)
            y_offset += 20

        # label
        #draw.rectangle([label_start, 216, label_end, 233], fill=BLACK)
        #draw.rectangle([label_start, 217, label_end, 229], fill=WHITE)
        #draw.text((label_start + 1, 217), name, font=SMALL_FONT, fill=BLACK)

        # draw logo
        #tick_mark_start = mark_start
        #mark_start = label_start - 2 #round(mark_start - 67/2)
        #draw.rectangle([mark_start, 131 + 67, mark_start + 67, 131 + 63], fill=WHITE)
        #draw.rectangle([mark_start + 1, 131 + 1, mark_start + 67 - 1, 131 + 67 - 1], fill=BLACK)
        if pushed:
            logo_position = (129, 143)
            logo = streams[name]['logo_60']            
            this_star = star_60.copy()
            this_live = live_60.copy()
        else:
            logo_position = (111, 125)
            logo = streams[name]['logo_96']
            this_star = star_96.copy()
            this_live = live_96.copy()
        
        image.paste(logo, logo_position)

        #if name in favorites:
        #    image.paste(this_star, logo_position, this_star)
        #if name not in reruns:
        #    image.paste(this_live, logo_position, this_live)

        # line
        #draw.line([tick_mark_start + 1, 216, round(mark_start + 67/2), 131 + 67], fill=WHITE, width=2)
        
        # prev and next
        #prev_position = (mark_start - 40 - 2, 155)
        #next_position = (mark_start + 68 + 2, 155)
        prev_position = (39, 161)
        next_position = (219, 161)
        prev_next_rotation = 0
        prev = streams[prev_stream]['logo_60']#.rotate(prev_next_rotation, expand=True)
        next = streams[next_stream]['logo_60']#.rotate(-prev_next_rotation, expand=True)
        image.paste(prev, prev_position, prev)
        image.paste(next, next_position, next)
        
        if prev_stream in favorites:
            prev_star = star_60.copy().rotate(prev_next_rotation, expand=True)
            #image.paste(prev_star, prev_position, prev_star)
        if next_stream in favorites:
            next_star = star_60.copy().rotate(-prev_next_rotation, expand=True)
            #image.paste(next_star, next_position, next_star)
        if prev_stream not in reruns:
            prev_live = live_60.copy().rotate(prev_next_rotation, expand=True)
            #image.paste(prev_live, prev_position, prev_live)
        if next_stream not in reruns:
            next_live = live_60.copy().rotate(-prev_next_rotation, expand=True)
            #image.paste(next_live, next_position, next_live)

        # double prev and next
        #double_prev_position = (mark_start - 40 - 25 - 2 - 6, 170)
        #double_next_position = (mark_start + 68 + 40 + 2 + 6, 170)
        double_prev_position = (7, 196)
        double_next_position = (286, 196)
        double_prev_next_rotation = 0
        double_prev = streams[double_prev_stream]['logo_25']#.rotate(double_prev_next_rotation, expand=True)
        double_next = streams[double_next_stream]['logo_25']#.rotate(-double_prev_next_rotation, expand=True)

        #draw_angled_text(double_prev_stream, MEDIUM_FONT, -64, image, (27,210), BLACK)
        #draw_angled_text(double_next_stream, MEDIUM_FONT, -116, image, (264,208), BLACK)
        
        image.paste(double_prev, double_prev_position, double_prev)
        if double_prev_stream in favorites:
            double_prev_star = star_25.copy()#.rotate(double_prev_next_rotation, expand=True)
            ##image.paste(double_prev_star, double_prev_position, double_prev_star)
        if double_prev_stream not in reruns:
            double_prev_live = live_25.copy()#.rotate(double_prev_next_rotation, expand=True)
            #image.paste(double_prev_live, double_prev_position, double_prev_live)

        image.paste(double_next, double_next_position, double_next)
        if double_next_stream in favorites:
            double_next_star = star_25.copy()#.rotate(-double_prev_next_rotation, expand=True)
            #image.paste(double_next_star, double_next_position, double_next_star)
        if double_next_stream not in reruns:
            double_next_live = live_25.copy()#.rotate(-double_prev_next_rotation, expand=True)
            #image.paste(double_next_live, double_next_position, double_next_live)

        # draw mark
        tick_width = 0
        mark_width = round(SCREEN_WIDTH / len(stream_list))
        tick_start = 0
        for i in stream_list:
            draw.rectangle([tick_start, 231, tick_start + tick_width, 232], fill=WHITE)
            tick_start += mark_width

        bar_width = 1
        mark_start = round(stream_list.index(name) * mark_width)
        label_width = round(width(name, SMALL_FONT) + 2)
        label_start = mark_start + (2 * bar_width) + 4
        label_end = label_start + label_width

        if label_end > 320:
            label_start = mark_start - label_width - (bar_width) - 2
            label_end = label_start + label_width

        # marker
        draw.rectangle([mark_start, 226, mark_start + bar_width, 237], fill=WHITE)
        #draw.rectangle([mark_start - mark_width, 229, mark_start - mark_width + bar_width, 234], fill=WHITE)
        #draw.rectangle([mark_start + mark_width, 229, mark_start + mark_width + bar_width, 234], fill=WHITE)

        safe_display(image)
    
    else:
        if not restarting:
            display_one(name)

    
def display_one(name):
    global has_displayed_once 

    # logo
    logo = streams[name]['logo_60']
    first_pixel_color = logo.getpixel((2,2))
    pixel_array = np.asarray(first_pixel_color)
    white_array = np.asarray([255, 255, 255, 255])
    black_array = np.asarray([0, 0, 0, 255])

    distance_to_black = np.sum(np.abs(black_array - pixel_array))
    distance_to_white = np.sum(np.abs(white_array - pixel_array))
    if distance_to_black * 0.7 <= distance_to_white:
        trim_color = WHITE
    else:
        trim_color = BLACK

    #if first_pixel_color == (255, 255, 255) or first_pixel_color == (255, 255, 255, 255):
    #   first_pixel_color = (171, 171, 171)
    #   trim_color = BLACK

    image = Image.new('RGBA',(320, 240), color=first_pixel_color)
    draw = ImageDraw.Draw(image)  

    draw.rectangle([13, 9, 78, 74], fill=trim_color)
    draw.rectangle([13 + 1, 9 + 1, 78 - 1, 74 - 1], fill=first_pixel_color)
    logo_position = (16, 12)
    image.paste(logo, logo_position)
    #if name in favorites:
    #    image.paste(star_60, logo_position, star_60)
    #if name not in reruns:
        #draw.rectangle([logo_position[0] + 30, logo_position[1] + 46, logo_position[0] + 30 + 31, logo_position[1] + 46 + 16], fill=first_pixel_color)
        #draw.rectangle([logo_position[0] + 31, logo_position[1] + 47, logo_position[0] + 30 + 31, logo_position[1] + 46 + 16], fill=RED)
        #draw.text((logo_position[0] + 33, logo_position[1] + 49), "LIVE", fill=WHITE, font=SMALL_FONT)
    #    image.paste(live_60, (16, 12), live_60)

    # bottom bar
    draw.rectangle([0, 222, 320, 222], fill=BLACK)
    draw.rectangle([0, 223, 320, 240], fill=WHITE)

    # name and underline
    name_line = calculate_text(name, font=LARGE_FONT, max_width=225, lines=1)[0]
    draw.text((92, 20 - 7), name_line, font=LARGE_FONT, fill=trim_color)
    draw.rectangle([92, 47, 92 + width(name_line, LARGE_FONT), 47], fill=trim_color)
   
    # location
    draw.text((92, 52), calculate_text(streams[name]['location'], font=MEDIUM_FONT, max_width=223, lines=1)[0], font=MEDIUM_FONT, fill=trim_color)    

    # now playing
    y_offset = 0
    num_title_lines = 2
    info = streams[name]['oneLiner'].replace('&amp;','&').split(' - ')
    info = [i for i in info if i in list(set(info))]

    if len(info) == 1:
        num_title_lines = 4
    elif len(info) == 2:
        num_title_lines = 3

    title_lines = [i for i in calculate_text(info[0], font=LARGE_FONT, max_width=290, lines=num_title_lines) if i != '']

    if len(title_lines) == 3:
        num_info_lines = 1
    elif len(title_lines) == 1: 
        num_info_lines = 4
    else:
        num_info_lines = 2
    
    info_lines = [i for i in calculate_text(' - '.join(info[1:]), font=MEDIUM_FONT, max_width=290, lines=num_info_lines) if i != '']

    anchor = get_anchor(title_lines, info_lines, name not in reruns)
    avg_title_height = sum(height(i, LARGE_FONT) for i in title_lines) / len(title_lines) if title_lines else 0
    avg_info_height = sum(height(i, MEDIUM_FONT) for i in info_lines) / len(info_lines) if info_lines else 0

    for i in title_lines:
        draw.text((14, anchor), i, font=LARGE_FONT, fill=trim_color)
        anchor += avg_title_height + 6

    anchor += 5

    if info_lines:
        for i in info_lines:
            draw.text((14, anchor), i, font=MEDIUM_FONT, fill=trim_color)
            anchor += avg_info_height + 6

    # battery
    display_battery(draw, image)

    # time
    now = time.time()
    current_time = datetime.fromtimestamp(now, tz=user_tz)
    formatted_time = current_time.strftime("%a %b %d %I:%M %p").replace(' 0', '  ').lstrip('0')
    
    draw.text((13,224), formatted_time, font=SMALL_FONT, fill=BLACK)

    # wifi    
    display_wifi(image)

    safe_display(image)
    has_displayed_once = True


def display_ambient(name):
    global screen_dim

    # logo
    logo = streams[name]['logo_176']
    first_pixel = logo.getpixel((5,5))

    image = Image.new('RGB',(SCREEN_WIDTH, SCREEN_HEIGHT), color = first_pixel)
    image.paste(logo, (72, 32))

    safe_display(image)

    screen_dim = True


def get_anchor(title, info, live):
    size = 0
    for line in title:
        size += height(line, LARGE_FONT) + 6
    if info:
        size += 5
        for line in info:
            size += height(line, MEDIUM_FONT) + 6

    section_height = 215 - 77
    return 77 + round((section_height - size) // 2)


def display_battery(draw, image):
    if not battery:
        get_battery()
    if battery:
        outer_sq = draw.rectangle([280, 227, 300, 237], fill=BLACK)
        nipple = draw.rectangle([300, 229, 301, 235], fill=BLACK)
        inner_white = draw.rectangle([281, 228, 299, 236], fill=WHITE) 
        inner_sq = draw.rectangle([282, 229, 282 + round(15*battery/100), 235], fill=BLACK) 

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
    image.paste(signal, (260, 227), signal)

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

    display_everything(direction, readied_stream, readied=True)

def confirm_seek():
    global readied_stream, stream
    if readied_stream:
        if stream != readied_stream:
            #pause()
            stream = readied_stream
            play(stream)
        display_everything(0, stream)
        readied_stream = None

def show_volume_overlay(volume):
    global current_image, volume_overlay_showing
    if current_image:
        img = current_image.copy()
        time.sleep(0.008)  

        img_background = img.getpixel((5,5))
        if img_background == (255, 255, 255, 255) or img_background == (255, 255, 255):
            trim_color = BLACK
        else:
            trim_color = WHITE
        
        draw = ImageDraw.Draw(img)
        total_bar_height = SCREEN_HEIGHT
        volume_bar_end = total_bar_height * ((150-volume)/150)
        draw.rectangle([SCREEN_WIDTH-15, 222, SCREEN_WIDTH, SCREEN_WIDTH-15 + 1], fill=BLACK)
        draw.rectangle([SCREEN_WIDTH-14, 0, SCREEN_WIDTH, SCREEN_HEIGHT], fill=img_background)

        # border
        tick_gap = round(SCREEN_HEIGHT / (150/ volume_step))
        tick_start = 0
        tick_height = 0
        while tick_start < SCREEN_HEIGHT:
            draw.rectangle([313, tick_start, 317, tick_start + tick_height], fill=trim_color)
            tick_start += tick_gap

        # volume fill
        draw.rectangle([SCREEN_WIDTH-10, volume_bar_end, SCREEN_WIDTH, SCREEN_HEIGHT], fill=trim_color)

        #draw.rectangle([SCREEN_WIDTH-9, 215, SCREEN_WIDTH, SCREEN_HEIGHT], fill=WHITE)

        time.sleep(0.005)  
        safe_display(img)
        time.sleep(0.005)
        volume_overlay_showing = True

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
    run(['sudo','systemctl', 'restart','splash'])

button_released_time = time.time()

def on_button_pressed():
    global button_press_time, rotated, button_press_times, held, button_released_time, last_input_time
    last_input_time = time.time()
    button_press_time = time.time()
    button_released_time = None
    if readied_stream:
        display_everything(0, readied_stream, readied=True, pushed=True)
    held = True
    rotated = False

button_press_times = []
def on_button_released():
    global button_press_times, rotated, held, button_released_time
    held = False
    current_time = time.time()
    button_released_time = current_time
    if readied_stream:
        display_everything(0, readied_stream, readied=True, pushed=False)
        confirm_seek()
    else:
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
        img = current_image.copy().convert('RGBA')
        
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
    global rotated, current_volume, button_press_time, last_rotation, screen_on, screen_dim, last_input_time
    rotated = True
    last_input_time = time.time()

    if click_button.is_pressed:
        if direction == 1: 
            if current_volume == 0:
                backlight_on()
                screen_on = True
            current_volume = min(150, current_volume + volume_step)
        else: 
            current_volume = max(0, current_volume - volume_step)
            if current_volume == 0:
                backlight_off()
                screen_on = False

        show_volume_overlay(current_volume)
        send_mpv_command({"command": ["set_property", "volume", current_volume]})

    else:
        if button_released_time and (time.time() - button_released_time > 0.3):
            last_rotation = time.time()
            if screen_dim:
                display_one(stream)
            else:
                seek_stream(direction)

failed_fetches = 0
time_since_last_update = 0
def periodic_update():
    global screen_on, failed_fetches, time_since_last_update

    if not charging and screen_on == False and current_volume == 0 and (time.time() - last_input_time > 900):
        subprocess.run(['sudo','systemctl', 'start', 'shutdown'])

    if screen_on and has_displayed_once and stream and (time.time() - last_input_time > 20):
        display_ambient(stream)

    if screen_on and (time.time() - last_input_time > 600):
        screen_on = False
        backlight_off()
        pass
    else:
        if time_since_last_update == 15:
            try:
                info = requests.get('https://internetradioprotocol.org/info').json()
                for name, v in info.items():
                    if name in streams:
                        streams[name].update(v)
                stream_list = get_stream_list(streams)
                failed_fetches = 0
                    
            except Exception as e:
                failed_fetches += 1
                if failed_fetches == 3:
                    disp.clear()
                    disp.reset()
                    disp.close()
                    subprocess.run(['sudo','systemctl','restart','radio'])
                    sys.exit(0)
                pass

        if not held and not readied_stream and not screen_dim:
            display_everything(0, stream, update=True)

        time_since_last_update = 0
    
    time_since_last_update += 5
    threading.Timer(5, periodic_update).start()

def wake_screen():
    global screen_on, screen_dim, last_input_time, current_image
    last_input_time = time.time()
    if (not screen_on) or screen_dim:
        screen_on = True
        screen_dim = False
        backlight_on()
        if stream:
            display_one(stream)
        else:
            display_scud()
        return True
    return False

def wrapped_action(func, direction=0):
    def inner():
        if not click_button.is_pressed and current_volume == 0 and direction == -1:
            func()
        elif click_button.is_pressed and current_volume == 0 and direction == -1:
            func()
        else:
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
rotor.when_rotated_counter_clockwise = wrapped_action(lambda: handle_rotation(-1), -1)
rotor.when_rotated_clockwise = wrapped_action(lambda: handle_rotation(1), 1)

last_played = read_last_played()
if last_played in stream_list:
    play(last_played)
else:
    play_random()
    
display_everything(0, stream)
last_input_time = time.time()
periodic_update()

time_since_battery_check = 0
live_overlay_version = 1
try:
    while True:
        if time_since_battery_check == 20:
            get_battery()
            time_since_battery_check = 0

        if (readied_stream or volume_overlay_showing) and last_rotation and (time.time() - last_rotation > 5) and restarting == False and held == False:
            readied_stream = None
            volume_overlay_showing = False
            if screen_on and stream and not screen_dim:
                display_everything(0, stream)

        #if stream and not readied_stream and not restarting and not held:
            #image = current_image.copy()
            # toggle live overlay version
            #if live_overlay_version == 1:
            #    image.paste(live_overlay_1, (0,0), live_overlay_1)
            #    live_overlay_version = 2
            #else:
            #    image.paste(live_overlay_2, (0,0), live_overlay_2)
            #    live_overlay_version = 1
            #safe_display(image)

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
