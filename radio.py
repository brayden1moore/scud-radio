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

from functools import lru_cache

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
LARGE_FONT = ImageFont.truetype("assets/Archivo-Light.ttf",42)
LARGE_ISH_FONT = ImageFont.truetype("assets/Archivo-Bold.ttf",28)
LARGE_FONT_THIN = ImageFont.truetype("assets/Archivo-Light.ttf",28)

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

LIB_PATH = "/var/lib/scud-radio"

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

def display_scud():

    image = Image.new('RGBA', (SCREEN_WIDTH, SCREEN_HEIGHT))
    bg = Image.open(f'assets/scud_splash_1.png') 
    image.paste(bg, (0, 0))
    disp.ShowImage(image)

    global user_tz

    timezone_name = get_timezone_from_ip()
    user_tz = pytz.timezone(timezone_name)
    now = time.time()
    current_time = datetime.fromtimestamp(now, tz=user_tz)
    current_hour = current_time.hour

    last_played = read_last_played()
    volume = round((get_last_volume()/150)*100)
    get_battery()

display_scud()

def angled_sine_wave(x):
    linear = x
    amplitude = 40 #* np.sin(np.pi * x / 320)
    wave_frequency = 5
    sine_component = amplitude * np.sin(2 * np.pi * wave_frequency * x / 320)
    y = 120 + sine_component
    return y

def display_logos():
    lib_path = Path(LIB_PATH)
    small_logos = [i for i in os.listdir(lib_path) if '25.pkl' in i]
    img = Image.new('RGB', (320, 240), color=WHITE)
    draw = ImageDraw.Draw(img)
    x_offset = 0
    y_offset = 0
    
    for idx, i in enumerate(small_logos):
        with open(lib_path / i, 'rb') as f:
            logo = pickle.load(f)

        t = idx / len(small_logos)
        x_offset = t * 295
        y_offset = angled_sine_wave(x_offset)
        draw.rectangle([round(x_offset), round(y_offset), round(x_offset)+25, round(y_offset)+25], outline=BLACK, width=1)
        img.paste(logo, (round(x_offset), round(y_offset)))
        x_offset += 295 / len(small_logos)
    
        disp.ShowImage(img)

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


def backlight_on():
    global screen_on
    if disp:
        if current_image:
            safe_display(current_image)
        else:
            display_scud()
        time.sleep(0.2)
        disp.bl_DutyCycle(100)
        screen_on = True

def backlight_off():
    global screen_on
    if disp:
        disp.bl_DutyCycle(0)
        #disp.clear()
        screen_on = False

def backlight_dim():
    if disp:
        disp.bl_DutyCycle(20)

mpv_process = Popen([
    "mpv",
    "--idle=yes",
    "--no-video",
    "--quiet",
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
    active = {n: v for n, v in info.items() if v['hidden']!=True}
    
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
                        image = pickle.load(f).convert('RGB')
                        
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
            logo_96 = img.resize((96,  96)).convert('RGB')#.convert('LA')
            logo_60 = img.resize((60,  60)).convert('RGB')#.convert('LA')
            logo_25 = img.resize((25,  25)).convert('RGB')#.convert('LA')
            logo_176 = img.resize((176, 176)).convert('RGB')

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
    stream_list = sorted(list(streams.keys()), key=str.casefold)
    reruns = [i for i in stream_list if streams[i]['status'] == 'Re-Run']
    
    if favorites:
        #fav_start_idx = round(len(stream_list) / 2) - round(len(favorites) / 2)
        #front_half = [i for i in stream_list if i not in favorites][:fav_start_idx]
        #back_half = [i for i in stream_list if i not in favorites and i not in front_half]
        stream_list =  sorted(favorites, key=str.casefold) + sorted([i for i in stream_list if i not in favorites], key=str.casefold)
    
    return stream_list

streams = get_streams()
stream_list = get_stream_list(streams)

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

@lru_cache(maxsize=128)
def calculate_text_cached(text, font_name, width, lines):
    return calculate_text(text, font_name, width, lines)

base_layer = Image.new('RGBA', (SCREEN_WIDTH, SCREEN_HEIGHT), color=BLACK)
start_x = 0
logo_chunk_start = 35
logo_chunk_start_x = 12 + start_x
og_logo_position = (111, logo_chunk_start - 14 - 4)
logo_position = og_logo_position

def display_everything(direction, name, update=False, readied=False, pushed=False, silent=False):
    global streams, play_status, first_display, selector, start_x, currently_displaying
    
    if readied and not restarting:
    #if not restarting:
        now = time.time()

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

        image = Image.new('RGBA', (SCREEN_WIDTH, SCREEN_HEIGHT), color=BLACK)
        draw = ImageDraw.Draw(image) 
        
        currently_displaying = 'everything'
        if not readied:
            display_bar(y=4, draw=draw)

        location = streams[name]['location']
        title_lines = calculate_text(streams[name]['oneLiner'].replace('&amp;','&'), MEDIUM_FONT, 315, 1)

        # draw name and underline

        name_chunk_start = 240 - 80
        name_chunk_start_x = 12 + start_x
        name_line = calculate_text(name, LARGE_FONT_THIN, 315, 1)
        draw.rectangle([name_chunk_start_x, name_chunk_start - 1, name_chunk_start_x + width(name_line[0], LARGE_FONT_THIN), name_chunk_start + height('S', LARGE_FONT_THIN)], fill=BLACK) # bg
        draw.text((name_chunk_start_x - 1, name_chunk_start - 1), name_line[0], font=LARGE_FONT_THIN, fill=WHITE) 
        draw.rectangle([name_chunk_start_x, name_chunk_start + 30, name_chunk_start_x + width(name_line[0], LARGE_FONT_THIN), name_chunk_start + 30], fill=WHITE) # ul

        # draw info
        y_offset = 0
        for i in title_lines:
            draw.text((name_chunk_start_x, name_chunk_start + 33 + y_offset), i, font=MEDIUM_FONT, fill=WHITE)
            y_offset += 20

        # draw location
        draw.rectangle([name_chunk_start_x, name_chunk_start + 54, name_chunk_start_x + width(location, MEDIUM_FONT), name_chunk_start + 55 + height('S', MEDIUM_FONT)], fill=BLUE) # bg
        draw.text((name_chunk_start_x, name_chunk_start + 52), location, font=MEDIUM_FONT, fill=BLACK)
        
        genre_start = name_chunk_start_x + width(location, MEDIUM_FONT)
        genres = streams[name]['genres']
        genre_x_offset = 5
        if genres:
            genre_widths = [width(g, MEDIUM_FONT) for g in genres]
            genre_x_offset = 5
            for genre, genre_width in zip(genres, genre_widths):
                draw.rectangle([genre_start + genre_x_offset, name_chunk_start + 54, genre_start + genre_x_offset + genre_width, name_chunk_start + 55 + height('S', MEDIUM_FONT)], fill=GREEN) # bg
                draw.text((genre_start + genre_x_offset, name_chunk_start + 52), genre, font=MEDIUM_FONT, fill=BLACK)
                genre_x_offset += genre_width + 5


        # logos
        logo = streams[name]['logo_96']
        image.paste(logo, logo_position)

        if name in favorites:
            this_star = star_96.copy()
            image.paste(this_star, og_logo_position, this_star)
        if streams[name]['status'] == 'Live':
            this_live = live_96.copy()
            image.paste(this_live, og_logo_position, this_live)
        
        draw.rectangle([og_logo_position[0], og_logo_position[1], og_logo_position[0]+96, og_logo_position[1]+96], outline=WHITE, width=1) # border

        prev_position = (39, logo_chunk_start + 22 - 4)
        next_position = (219, logo_chunk_start + 22 - 4)
        prev_next_rotation = 0
        prev = streams[prev_stream]['logo_60']
        next = streams[next_stream]['logo_60']
        image.paste(prev, prev_position)
        draw.rectangle([prev_position[0],prev_position[1], prev_position[0] + 60, prev_position[1] + 60], outline=WHITE, width=1)
        image.paste(next, next_position)
        draw.rectangle([next_position[0],next_position[1], next_position[0] + 60, next_position[1] + 60], outline=WHITE, width=1)

        if prev_stream in favorites:
            prev_star = star_60.copy().rotate(prev_next_rotation, expand=True)
            image.paste(prev_star, prev_position, prev_star)
        if next_stream in favorites:
            next_star = star_60.copy().rotate(-prev_next_rotation, expand=True)
            image.paste(next_star, next_position, next_star)
        if streams[prev_stream]['status'] == "Live":
            prev_live = live_60.copy().rotate(prev_next_rotation, expand=True)
            image.paste(prev_live, prev_position, prev_live)
        if streams[next_stream]['status'] == "Live":
            next_live = live_60.copy().rotate(-prev_next_rotation, expand=True)
            image.paste(next_live, next_position, next_live)

        # double prev and next
        double_prev_position = (7, logo_chunk_start + 57 - 4)
        double_next_position = (286, logo_chunk_start + 57 - 4)
        double_prev_next_rotation = 0
        double_prev = streams[double_prev_stream]['logo_25']
        double_next = streams[double_next_stream]['logo_25']
        
        image.paste(double_prev, double_prev_position)
        draw.rectangle([double_prev_position[0],double_prev_position[1], double_prev_position[0] + 25, double_prev_position[1] + 25], outline=WHITE, width=1)
        if double_prev_stream in favorites:
            double_prev_star = star_25.copy()
            image.paste(double_prev_star, double_prev_position, double_prev_star)
        if streams[double_prev_stream]['status'] == "Live":
            double_prev_live = live_25.copy()
            image.paste(double_prev_live, double_prev_position, double_prev_live)

        image.paste(double_next, double_next_position)
        draw.rectangle([double_next_position[0],double_next_position[1], double_next_position[0] + 25, double_next_position[1] + 25], outline=WHITE, width=1)
        if double_next_stream in favorites:
            double_next_star = star_25.copy()
            image.paste(double_next_star, double_next_position, double_next_star)
        if streams[double_next_stream]['status'] == "Live":
            double_next_live = live_25.copy()
            image.paste(double_next_live, double_next_position, double_next_live)

        # draw mark
        if readied:
            tick_locations = {}

            tick_width = 1
            padding = 12 + 6
            total_ticks = len(stream_list)
            total_span = SCREEN_WIDTH - (2 * padding)
            mark_width = round(total_span / (total_ticks))
            tick_start = padding  
            tick_bar_height = 25
            tick_bar_start = logo_chunk_start + 94
            tick_height = 3
            tick_start_y = (tick_bar_start + tick_bar_height / 2) - 2

            square_start = padding - 5
            square_end = padding + mark_width * len(favorites) - 1
            if favorites:
                tick_color = BLACK
                draw.rectangle([square_start, tick_bar_start + 4, square_end, tick_bar_start - 4 + tick_bar_height], fill=YELLOW, outline=YELLOW, width=1)
                for i in sorted(favorites, key=str.casefold):
                    draw.rectangle([tick_start, tick_start_y - 2, tick_start + tick_width, tick_start_y + tick_height+2], fill=tick_color)
                    tick_locations[i] = tick_start
                    tick_start += mark_width
                    square_end += mark_width
                tick_start += 5

            tick_color = WHITE
            for i in [i for i in stream_list if i not in favorites]:
                draw.rectangle([tick_start, tick_start_y - 2, tick_start + tick_width, tick_start_y + tick_height+2], fill=tick_color)
                tick_locations[i] = tick_start
                tick_start += mark_width

            # marker
            first_tick_start = padding
            bar_width = 2
            mark_start = tick_locations[stream]
            #current_fill = BLUE if stream not in favorites else BLUE
            #current_station_highlight = [mark_start, tick_bar_start + 2, mark_start + bar_width, tick_bar_start + 2 + tick_bar_height - 4]
            #draw.rectangle(current_station_highlight, fill=current_fill, outline=BLACK, width=1)
            mark_start = tick_locations[name]
            readied_fill = WHITE if name not in favorites else WHITE 
            draw.rectangle([mark_start-1, tick_bar_start + 1, mark_start + bar_width+1, tick_bar_start + 2 + tick_bar_height - 3], fill=readied_fill, outline=BLACK, width=1)

        if not silent:  
            disp.ShowImage(image)
        return image
        #safe_display(image)
    else:
        display_one(name)

one_cache = {}
def display_one(name):
    global has_displayed_once, currently_displaying, current_image
    
    if name in one_cache.keys():
        disp.ShowImage(one_cache[name])
        current_image = one_cache[name]
    else:
        # logo
        logo = streams[name]['logo_60']
        first_pixel_color = logo.getpixel((2,2))
        pixel_array = np.asarray(first_pixel_color)
        white_array = np.asarray([255, 255, 255, 255])
        black_array = np.asarray([0, 0, 0, 255])

        image = Image.new('RGBA',(320, 240), color=BLACK)
        draw = ImageDraw.Draw(image)  

        draw.rectangle([15, 11, 76, 72], outline=WHITE, width=1)
        logo_position = (16, 12)
        image.paste(logo, logo_position)
        if name in favorites:
            image.paste(star_60, logo_position, star_60)
        if streams[name]['status'] == 'Live':
            image.paste(live_60, (16, 12), live_60)

        # name and underline
        name_line = calculate_text(name, font=LARGE_FONT_THIN, max_width=225, lines=1)[0]
        draw.rectangle([92, 20 - 4, 92 + width(name_line, LARGE_FONT_THIN), 20 + height('S', LARGE_FONT_THIN)], fill=BLACK)
        draw.text((90, 13), name_line, font=LARGE_FONT_THIN, fill=WHITE)
        draw.rectangle([92, 47, 92 + width(name_line, LARGE_FONT_THIN), 47], fill=WHITE) # underline
        #draw.rectangle([15, 72 + 12, SCREEN_WIDTH-15, 72 + 12], outline=WHITE, width=1) # divider
        
        # location
        location = streams[name]['location']
        draw.rectangle([92, 52 + 2, 92 + width(location, MEDIUM_FONT), 52 + 3 + height('S', MEDIUM_FONT)], fill=BLUE)# bg
        draw.text((92, 52), calculate_text(location, font=MEDIUM_FONT, max_width=223, lines=1)[0], font=MEDIUM_FONT, fill=BLACK)    

        # now playing
        y_offset = 0
        num_title_lines = 2
        info = streams[name]['oneLiner'].replace('&amp;','&').split(' - ')
        info = [i for i in info if i in list(set(info))]

        if len(info) == 1:
            num_title_lines = 3
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

        line_gap = 3
        section_gap = 6
        anchor = get_anchor(title_lines, info_lines, line_gap, section_gap)
        avg_title_height = sum(height(i, LARGE_FONT) for i in title_lines) / len(title_lines) if title_lines else 0
        avg_info_height = sum(height(i, MEDIUM_FONT) for i in info_lines) / len(info_lines) if info_lines else 0

        for i in title_lines:
            draw.text((14, anchor), i, font=LARGE_FONT, fill=WHITE)
            anchor += avg_title_height + line_gap

        anchor += section_gap

        if info_lines:
            for i in info_lines:
                draw.text((14, anchor), i, font=MEDIUM_FONT, fill=WHITE)
                anchor += avg_info_height + line_gap

        currently_displaying = 'one'
        display_bar(y=218, draw=draw)

        disp.ShowImage(image)
        current_image = image
        has_displayed_once = True
        one_cache[name] = image


def display_bar(y, draw):
    # time
    now = time.time()
    current_time = datetime.fromtimestamp(now, tz=user_tz)
    formatted_date = current_time.strftime("%a %b %d").replace(' 0', '  ').lstrip('0')
    formatted_time = current_time.strftime("%I:%M %p").replace(' 0', '  ').lstrip('0')
    text_color = BLACK

    # bottom bar 218 y for bottom
    if y!=4:
        draw.rectangle([0, y, 320, y+24], fill=YELLOW)
        draw.rectangle([0, y, 320, y], fill=BLACK)
        center_of_section = round((240 + 218) / 2)

    if y==4:
        line_y = y + height("S", MEDIUM_FONT) + 10
        draw.rectangle([0, line_y, 320, line_y], fill=YELLOW)
        draw.rectangle([0, line_y-24, 320, line_y], fill=YELLOW)
        center_of_section = round((0 + line_y+4) / 2)

    draw.text((13,y+2), formatted_date, font=MEDIUM_FONT, fill=text_color)
    draw.text((SCREEN_WIDTH - width(formatted_time, MEDIUM_FONT) - 13, y+2), formatted_time, font=MEDIUM_FONT, fill=text_color)

    #radius = 4
    #draw.ellipse((144-radius, center_of_section-radius, 144+radius, center_of_section+radius), fill=BLACK if currently_displaying=='everything' else None, outline=BLACK, width=1)
    #draw.ellipse((157-radius, center_of_section-radius, 157+radius, center_of_section+radius), fill=BLACK if currently_displaying=='one' else None, outline=BLACK, width=1)
    #draw.ellipse((170-radius, center_of_section-radius, 170+radius, center_of_section+radius), fill=BLACK if currently_displaying=='ambient' else None, outline=BLACK, width=1)


def display_ambient(name, clicked=False):
    global screen_dim, currently_displaying

    # logo
    logo = streams[name]['logo_176']
    first_pixel = logo.getpixel((5,5))

    image = Image.new('RGB',(SCREEN_WIDTH, SCREEN_HEIGHT), color = first_pixel)
    image.paste(logo, (72, 32))
    draw = ImageDraw.Draw(image)

    currently_displaying = 'ambient'
    display_bar(y=218,draw=draw)

    safe_display(image)

    if not clicked:
        screen_dim = True


def display_current():
    print('displaying current')
    print(currently_displaying)
    if currently_displaying == 'everything':
        #display_readied_cached(stream)
        display_one(stream)

    elif currently_displaying == 'one':
        display_one(stream)

    elif currently_displaying == 'ambient':
        display_ambient(stream, clicked=True)


def get_anchor(title, info, line_gap, section_gap):
    size = 0
    for line in title:
        size += height(line, LARGE_FONT) + line_gap
    if info:
        size += section_gap
        for line in info:
            size += height(line, MEDIUM_FONT) + line_gap

    section_height = 215 - (72 + 12 + 6)
    return 65 + 12 + 6 + round((section_height - size) // 2)


def display_battery(draw, image):
    if not battery:
        get_battery()
    if battery:
        outer_sq = draw.rectangle([280, 227, 300, 237], fill=BLACK)
        nipple = draw.rectangle([300, 229, 301, 235], fill=BLACK)
        inner_white = draw.rectangle([281, 228, 299, 236], fill=WHITE) 

        fill = BLACK if not charging else GREEN
        inner_sq = draw.rectangle([282, 229, 282 + round(15*battery/100), 235], fill=fill) 

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
        idx = stream_list.index(readied_stream if readied_stream else stream)
        if (direction == 1) and (idx==len(stream_list)-1):
            readied_stream = stream_list[0]
        elif (direction == -1) and (idx==0):
            readied_stream = stream_list[-1]
        else:
            readied_stream = stream_list[idx + direction]

    display_readied_cached(readied_stream)
    #display_everything(direction, readied_stream, readied=True)

def confirm_seek():
    global readied_stream, stream
    if readied_stream:
        if stream != readied_stream:
            #pause()
            stream = readied_stream
            play(stream)
        #display_everything(0, stream)
        readied_stream = None

def show_volume_overlay(volume):
    global current_image, volume_overlay_showing
    if current_image:
        img = current_image.copy()

        trim_color = RED

        draw = ImageDraw.Draw(img)
        total_bar_height = SCREEN_HEIGHT
        last_volume_bar_end = max(0, total_bar_height * ((150-current_volume)/150)) 
        volume_bar_end = total_bar_height * ((150-volume)/150)
        overlay_width = 12
        #draw.rectangle([SCREEN_WIDTH-12, 222, SCREEN_WIDTH, SCREEN_WIDTH-12 + 1], fill=BLACK) # make small divider on bottom bar
        # ticks
        tick_gap = round(SCREEN_HEIGHT / (150/ volume_step))
        tick_start = 0
        tick_height = 1
        while tick_start < SCREEN_HEIGHT:
            #draw.rectangle([SCREEN_WIDTH-6, tick_start, SCREEN_WIDTH-4, tick_start + tick_height], fill=BLACK)
            tick_start += tick_gap

        # volume fill
        #img_background = img.getpixel((SCREEN_WIDTH-5,last_volume_bar_end))
        #draw.rectangle([SCREEN_WIDTH-10, last_volume_bar_end, SCREEN_WIDTH, SCREEN_HEIGHT], fill=img_background)
        draw.rectangle([SCREEN_WIDTH-10, volume_bar_end, SCREEN_WIDTH, SCREEN_HEIGHT], fill=trim_color)
        draw.rectangle([SCREEN_WIDTH-10, volume_bar_end, SCREEN_WIDTH, SCREEN_HEIGHT], width=1, outline=BLACK)

        disp.ShowImage(img)
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
    run(['sudo','systemctl', 'restart','radio'])

button_released_time = time.time()
currently_displaying = 'everything'
def on_button_pressed():
    global button_press_time, rotated, button_press_times, held, button_released_time, last_input_time, currently_displaying
    last_input_time = time.time()
    button_press_time = time.time()
    button_released_time = None

    #logging.info('PRESSED AND CURRENTLY DISPLAYING', currently_displaying)

    if readied_stream:
        display_readied_cached(readied_stream, pushed=True)

    else:
        if currently_displaying=='everything':
            display_one(stream)

        elif currently_displaying == 'one':
            display_ambient(stream, clicked=True)

        elif currently_displaying == 'ambient':
            display_readied_cached(stream)

    held = True
    rotated = False

button_press_times = []
def on_button_released():
    global button_press_times, rotated, held, button_released_time, last_input_time, currently_displaying

    held = False
    current_time = time.time()
    last_input_time = time.time()
    button_released_time = current_time

    if readied_stream and (button_released_time - button_press_time < 2):
        display_one(readied_stream)
        confirm_seek()
    
    else:
        set_last_volume(str(current_volume))

        button_press_times.append(current_time)
        button_press_times = [t for t in button_press_times if current_time - t <= 3.0]
        
        if len(button_press_times) >= 5:
            button_press_times = [] 
            safe_restart()
            return    
        
def on_volume_button_pressed():
    global button_press_times, rotated, held, button_released_time, last_input_time, current_volume, screen_on
    held = False
    current_time = time.time()
    last_input_time = time.time()
    button_released_time = current_time
    if screen_on:
        send_mpv_command({"command": ["set_property", "volume", 0]})
        set_last_volume(str(current_volume))
        backlight_off()
    else: 
        screen_on = True
        backlight_on()
        current_volume = get_last_volume()
        logging.info('current vol', current_volume)
        if current_volume:
            send_mpv_command({"command": ["set_property", "volume", current_volume]})
        else:
            send_mpv_command({"command": ["set_property", "volume", 50]})

def toggle_favorite():
    global favorites, stream_list, cached_everything_dict
    now = time.time()

    chosen_stream = stream if not readied_stream else readied_stream
    img = current_image.copy().convert('RGBA')
    
    if chosen_stream in favorites:
        favorites = [i for i in favorites if i != chosen_stream]
        for i in list(reversed(favorite_images)):
            img.paste(i, (0, 0), i)
            disp.ShowImage(img)  
            img = current_image.convert('RGBA')
        img.paste(unfavorite, (0, 0), unfavorite)
        disp.ShowImage(img)
        set_favorites(favorites)
    else:
        favorites.append(chosen_stream)
        favorites = list(set(favorites))
        set_favorites(favorites)
        img.paste(unfavorite, (0, 0), unfavorite)
        disp.ShowImage(img)
        for i in favorite_images:
            img.paste(i, (0, 0), i)
            disp.ShowImage(img)           

    stream_list = get_stream_list(streams)
    time.sleep(0.3)
    show_readied = False if not readied_stream else True
    cached_everything_dict[chosen_stream] = display_everything(0, name=chosen_stream, readied=show_readied)
    refresh_everything_cache()

def refresh_everything_cache(streams=stream_list):
    global cached_everything_dict
    for name in streams:
        if name in one_cache.keys():
            del one_cache[name]
        logging.info(f'Refreshing image for {name}')
        cached_everything_dict[name] = display_everything(0, name=name, readied=True, silent=True)

def handle_rotation(direction):
    global rotated, current_volume, button_press_time, last_rotation, screen_on, screen_dim, last_input_time
    rotated = True
    last_rotation = time.time()
    last_input_time = time.time()

    if held:
        volume_handle_rotation(direction)
    else:
        if button_released_time and (time.time() - button_released_time > 0.3):
            last_rotation = time.time()
            seek_stream(direction)

def volume_handle_rotation(direction):
    global rotated, current_volume, button_press_time, last_rotation, screen_on, screen_dim, last_input_time
    rotated = True
    last_input_time = time.time()
    last_rotation = time.time()

    if direction == 1: 
        new_volume = min(150, current_volume + volume_step)
    else: 
        new_volume = max(0, current_volume - volume_step)
    
    show_volume_overlay(new_volume)
    current_volume = new_volume

    send_mpv_command({"command": ["set_property", "volume", current_volume]})

failed_fetches = 0
time_since_last_update = 0
last_successful_fetch = time.time()

cached_everything_dict = {}
def display_readied_cached(name, pushed=False):
    ''' First looks for cached version and if not, rebuilds '''
    global cached_everything_dict, currently_displaying
    currently_displaying = 'everything'
    if name in list(cached_everything_dict.keys()):
        image = cached_everything_dict[name]

        if pushed:
            image = image.copy()
            draw = ImageDraw.Draw(image)
            logo_position = (129, logo_chunk_start)
            bg_position = og_logo_position
            logo = streams[name]['logo_60']    
            first_pixel_color = logo.getpixel((2,2))
            draw.rectangle([bg_position[0], bg_position[1], bg_position[0] + 96, bg_position[1] + 96], fill=first_pixel_color, outline=WHITE, width=1)
            image.paste(logo, logo_position)

        disp.ShowImage(image)
    else:
        cached_everything_dict[name] = display_everything(0, name, readied=True)

def periodic_update():
    global screen_on, failed_fetches, time_since_last_update, last_successful_fetch, streams, stream_list, cached_everything_dict
    while True:
        logging.info('PERIODIC UPDATE OCCURRING')

        if not charging and screen_on == False and current_volume == 0 and (time.time() - last_input_time > 300):
            pass
            #subprocess.run(['sudo','systemctl', 'start', 'shutdown'])

        if (time.time() - last_input_time > 20):
            display_ambient(stream)

        if screen_on and (time.time() - last_input_time > 600):
            screen_on = False
            backlight_off()
        else:
            time_since_last_success = time.time() - last_successful_fetch
            should_fetch = (time_since_last_update >= 15) or (time_since_last_success > 30) or len(cached_everything_dict)==0
            if should_fetch:
                try:
                    logging.info(f"Fetching stream updates... (last successful: {time_since_last_success:.0f}s ago)")
                    fetched_streams = get_streams()

                    updated_count = 0
                    updated_streams = []
                    for name, v in fetched_streams.items():
                        if (name in streams.keys()):
                            if (v['oneLiner'] != streams[name]['oneLiner']) or (len(cached_everything_dict)==0):
                                updated_streams.append(name)
                                streams[name].update(v)
                                updated_count += 1                              
                    
                    refresh_everything_cache(updated_streams)
                    logging.info(f"Successfully updated {updated_count} streams")
                    streams = fetched_streams
                    stream_list = get_stream_list(streams)
                    failed_fetches = 0
                    last_successful_fetch = time.time()
                        
                except requests.Timeout:
                    failed_fetches += 1
                    logging.error(f"Stream fetch timeout (attempt {failed_fetches}/3)")
                except requests.RequestException as e:
                    failed_fetches += 1
                    logging.error(f"Stream fetch network error: {e} (attempt {failed_fetches}/3)")
                except ValueError as e:
                    failed_fetches += 1
                    logging.error(f"Stream fetch invalid response: {e} (attempt {failed_fetches}/3)")
                except Exception as e:
                    failed_fetches += 1
                    logging.error(f"Stream fetch unexpected error: {type(e).__name__}: {e} (attempt {failed_fetches}/3)")
                
                if failed_fetches >= 3:
                    logging.error("Stream fetch failed 3 times. Restarting radio hardware.")
                    try:
                        disp.clear()
                        disp.reset()
                        disp.close()
                    except:
                        pass
                    if screen_on:
                        print('failed :(')
                        #subprocess.run(['sudo','systemctl','restart','radio'])
                    sys.exit(0)
                
                time_since_last_update = 0

            #if not held and not readied_stream and not screen_dim and screen_on:
            #    display_current()

            time_since_last_update += 5
        
        time.sleep(5)

def wake_screen():
    global screen_on, screen_dim, last_input_time, current_image
    last_input_time = time.time()
    if (not screen_on) or (screen_dim):
        screen_on = True
        screen_dim = False
        
        display_one(stream)
        time.sleep(0.05)
        display_one(stream)
        time.sleep(0.05)
        backlight_on()
        return True
    return False

def wrapped_action(func, direction=0, volume=False):
    def inner():
        if click_button.is_pressed and current_volume == 0 and direction == -1:
            func()
        else:
            if not volume:
                if not wake_screen():
                    func()
            else:
                func()
    return inner


## remote controls

CONTROL_SOCKET = "/tmp/radio_control"

def handle_remote_command(command_data):
    global current_volume, stream, readied_stream, screen_on, rotated, play_status
    
    try:
        cmd = command_data.get('command')
        
        if cmd == 'volume_up':
            volume_handle_rotation(1)
            set_last_volume(current_volume)
            return {'status': 'ok', 'volume': current_volume}
        
        elif cmd == 'volume_down':
            volume_handle_rotation(-1)
            set_last_volume(current_volume)
            return {'status': 'ok', 'volume': current_volume}
        
        elif cmd == 'volume':
            vol = int(command_data.get('value', 60))
            vol = max(0, min(150, vol))
            current_volume = vol
            send_mpv_command({"command": ["set_property", "volume", current_volume]})
            show_volume_overlay(current_volume)
            set_last_volume(str(current_volume))
            return {'status': 'ok', 'volume': current_volume}
        
        elif cmd == 'play':
            station_name = command_data.get('value')
            if station_name in stream_list:
                play(station_name)
                display_everything(0,station_name)
            return {
                'status': 'ok',
                'station': station_name,
                'now_playing': streams[station_name]['oneLiner'],
            }
        
        elif cmd == 'next':
            readied_stream = stream
            seek_stream(1)
            confirm_seek()
            return {
                'status': 'ok',
                'station': stream,
                'now_playing': streams[stream]['oneLiner'],
            }
        
        elif cmd == 'prev':
            readied_stream = stream
            seek_stream(-1)
            confirm_seek()
            return {
                'status': 'ok',
                'station': stream,
                'now_playing': streams[stream]['oneLiner'],
            }
        
        elif cmd == 'play_random':
            play_random()
            return {
                'status': 'ok',
                'station': stream,
                'now_playing': streams[stream]['oneLiner'],
                'volume': round(current_volume*100/150),
                'battery': battery,
                'charging': charging
            }
        
        elif cmd == 'status':
            return {
                'status': 'ok',
                'station': stream,
                'now_playing': streams[stream]['oneLiner'],
                'volume': round(current_volume*100/150),
                'battery': battery,
                'charging': charging
            }
        
        elif cmd == 'list':
            return {
                'status': 'ok',
                'stations': stream_list,
                'favorites': favorites
            }
        
        elif cmd == 'favorite':
            rotated = False
            toggle_favorite()
            return {'status': 'ok', 'favorites': favorites}
        
        elif cmd == 'off':
            screen_on = False
            send_mpv_command({"command": ["set_property", "volume", 0]})
            backlight_off()

        elif cmd == 'on':
            send_mpv_command({"command": ["set_property", "volume", current_volume]})
            set_last_volume(str(current_volume))
            wake_screen()

        elif cmd == 'pause':
            send_mpv_command({"command": ["set_property", "volume", 0]})

        elif cmd == 'resume':
            send_mpv_command({"command": ["set_property", "volume", current_volume]})

        elif cmd == 'restart':
            safe_restart()

        elif cmd == 'power':
            if screen_on:
                screen_on = False
                send_mpv_command({"command": ["set_property", "volume", 0]})
                backlight_off()
            else:
                send_mpv_command({"command": ["set_property", "volume", current_volume]})
                set_last_volume(str(current_volume))
                wake_screen()

        elif cmd == 'toggle':
            if play_status == 'play':
                send_mpv_command({"command": ["set_property", "volume", 0]})
                play_status = 'pause'
            else:
                play_status = 'play'
                send_mpv_command({"command": ["set_property", "volume", current_volume]})

        else:
            return {'status': 'error', 'message': 'Unknown command'}
            
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def control_socket_listener():
    global last_input_time
    
    if os.path.exists(CONTROL_SOCKET):
        os.remove(CONTROL_SOCKET)
    
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(CONTROL_SOCKET)
    os.chmod(CONTROL_SOCKET, 0o666) 
    sock.listen(1)
    logging.info(f"Listening on {CONTROL_SOCKET}")
    
    while True:
        try:
            conn, _ = sock.accept()
            data = conn.recv(1024).decode('utf-8').strip()
            
            if data:
                command = json.loads(data)
                response = handle_remote_command(command)
                conn.sendall((json.dumps(response) + '\n').encode('utf-8'))
                last_input_time = time.time()
            conn.close()
            
        except socket.timeout:
            # Timeout is normal, just continue
            continue
        except Exception as e:
            # Only log actual errors
            logging.error(f"Control socket error: {e}")

threading.Thread(target=control_socket_listener, daemon=True).start()


## physical controls

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

CLK_PIN = 16
DT_PIN = 12  
volume_rotor = RotaryEncoder(CLK_PIN, DT_PIN)
volume_rotor.when_rotated_counter_clockwise = wrapped_action(lambda: volume_handle_rotation(-1), -1, True)
volume_rotor.when_rotated_clockwise = wrapped_action(lambda: volume_handle_rotation(1), 1, True)

volume_click_button = Button(17, bounce_time=0.05)
volume_click_button.when_pressed = wrapped_action(lambda: on_volume_button_pressed())

## main loop

last_played = read_last_played()
if last_played in list(streams.keys()):
    play(last_played)
else:
    play_random()

last_input_time = time.time()
update_thread = threading.Thread(target=periodic_update, daemon=True)
update_thread.start()

readied_stream = None
display_everything(0, stream, readied=False)

time_since_battery_check = 0
live_overlay_version = 1
try:
    while True:
        if time_since_battery_check == 15:
            get_battery()
            #if not charging:
                #subprocess.run(['sudo','systemctl', 'start', 'shutdown'])
            time_since_battery_check = 0

        if (readied_stream or volume_overlay_showing) and last_rotation and (time.time() - last_rotation > 5) and restarting == False and held == False:
            readied_stream = None
            volume_overlay_showing = False
            if screen_on and stream and not screen_dim:
                display_current()

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
