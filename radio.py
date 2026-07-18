from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageSequence, ImageOps
from datetime import date, datetime, timezone, timedelta
from subprocess import Popen, run
from pathlib import Path
from io import BytesIO
import spidev as SPI
import numpy as np
import subprocess
import threading
import traceback
import requests
import platform
import logging
import random
import pickle
import signal
import pytz
import time
import json
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

display_lock = threading.Lock()
state_lock = threading.RLock()

battery = None
charging = False
sleeping = False
muted = False
put_to_sleep = False
current_image = None

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

BRIGHTNESS = 1

WHITE = (255,255,255)
DARK_WHITE = (243,243,243)
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
MEDIUM_FONT_BOLD = ImageFont.truetype("assets/Archivo-Bold.ttf", 18)
LARGE_FONT = ImageFont.truetype("assets/Archivo-Light.ttf",42)
LARGE_ISH_FONT = ImageFont.truetype("assets/Archivo-Bold.ttf",28)
LARGE_FONT_THIN = ImageFont.truetype("assets/Archivo-Light.ttf",28) 

def load_font(name, size, weight=400):
    if name == 'Archivo':
        font = ImageFont.truetype('assets/Archivo/Archivo-VariableFont_wdth,wght.ttf', size)
    elif name == 'Noto':
        font = ImageFont.truetype('assets/Noto_Sans/NotoSans-VariableFont_wdth,wght.ttf', size)   
    elif name == 'Favorit':
        font = ImageFont.truetype('assets/Favorit/ABCFavoritMono-Regular.otf', size)   
    
    if name != 'Favorit':
        font.set_variation_by_axes([weight]) 
    return font

SMALL_LIGHT = load_font('Favorit', 17, weight=400)  #load_font('Noto', 17, weight=400)  
MEDIUM_BOLD = load_font('Archivo',28, weight=600)
LARGE_LIGHT = load_font('Archivo',32, weight=400)  
EXTRALARGE_LIGHT = load_font('Favorit', 38, weight=400)#load_font('Archivo',38, weight=400)  

def replace_font(font):
    replacement = 'Noto'
    size = 17
    weight = 400
    if font == SMALL_LIGHT:
        weight = 400
        size = 17
    elif font == MEDIUM_BOLD:
        weight = 600
        size = 28
    elif font == LARGE_LIGHT:
        weight = 400
        size = 32
    elif font == EXTRALARGE_LIGHT:
        weight = 400
        size = 38
    return load_font(replacement, size, weight)

ONE_INFO_FONT = SMALL_LIGHT
EVERYTHING_NAME_FONT = MEDIUM_BOLD
ONE_NAME_FONT = MEDIUM_BOLD
ONE_LARGISH_FONT = LARGE_LIGHT
ONE_LARGE_FONT = EXTRALARGE_LIGHT

LIB_PATH = "/var/lib/scud-radio"

## functions

import driver as LCD_2inch

def get_timezone_from_ip():
    try:
        response = requests.get('http://ip-api.com/json/')
        data = response.json()
        return data['timezone']
    except:
        return 'UTC' 
user_tz = pytz.timezone(get_timezone_from_ip())
    
def get_config():
    Path(LIB_PATH).mkdir(parents=True, exist_ok=True)
    default_config = {
            'confirm_on_rotate': True,
            'volume': 60,
            'last_played': None
    }
    config_file_path = Path(LIB_PATH) / 'config.json'
    if not config_file_path.exists():
        config_file_path.touch() 
        return default_config
    try:
        with open(config_file_path, 'r') as f:
            config = json.load(f)
        return config
    except:
        return default_config
    
def set_config(config):
    Path(LIB_PATH).mkdir(parents=True, exist_ok=True)
    config_file_path = Path(LIB_PATH) / 'config.json'
    if isinstance(config, dict):
        with open(config_file_path, 'w') as f:
            json.dump(config, f)

def get_last_volume():
    config = get_config()
    return config['volume']

def set_last_volume(vol):
    config = get_config()
    try:
        config['volume'] = int(vol)
    except:
        config['volume'] = 60
    set_config(config)

def set_last_played(name):
    config = get_config()
    config['last_played'] = name
    set_config(config)

def get_last_played():
    config = get_config()
    return config['last_played']

def display_scud():
    global currently_displaying, current_image, current_time
    currently_displaying = 'scud'

    image = Image.new('RGBA', (SCREEN_WIDTH, SCREEN_HEIGHT), color=YELLOW)
    bg = Image.open(f'assets/success.png') 
    image.paste(bg, (0, 0))
    enhancer = ImageEnhance.Brightness(image)
    image = enhancer.enhance(BRIGHTNESS)
    disp.ShowImage(image)
    current_image = image.copy()
    now = time.time()
    current_time = datetime.fromtimestamp(now, tz=user_tz)

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

def get_hidden():
    hidden_path = Path(LIB_PATH)
    hidden_path.mkdir(parents=True, exist_ok=True)
    
    hidden_file = hidden_path / 'hidden.txt'
    if not hidden_file.exists():
        hidden_file.touch() 
        return []
    
    with open(hidden_file, 'r') as f:
        hidden = f.readlines()

    return [hid.strip() for hid in hidden]

def set_hidden(hidden):
    hidden_path = Path(LIB_PATH)
    hidden_path.mkdir(parents=True, exist_ok=True)
    
    with open(hidden_path / 'hidden.txt', 'w') as f:
        f.write('\n'.join(hidden))
    
    return hidden

def safe_display(image):
    global current_image
    with display_lock:
        disp.ShowImage(image)
    current_image = image.copy()

def backlight_on():
    global screen_on
    if disp:
        if stream:
            if currently_displaying == 'ambient':
                display_ambient(stream)
            else:
                displa_cached_scroll(stream)
        else:
            display_scud()
        time.sleep(0.1)
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

from gpiozero import Button
import socket

def send_mpv_command(cmd, max_retries=10, retry_delay=1):
    for attempt in range(max_retries):
        try:
            #logging.info(f"Sending MPV command: {cmd}")
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(2)
                s.connect("/tmp/mpvsocket")
                try:
                    s.sendall((json.dumps(cmd) + '\n').encode())
                except BrokenPipeError as e:
                    pass
                return True
        except (ConnectionRefusedError, FileNotFoundError, socket.timeout) as e:
            if attempt < max_retries - 1:
                #logging.warning(f"MPV command failed (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(retry_delay)
            else:
                #logging.error(f"MPV command failed after {max_retries} attempts: {e}")
                return False
    return False

def fetch_logos(name):
    logos = {}
    for i in ['25','60','96','216']:
        resp = requests.get(f'https://internetradioprotocol.org/logos/{name.replace(' ','_')}_{i}.pkl', timeout=5)
        resp.raise_for_status()
        data = pickle.load(BytesIO(resp.content))
        logos[i] = data
    return name, logos

def get_streams():
    global hidden

    info = requests.get(f'https://internetradioprotocol.org/info?cacheBuster={random.randint(0,10000)}', timeout=5).json()
    active = {n: v for n, v in info.items() if v['hidden']!=True}
    #hidden.extend([n for n, v in info.items() if v['hidden']==True])
    #hidden = list(set(hidden))
    #print('HIDDEN ON O-R', [n for n, v in info.items() if v['hidden']==True])
    
    # clean text
    for name, _ in active.items():
        rendered = html.unescape(active[name]['oneLiner']).replace('&amp;', '&').strip()
        active[name]['oneLiner'] = rendered
        if active[name]['status'] == 'Offline':
            active[name]['oneLiner'] = 'Offline'
        active[name]['oneLinerWidth'] = width(active[name]['oneLiner'], SMALL_LIGHT)
        
        if active[name]['status'] == 'Offline':
            active[name]['oneLiner'] = 'Offline'
    
    # see if cached image exists. if so, read into dict. if not, add to queue.
    need_imgs = []
    for name, _ in active.items():
        full_img_path = Path(LIB_PATH) / f'{name.replace(' ','_')}_216.pkl'

        if not full_img_path.exists():
            need_imgs.append(name)
        else:
            file_stat = full_img_path.stat()
            file_age_seconds = time.time() - file_stat.st_mtime
            file_age_days = file_age_seconds / (24 * 3600) 

            if file_age_days > 7:  # refresh if older than 7 days
                need_imgs.append(name)
            else:
                for i in ['25','60','96','216']:
                    with open(Path(LIB_PATH) / f'{name.replace(' ','_')}_{i}.pkl', 'rb') as f:
                        image = pickle.load(f).convert('RGB')
                        active[name][f'logo_{i}'] = image

    with ThreadPoolExecutor(max_workers=8) as exe:
        futures = [
            exe.submit(fetch_logos, name)
            for name, v in active.items() if name in need_imgs
        ]
        for f in as_completed(futures):
            name, logo_dict = f.result()
            
            # save images to lib
            for key, val in logo_dict.items():
                active[name][f'logo_{key}'] = val
                entire_path = Path(LIB_PATH) / f'{name.replace(' ','_')}_{key}.pkl'

                if not entire_path.exists():
                    entire_path.touch() 

                with open(entire_path, 'wb') as f:
                    pickle.dump(val, f)

    return active

reruns = []
def get_stream_list(stream_dict):
    global reruns 
    stream_list = sorted(list(stream_dict.keys()), key=str.casefold)
    reruns = [i for i in stream_list if stream_dict[i]['status'] == 'Re-Run']
    
    if favorites:
        stream_list =  sorted([i for i in favorites if i in stream_list], key=str.casefold) + sorted([i for i in stream_list if i not in favorites], key=str.casefold)
    
    if hidden:
        stream_list = [i for i in stream_list if i not in hidden]

    return stream_list

def width(string, font):
    if not string:
        string = ''
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
    else:
        stream_url = streams[name]['streamLink']
        if first_boot:
            send_mpv_command({"command": ["loadfile", stream_url]})
            first_boot = False
        else:
            send_mpv_command({"command": ["loadfile", stream_url, 'replace']})
    #if not sleeping:
        #send_mpv_command({"command": ["set_property", "volume", current_volume]})

    set_last_played(name)


def play_random():
    global stream, play_status, readied_stream
    with state_lock:
        available = [i for i in stream_list if i != stream and streams[i]['status'] != 'Offline']
    chosen = random.choice(available)
    displa_cached_scroll(chosen)
    play(chosen)
    stream = chosen
    readied_stream = None
    play_status = 'play'

def calculate_text(text, font, max_width, lines):
    text = text.strip()

    all_good = True
    text_idx = -1
    tofu = bytes(font.getmask('\uffff'))
    while all_good and text_idx < min(3,len(text)):
        try:
            if bytes(font.getmask(text[text_idx])) == tofu:
                font = replace_font(font)
                all_good = False
        except IndexError:
            pass
        text_idx += 1

    if width(text, font) <= max_width:
        return [f"{text}"], font
    
    else:
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
                    line_list.append(f"{characters}")
                    return line_list, font
                else:
                    characters += i
                    current_width = width(characters, font)
            else:
                if width(characters + i, font) >= max_width: # if current line exceeds max width and is not last line
                    if i in [')']:
                        characters += i
                    else:
                        current_line += 1
                        line_list.append(f"{characters}")
                        if i not in [' ','-','/',':']:
                            characters = i
                        else:
                            characters = ''
                        current_width = 0
                else:
                    characters += i
                    current_width = width(characters, font)
        if characters:  # if there are remaining characters
            line_list.append(f"{characters}")
        return line_list, font
    

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

start_x = 0
logo_chunk_start = 35
logo_chunk_start_x = 12 + start_x
og_logo_position = (116, logo_chunk_start - 14 - 4)
logo_position = og_logo_position

tick_width = 0
padding = 10
square_start = padding 
total_span = SCREEN_WIDTH - (2 * padding)
tick_start = padding  
tick_bar_height = 25
tick_bar_start = logo_chunk_start + 90
tick_height = 1
tick_start_y = (tick_bar_start + tick_bar_height / 2) 
tick_image = None
tick_locations = {}

def calculate_ticks():
    global tick_locations, tick_image
    image = Image.new('RGBA', (SCREEN_WIDTH, SCREEN_HEIGHT), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    tick_locations = {}

    total_ticks = len(stream_list)
    step = total_span / total_ticks        

    fav_sorted = sorted(favorites, key=str.casefold)
    rest = [i for i in stream_list if i not in favorites]
    ordered = fav_sorted + rest

    line_y = tick_start_y

    # yellow highlight block behind the favorites region
    if fav_sorted:
        fav_start_x = tick_start
        fav_end_x = tick_start + step * len(fav_sorted)
        draw.rectangle([fav_start_x, line_y - 3, fav_end_x, line_y + 3], fill=YELLOW)

    # white baseline for the non-favorite region
    rest_start_x = tick_start + step * len(fav_sorted)
    draw.rectangle([rest_start_x, line_y - 1, SCREEN_WIDTH, line_y + 1], fill=WHITE)

    # assign positions; draw individual ticks only for favorites
    for idx, name in enumerate(ordered):
        x = tick_start + step * idx
        tick_locations[name] = round(x)
    tick_image = image


def draw_tick(draw, name):
    if name not in tick_locations:
        calculate_ticks()

    mark_start = tick_locations[name]
    bar_width = 3
    draw.rectangle(
        [mark_start - 1, tick_bar_start, mark_start + bar_width, tick_bar_start + tick_bar_height],
        fill=WHITE,
        outline=BLACK,
        width=1
    )

FONT_HEIGHTS = {
    'SMALL' : height('Sg',SMALL_FONT),
    'SMALL_LIGHT' : height('Sg',SMALL_LIGHT),
    'EXTRALARGE_LIGHT' : height('Sg',EXTRALARGE_LIGHT),
}

NAME_Y = 240 - 88        
_name_metrics_cache = {}              

def _name_metrics(name):
    if name not in _name_metrics_cache:
        _, f = calculate_text(name, EXTRALARGE_LIGHT, 10**9, 1)
        _name_metrics_cache[name] = (f, width(name, f))
    return _name_metrics_cache[name]

def _draw_marquee_name(draw, name, offset):
    """Paint the scrolled station name onto an existing draw object. No push."""
    font, full_w = _name_metrics(name)
    line_h = FONT_HEIGHTS['EXTRALARGE_LIGHT']
    strip_bottom = NAME_Y + line_h + 9   # stops just above the oneLiner row

    # clear the whole name strip (covers the baked-in truncated name)
    draw.rectangle([0, NAME_Y - 2, SCREEN_WIDTH, strip_bottom], fill=BLACK)

    span = full_w + MARQUEE_GAP
    start = MARQUEE_X - (offset % span)
    draw.text((start - 1, NAME_Y - 1), name, font=font, fill=WHITE)
    draw.text((start - 1 + span, NAME_Y - 1), name, font=font, fill=WHITE)

    # left gutter
    draw.rectangle([0, NAME_Y - 2, MARQUEE_X - 1, strip_bottom], fill=BLACK)

oneliner_mq  = {'offset': 0, 'pause_until': 0, 'needed': False}
name_mq  = {'offset': 0, 'pause_until': 0, 'needed': False}

def _mq_reset(mq, now):
    mq['offset'] = 0
    mq['pause_until'] = now + 3

def _mq_tick(mq, span, now):
    """Advance one marquee controller. Returns current offset."""
    if now >= mq['pause_until']:
        mq['offset'] += 2
        if mq['offset'] >= span:
            mq['offset'] = 0
            mq['pause_until'] = now + 3
    return mq['offset']

marquee_name = None
seek_token = 0
text_on_screen = None

MARQUEE_X = 12 + start_x                      # name_chunk_start_x
MARQUEE_GAP = 30                              # blank gap before the text repeats

def _draw_marquee_oneliner(draw, name, offset):
    global text_on_screen

    """Paint the scrolled oneLiner onto an existing draw object. No push."""
    text = streams[name]['oneLiner'].replace('&amp;', '&').strip()
    full_w = streams[name].get('oneLinerWidth') or width(text, SMALL_LIGHT)

    name_font = EXTRALARGE_LIGHT
    name_chunk_start = 240 - 88
    everything_info_y = name_chunk_start + FONT_HEIGHTS['EXTRALARGE_LIGHT'] + 5
    line_h = FONT_HEIGHTS['SMALL_LIGHT']

    draw.rectangle([MARQUEE_X, everything_info_y + 1,
                    SCREEN_WIDTH, everything_info_y + line_h + 4], fill=BLACK)

    span = full_w + MARQUEE_GAP
    start = MARQUEE_X - (offset % span)
    draw.text((start, everything_info_y), text, font=SMALL_LIGHT, fill=WHITE)
    draw.text((start + span, everything_info_y), text, font=SMALL_LIGHT, fill=WHITE)

    draw.rectangle([0, everything_info_y, MARQUEE_X - 1,
                    everything_info_y + line_h + 4], fill=BLACK)
    
    text_on_screen = streams[name]['oneLiner']


def _draw_volume_bar(draw, volume):
    """Paint the volume bar onto an existing draw object. No push."""
    bar_top = tick_bar_start + 7
    bar_bottom = bar_top + 10
    volume_bar_end = padding + SCREEN_WIDTH * (volume / 150)
    draw.rectangle([padding, bar_top - 10, SCREEN_WIDTH, bar_bottom + 10], fill=BLACK)
    draw.rectangle([padding, bar_top, volume_bar_end, bar_bottom], fill=RED)
    draw.rectangle([padding, bar_top, volume_bar_end, bar_bottom], width=1, outline=BLACK)


def render_frame(name, offset=0, volume=None, draw_oneliner=True, name_offset=None):
    base = scroll_cache_dict.get(name)
    if not base:
        return
    img = base.copy()
    draw = ImageDraw.Draw(img)
    if name_offset is not None:
        _draw_marquee_name(draw, name, name_offset)
    if draw_oneliner:
        _draw_marquee_oneliner(draw, name, offset)
    if volume is not None:
        _draw_volume_bar(draw, volume)
    with display_lock:
        if (readied_stream if readied_stream else stream) != name:
            return
        disp.ShowImage(img)

def display_scroll(name, silent=False):
    global streams, play_status, first_display, selector, start_x, currently_displaying
    
    if not restarting:

        first_display = False

        first_display = False
        len_stream_list = len(stream_list)
        prev_stream = stream_list[(stream_list.index(name) - 1) % len_stream_list]
        double_prev_stream = stream_list[(stream_list.index(prev_stream) - 1) % len_stream_list]
        next_stream = stream_list[(stream_list.index(name) + 1) % len_stream_list]
        double_next_stream = stream_list[(stream_list.index(next_stream) + 1) % len_stream_list]


        image = Image.new('RGBA', (SCREEN_WIDTH, SCREEN_HEIGHT), color=BLACK)
        draw = ImageDraw.Draw(image) 
        
        if not silent:
            currently_displaying = 'everything'

        # draw name and underline
        name_chunk_start = 240 - 88
        name_chunk_start_x = 12 + start_x
        name_font = EXTRALARGE_LIGHT
        name_line = calculate_text(name, name_font, 350, 1)[0]
        draw.rectangle([name_chunk_start_x, name_chunk_start - 1, name_chunk_start_x + width(name_line[0], name_font), name_chunk_start + FONT_HEIGHTS['EXTRALARGE_LIGHT']], fill=BLACK) # bg
        draw.text((name_chunk_start_x - 1, name_chunk_start - 1), name_line[0], font=name_font, fill=WHITE) 
        #draw.rectangle([name_chunk_start_x, name_chunk_start + 30, name_chunk_start_x + width(name_line[0], name_font), name_chunk_start + 30], fill=WHITE) # ul

        # draw info
        info_font = SMALL_LIGHT
        y_offset = 0
        everything_info_y = name_chunk_start + FONT_HEIGHTS['EXTRALARGE_LIGHT'] + 5
        info_line = streams[name]['oneLiner']
        draw.text((name_chunk_start_x, everything_info_y + y_offset), info_line, font=SMALL_LIGHT, fill=WHITE)
        y_offset += 20

        # draw tags
        tags_start_y = round(everything_info_y + FONT_HEIGHTS['SMALL_LIGHT'] + 12)
        tags_start_x = name_chunk_start_x
        location = streams[name]['location']
        live_status = streams[name]['status']
        stream_genres = streams[name]['genres']

        genres = [live_status,location]
        if stream_genres:
            genres.extend(stream_genres)

        genre_x_offset = 0
        if genres:
            genre_widths = [width(g, SMALL_LIGHT) for g in genres]
            box_h = FONT_HEIGHTS['SMALL_LIGHT'] - 4
            for (idx, genre), genre_width in zip(enumerate(genres), genre_widths):
                fill = RED if idx == 0 else BLUE if idx == 1 else YELLOW
                x0 = tags_start_x + genre_x_offset
                draw.rectangle([x0, tags_start_y, x0 + genre_width, tags_start_y + 1 + box_h], fill=fill)
                # anchor text by its own bbox top so per-string metrics don't shift it
                top = info_font.getbbox(genre)[1]
                draw.text((x0, tags_start_y - top + 1), genre, font=info_font, fill=BLACK)
                genre_x_offset += genre_width + 5

        # logos
        logo = streams[name]['logo_96']
        image.paste(logo, logo_position)

        if name in favorites:
            this_star = star_96.copy()
            image.paste(this_star, og_logo_position, this_star)
        #if streams[name]['status'] == 'Live':
            #this_live = live_96.copy()
            #image.paste(this_live, og_logo_position, this_live)
        
        draw.rectangle([og_logo_position[0], og_logo_position[1], og_logo_position[0]+96, og_logo_position[1]+96], outline=BLUE, width=3) # border

        prev_position = (og_logo_position[0] - 70, logo_chunk_start + 22 - 4)
        next_position = (og_logo_position[0] + 106, logo_chunk_start + 22 - 4)
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

        # double prev and next
        double_prev_position = (square_start, logo_chunk_start + 57 - 4)
        double_next_position = (290, logo_chunk_start + 57 - 4)     
        double_prev = streams[double_prev_stream]['logo_25']
        double_next = streams[double_next_stream]['logo_25']
        
        image.paste(double_prev, double_prev_position)
        double_size = 25
        draw.rectangle([double_prev_position[0],double_prev_position[1], double_prev_position[0] + double_size, double_prev_position[1] + double_size], outline=WHITE, width=1)
        if double_prev_stream in favorites:
            double_prev_star = star_25.copy()
            image.paste(double_prev_star, double_prev_position, double_prev_star)

        image.paste(double_next, double_next_position)
        draw.rectangle([double_next_position[0],double_next_position[1], double_next_position[0] + double_size, double_next_position[1] + double_size], outline=WHITE, width=1)
        if double_next_stream in favorites:
            double_next_star = star_25.copy()
            image.paste(double_next_star, double_next_position, double_next_star)

        # draw marks
        image.paste(tick_image, (0,0), mask=tick_image)
        draw_tick(draw, name)
        
        if BRIGHTNESS != 1:
            image = ImageEnhance.Brightness(image).enhance(BRIGHTNESS)

        if not silent: 
            with display_lock:
                    disp.ShowImage(image)   
        return image
        #safe_display(image)

def display_bar(image=current_image, color=WHITE):
    if image:
        draw = ImageDraw.Draw(image)
        now = time.time()
        current_time = datetime.fromtimestamp(now, tz=user_tz)
        formatted_date = current_time.strftime("%a %b %d").replace(' 0', '  ').lstrip('0')
        formatted_time = current_time.strftime("%I:%M %p").replace(' 0', '  ').lstrip('0')

        # pick text color based on how dark the bar color is
        r, g, b = color[:3]
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        text_color = WHITE if luminance < 128 else BLACK

        # bottom bar 218 y for bottom
        y = 218
        draw.rectangle([0, y, 320, y+24], fill=color)
        draw.rectangle([0, y, 320, y], fill=text_color)

        draw.text((13, y+2), formatted_date, font=MEDIUM_FONT, fill=text_color)
        draw.text((SCREEN_WIDTH - width(formatted_time, MEDIUM_FONT) - 13, y+2), formatted_time, font=MEDIUM_FONT, fill=text_color)


def display_ambient(name, clicked=False):
    global currently_displaying, last_ambient_display

    logo = streams[name]['logo_216']
    logo_w, logo_h = logo.size
    first_pixel = logo.getpixel((4, 0))

    image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT), color=first_pixel)

    first_col_strip = logo.crop((4, 0, 5, logo_h))
    last_col_strip = logo.crop((logo_w - 4, 0, logo_w - 3, logo_h))

    # fill left of the logo with its first column
    for col in range(52):
        image.paste(first_col_strip, (col, 2))

    image.paste(logo, (52, 2))

    # fill right of the logo with its last column
    logo_right = 52 + logo_w
    for col in range(logo_right, SCREEN_WIDTH):
        image.paste(last_col_strip, (col, 2))

    image.paste(logo, (52, 2))
    draw = ImageDraw.Draw(image)

    currently_displaying = 'ambient'
    logging.info(f'DISPLAY AMBIENT BEING CALLED')
    display_bar(image, color = first_pixel)

    enhancer = ImageEnhance.Brightness(image)
    image = enhancer.enhance(BRIGHTNESS)

    safe_display(image)

    last_ambient_display = time.time()


def display_current():

    if currently_displaying == 'everything':
        displa_cached_scroll(stream)

    elif currently_displaying == 'one':
        displa_cached_scroll(stream)

    elif currently_displaying == 'ambient':
        display_ambient(stream, clicked=True)


def get_anchor(title, info, line_gap, section_gap, title_font, info_font):
    size = 0
    for _ in title:
        size += height('Sg', title_font) + line_gap
    if info:
        size += section_gap
        for _ in info:
            size += height('Sg', info_font) + line_gap

    section_height = 215 - (72 + 12 + 6)
    return 65 + 12 + 6 + round((section_height - size) // 2) - 6
    

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

freeze_for_task = False
def seek_stream(direction):
    global readied_stream
    if freeze_for_task:
        return
    with state_lock:
        sl = stream_list
        cur = readied_stream if readied_stream else stream
        idx = sl.index(cur)
        readied_stream = sl[(idx + direction) % len(sl)]
    displa_cached_scroll(readied_stream)
    confirm_seek()

def confirm_seek():
    global readied_stream, stream

    if readied_stream:
        if stream != readied_stream:
            stream = readied_stream
            play(stream)
            readied_stream = None

def toggle_confirm_on_rotate():
    global confirm_on_rotate, current_image, confirm_overlay_showing, last_input_time
    last_input_time = time.time()

    if confirm_on_rotate:
        confirm_on_rotate = False
        icon = press_icon
    else: 
        confirm_on_rotate = True
        icon = turn_icon
        
    config = get_config()
    config['confirm_on_rotate'] = confirm_on_rotate
    set_config(config)

    if current_image:
        img = current_image.copy()
        img.paste(icon, (155,222), icon)
        disp.ShowImage(img)
        confirm_overlay_showing = True

def show_volume_overlay(volume):
    global volume_overlay_showing, volume_overlay_value, last_volume_change
    volume_overlay_value = volume
    volume_overlay_showing = True
    last_volume_change = time.time()

def safe_restart():
    global restarting
    if put_to_sleep:
        restarting = True
        image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))
        bg = Image.open(f'assets/updating.png') 
        image.paste(bg, (0, 0))
        safe_display(image)
        backlight_on()
        run(['sudo', '-u','scud','git', 'pull'], cwd='/home/scud/scud-radio')
        time.sleep(4)  
        backlight_off()
        run(['sudo','systemctl', 'restart','api'])
        run(['sudo','systemctl', 'restart','radio'])


def on_button_pressed():
    global button_press_time, rotated, button_press_times, held, button_released_time, last_input_time, currently_displaying, readied_stream
    last_input_time = time.time()
    button_press_time = time.time()
    button_released_time = None

    play_random()

    rotated = False


def on_volume_button_pressed():
    global button_press_times, rotated, held, button_released_time, last_input_time, current_volume, screen_on, sleeping, put_to_sleep, muted, volume_held
    held = False
    current_time = time.time()
    last_input_time = time.time()
    button_released_time = current_time
    

def on_volume_button_released():
    global button_press_times, rotated, held, button_released_time, last_input_time, current_volume, screen_on, sleeping, put_to_sleep, muted, volume_held
    held = False
    current_time = time.time()
    last_input_time = time.time()
    button_released_time = current_time
    volume_held = False

    toggle_favorite()

def switch_off():
    global button_press_times, rotated, held, button_released_time, last_input_time, current_volume, screen_on, sleeping, put_to_sleep, switch_off_time
    held = False
    current_time = time.time()
    last_input_time = current_time
    button_released_time = current_time
    switch_off_time = current_time
    send_mpv_command({"command": ["set_property", "volume", 0]})
    set_last_volume(str(current_volume))
    backlight_off()
    sleeping = True
    put_to_sleep = True

def switch_on():
    global button_press_times, rotated, held, button_released_time, last_input_time, current_volume, screen_on, sleeping, put_to_sleep
    held = False
    current_time = time.time()
    last_input_time = time.time()
    button_released_time = current_time
    backlight_on()
    sleeping = False
    put_to_sleep = False
    if switch_off_time:
        if current_time - switch_off_time >= 3600:
            with state_lock:
                target = stream if stream in stream_list else (stream_list[0] if stream_list else None)
            if target:
                play(target)
    if not muted:
        send_mpv_command({"command": ["set_property", "volume", current_volume]})

def proximity_order(sl, center):
    """[center, center-1, center+1, center-2, center+2, ...] wrapping around."""
    n = len(sl)
    idx = sl.index(center)
    order = [sl[idx]]
    for d in range(1, n // 2 + 1):
        order.append(sl[(idx - d) % n])
        if len(order) < n:
            order.append(sl[(idx + d) % n])
    return order

refresh_generation = 0

def start_priority_refresh(center):
    global refresh_generation
    with state_lock:
        refresh_generation += 1
        gen = refresh_generation
        sl = list(stream_list)
    if center not in sl:
        center = sl[0]
    ordered = proximity_order(sl, center)
    threading.Thread(target=_refresh_worker, args=(ordered, gen), daemon=True).start()

def _refresh_worker(ordered, gen):
    global refreshing_everything_now
    refreshing_everything_now = True
    try:
        for name in ordered:
            if gen != refresh_generation:      # superseded by a newer pass
                return
            one_cache.pop(name, None)
            img = display_scroll(name, silent=True)
            if gen != refresh_generation:      # check again before writing
                return
            if img:
                scroll_cache_dict[name] = img
            time.sleep(0.05)
    finally:
        if gen == refresh_generation:
            refreshing_everything_now = False

def toggle_favorite():
    global favorites, stream_list, scroll_cache_dict, last_input_time, freeze_for_task
    freeze_for_task = True
    try:
        chosen_stream = readied_stream if readied_stream else stream
        with state_lock:
            if chosen_stream not in stream_list:
                return
            if chosen_stream in favorites:
                action = 'unfavorite'
                favorites = [i for i in favorites if i != chosen_stream]
            else:
                action = 'favorite'
                favorites = list(set(favorites + [chosen_stream]))
            set_favorites(favorites)
            stream_list = get_stream_list(streams)

        img = scroll_cache_dict[chosen_stream].copy()

        if action == 'unfavorite':
            no_star_img = img.copy()
            for i in list(reversed(favorite_images)):
                img.paste(i, (0, 0), i)
                with display_lock:
                    disp.ShowImage(img)  
                img = no_star_img.convert('RGBA')

            img.paste(unfavorite, (0, 0), unfavorite)
            with display_lock:
                    disp.ShowImage(img)  
            time.sleep(0.1)
        else:
            img.paste(favorite_images[0], (0, 0), favorite_images[0])
            with display_lock:
                    disp.ShowImage(img)  
            for i in favorite_images:
                img.paste(i, (0, 0), i)
                with display_lock:
                    disp.ShowImage(img)     
            time.sleep(0.1)
            with display_lock:
                    disp.ShowImage(img)      

        calculate_ticks()
        scroll_cache_dict.clear()         
        displa_cached_scroll(chosen_stream)  
        start_priority_refresh(chosen_stream)   
        last_input_time = time.time()
    finally:
        freeze_for_task = False

ready_to_display = False
refreshing_everything_now = False

def refresh_scroll_cache(refresh_stream_list):
    global scroll_cache_dict, refreshing_everything_now, ready_to_display

    refreshing_everything_now = True
    origin_stream = readied_stream if readied_stream else stream
    if origin_stream:
        ordered_refresh_list = []
        sl = stream_list
        if origin_stream not in sl:
            refreshing_everything_now = False
            return
        stream_idx = sl.index(origin_stream)
        forwards = sl[stream_idx:] + sl[:stream_idx]
        backwards = list(reversed(forwards))

        curr_idx = 0
        while len(ordered_refresh_list) < len(refresh_stream_list):
            if forwards[curr_idx % len(forwards)] in refresh_stream_list:
                ordered_refresh_list.append(forwards[curr_idx % len(forwards)])
            if backwards[curr_idx % len(backwards)] in refresh_stream_list:
                ordered_refresh_list.append(backwards[curr_idx  % len(backwards)])
            curr_idx += 1
            
        #print('ORDERED', ordered_refresh_list)
    
    def refresh_stream(name):
        if name in one_cache.keys():
            del one_cache[name]
        if name in streams.keys():
            #logging.info(f'Refreshing image for {name}')
            result = display_scroll(name=name, silent=True)
        else:
            result = None
        return name, result 
    
    if len(ordered_refresh_list) > 0:
        calculate_ticks()
        for name in ordered_refresh_list:
            name, result = refresh_stream(name)
            scroll_cache_dict[name] = result
            time.sleep(0.05)

    refreshing_everything_now = False


def handle_rotation(direction):
    global rotated, current_volume, button_press_time, last_rotation, screen_on, last_input_time, last_seek_rotation, volume_overlay_showing, marquee_name, marquee_offset, seeking
    seeking = True
    now = time.time()
    last_input_time = now
    rotated = True
    last_rotation = now
    last_seek_rotation = now
    volume_overlay_showing = False
    marquee_name = None
    marquee_offset = 0
    seek_stream(direction)


def volume_handle_rotation(direction):
    global rotated, current_volume, button_press_time, last_rotation, screen_on, last_input_time
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


def displa_cached_scroll(name, pushed=False):
    ''' First looks for cached version and if not, rebuilds '''
    global scroll_cache_dict, currently_displaying, text_on_screen
    currently_displaying = 'everything'
    if name in list(scroll_cache_dict.keys()):
        image = scroll_cache_dict[name]
        if image:
            if pushed:
                image = image.copy()
                draw = ImageDraw.Draw(image)
                bg_position = og_logo_position
                draw.rectangle([bg_position[0], bg_position[1], bg_position[0] + 96, bg_position[1] + 96], outline=BLUE, width=3)

            with display_lock:
                disp.ShowImage(image)
        else:
            scroll_cache_dict[name] = display_scroll(name)
    else:
        scroll_cache_dict[name] = display_scroll(name)

    text_on_screen = streams[name]['oneLiner']
    

def periodic_update():
    global screen_on, failed_fetches, time_since_last_update, last_successful_fetch, streams, stream_list, scroll_cache_dict, sleeping
    while True:

        time_since_last_success = time.time() - last_successful_fetch
        if sleeping:
            should_fetch = not refreshing_everything_now and ((time_since_last_update >= 120) or (time_since_last_success > 120) or len(scroll_cache_dict)==0)
        else:
            should_fetch = not seeking and \
                        not refreshing_everything_now and \
                            ((((oneliner_mq['offset'] == 0) | (name_mq['offset'] == 0)) and (oneliner_mq['needed']==True and name_mq['needed']==True)) or (((oneliner_mq['offset'] == 0) and (name_mq['offset'] == 0))) or (((oneliner_mq['needed'] == False) and (name_mq['needed'] == False)))) and \
                        ((time_since_last_update >= 10) or (time_since_last_success > 10) or len(scroll_cache_dict)==0)
        if should_fetch:
            logging.info('PERIODIC UPDATE OCCURRING')
            print('cache size', len(scroll_cache_dict))

            try:
                logging.info(f"Fetching stream updates... (last successful: {time_since_last_success:.0f}s ago)")
                fetched_streams = get_streams()

                updated_count = 0
                updated_streams = []
                for name, v in fetched_streams.items():
                    if (name in streams.keys()):
                        if (v['oneLiner'] != streams[name]['oneLiner']) or (len(scroll_cache_dict)==0):
                            updated_streams.append(name)
                            streams[name].update(v)
                            updated_count += 1                              
                
                print('Updated',updated_streams)
                refresh_scroll_cache(updated_streams)
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
            
            if failed_fetches >= 5:
                logging.error("Stream fetch failed 5 times.")
                #subprocess.run(['sudo','systemctl','start','launcher'])
                #sys.exit(0)
            
            time_since_last_update = 0

        time_since_last_update += 1
        time.sleep(1)

def wake_screen():
    global screen_on, last_input_time, current_image
    last_input_time = time.time()
    if (not screen_on):
        screen_on = True

        display_current()
        time.sleep(0.05)
        display_current
        time.sleep(0.05)
        backlight_on()
        return True
    return False

def wrapped_action(func, direction=0, volume=False):
    def inner():
        if not put_to_sleep:
            if click_button.is_pressed and current_volume == 0 and direction == -1:
                func()
            else:
                if not volume:
                    if not wake_screen():
                        func()
                else:
                    func()
    return inner

## upon startup 

# 2 inch
RST = 27
DC = 25
BL = 23
bus = 0 
device = 0 
current_bl = 100
disp = LCD_2inch.LCD_2inch()
disp.Init()
#disp.clear()
disp.bl_DutyCycle(current_bl)

display_scud()

mpv_process = None
stream = None
readied_stream = None
last_rotation = None
last_seek_rotation = None
screen_on = True
saved_image_while_paused = None
play_status = 'pause'
last_input_time = time.time()
first_display = True
volume_step = 10
button_press_time = 0
rotated = False
restarting = False
held = False
volume_held = False
wifi_strength = None
first_boot = True
selector = 'red'
has_displayed_once = False
volume_overlay_showing = False
volume_overlay_value = 0
last_volume_change = 0
marquee_pause_until = 0
confirm_overlay_showing = False
last_ambient_display = time.time()
switch_off_time = None
confirm_on_rotate = get_config()['confirm_on_rotate']
seeking = False

current_volume = get_last_volume()

mpv_process = Popen([
    "mpv",
    "--audio-buffer=1.0",     
    "--audio-samplerate=48000",
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

unfavorite = Image.open('assets/unfavorited.png').convert('RGBA')
favorite_images = [Image.open('assets/favorited1.png').convert('RGBA'), 
                   Image.open('assets/favorited2.png').convert('RGBA'), 
                   Image.open('assets/favorited3.png').convert('RGBA'), 
                   Image.open('assets/favorited4.png').convert('RGBA'),
                   Image.open('assets/favorited5.png').convert('RGBA')]

hide_img = Image.open('assets/hide_img.png').convert('RGBA')
unhide_img = Image.open('assets/unhide_img.png').convert('RGBA')

star_60 = Image.open('assets/star_60.png').convert('RGBA')
star_96 = Image.open('assets/star_96.png').convert('RGBA')
star_25 = Image.open('assets/star_25.png').convert('RGBA')

live_60 = Image.open('assets/live_60.png').convert('RGBA')
live_96 = Image.open('assets/live_96.png').convert('RGBA')
live_25 = Image.open('assets/live_25.png').convert('RGBA')

press_icon = Image.open('assets/press_icon.png').convert('RGBA')
turn_icon = Image.open('assets/turn_icon.png').convert('RGBA')

# switch
switch = Button(23, pull_up=False, bounce_time=0.05)
switch.when_pressed  = switch_on
switch.when_released = switch_off
if switch.is_pressed: # sync initial state
    switch_on()
else:
    switch_off()

favorites = get_favorites()
hidden = get_hidden()

button_released_time = time.time()
currently_displaying = 'scud'
button_press_times = []

failed_fetches = 0
time_since_last_update = 0

one_cache = {}
scroll_cache_dict = {}

streams = get_streams()
last_successful_fetch = time.time()
stream_list = get_stream_list(streams)
calculate_ticks()

last_played = get_last_played()
if last_played in stream_list:
    play(last_played)
else:
    play_random()

## remote controls

CONTROL_SOCKET = "/tmp/radio_control"

def handle_remote_command(command_data):
    global current_volume, stream, readied_stream, screen_on, rotated, play_status
    
    try:
        cmd = command_data.get('command')
        
        if cmd == 'volume_up':
            volume_handle_rotation(1)
            return {'status': 'ok', 'volume': current_volume}
        
        elif cmd == 'volume_down':
            volume_handle_rotation(-1)
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
                displa_cached_scroll(station_name)
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
                'stations': {
                    'shown': stream_list,
                    'hidden': hidden,
                    'favorites': favorites
                }
        }

        elif cmd == 'hidden':
            return {
                'status': 'ok',
                'stations': hidden,
                'favorites': favorites
        }
        
        elif cmd == 'favorite':
            rotated = False
            toggle_favorite()
            return {'status': 'ok', 'favorites': favorites}
        
        elif cmd == 'hide':
            stations = command_data.get('value')
            if stations == '<None>':
                stations = []
            try:
                new_hidden = set_hidden(stations)
                return {'status': 'ok', 'hidden': new_hidden}        
            except Exception as e:
                return {'status': 'not ok', 'message': e}        

        elif cmd == 'off':
            screen_on = False
            send_mpv_command({"command": ["set_property", "volume", 0]})
            backlight_off()

        elif cmd == 'on':
            send_mpv_command({"command": ["set_property", "volume", current_volume]})
            set_last_volume(str(current_volume))
            wake_screen()

        elif cmd == 'mute':
            send_mpv_command({"command": ["set_property", "volume", 0]})

        elif cmd == 'pause':
            send_mpv_command({"command": ["set_property", "volume", 0]})

        elif cmd == 'resume':
            send_mpv_command({"command": ["set_property", "volume", current_volume]})

        elif cmd == 'power':
            if screen_on == False and put_to_sleep == False:
                backlight_on()
            else:
                backlight_off()

        elif cmd == 'restart':
            safe_restart()

        elif cmd == 'toggle':
            if play_status == 'play':
                send_mpv_command({"command": ["set_property", "volume", 0]})
                play_status = 'pause'
            else:
                play_status = 'play'
                send_mpv_command({"command": ["set_property", "volume", current_volume]})

        else:
            return {'status': 'error', 'message': 'Unknown command'}
            
    except Exception:
        return {'status': 'error', 'message': traceback.format_exc()}


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
click_button.hold_time = 5
click_button.when_pressed = wrapped_action(lambda: toggle_favorite())
#click_button.when_released = wrapped_action(lambda: on_button_released())
rotor.when_held = safe_restart()
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
#volume_click_button.when_pressed =  wrapped_action(lambda: on_volume_button_pressed())
#volume_click_button.when_released =  wrapped_action(lambda: on_volume_button_released())
volume_click_button.when_pressed = wrapped_action(lambda: on_button_pressed())
volume_click_button.hold_time = 5
volume_click_button.when_held = safe_restart()

## main loop
refresh_scroll_cache(stream_list)

last_input_time = time.time()
update_thread = threading.Thread(target=periodic_update, daemon=True)
update_thread.start()

displa_cached_scroll(stream)

try:
    while True:
        now = time.time()

        if now - last_input_time > 10:
            set_last_volume(str(current_volume))

        if (now - last_input_time > 300) & (now - last_ambient_display > 30):
            logging.info('DISPLAYING AMBIENT VIA MAIN LOOP')
            display_ambient(stream)
            last_ambient_display = now

        if screen_on and (now - last_input_time > 600):
            logging.info('TURNING SCREEN OFF VIA MAIN LOOP')
            sleeping = True
            screen_on = False
            backlight_off()
            
        # ---- marquee the oneLiner on the everything screen ----
        # expire the volume overlay after 5s of no volume rotation
        if volume_overlay_showing and (now - last_volume_change) > 3:
            volume_overlay_showing = False
            volume_just_cleared = True
        else:
            volume_just_cleared = False

        # ---- everything screen: marquee + optional volume overlay, one writer ----
        active_name = readied_stream if readied_stream else stream
        seeking = last_seek_rotation and (now - last_seek_rotation < 1)
        vol = volume_overlay_value if volume_overlay_showing else None

        on_everything = (screen_on and not sleeping
                         and not freeze_for_task
                         and not seeking
                         and currently_displaying == 'everything'
                         and active_name and active_name in scroll_cache_dict)

        if on_everything:
            text = streams[active_name]['oneLiner']
            text_w = width(text, SMALL_LIGHT)
            long_oneliner = text_w > (SCREEN_WIDTH - MARQUEE_X)

            _, name_w = _name_metrics(active_name)
            long_name = name_w > (SCREEN_WIDTH - MARQUEE_X)

            needs_scroll = long_oneliner or long_name
            text_span = text_w + MARQUEE_GAP
            name_span = name_w + MARQUEE_GAP

            name_mq['needed'] = long_name
            oneliner_mq['needed'] = long_oneliner

            text_changed = (text_on_screen != text)
            if text_changed:
                print('------TEXT CHANGED------')
                _mq_reset(oneliner_mq, now)
                marquee_name = None
                if not long_oneliner:
                    del scroll_cache_dict[active_name]
                    displa_cached_scroll(active_name)

            if vol is not None:
                if needs_scroll and not seeking:
                    if marquee_name != active_name:
                        marquee_name = active_name
                        _mq_reset(oneliner_mq, now)
                        _mq_reset(name_mq, now)
                    ol_off = _mq_tick(oneliner_mq, text_span, now) if long_oneliner else 0
                    n_off = _mq_tick(name_mq, name_span, now) if long_name else None
                    render_frame(active_name, ol_off, volume=vol,
                                 draw_oneliner=long_oneliner, name_offset=n_off)
                else:
                    render_frame(active_name, 0, volume=vol, draw_oneliner=False)

            elif seeking:
                marquee_name = None

            elif needs_scroll:
                if marquee_name != active_name:
                    marquee_name = active_name
                    _mq_reset(oneliner_mq, now)
                    _mq_reset(name_mq, now)
                ol_off = _mq_tick(oneliner_mq, text_span, now) if long_oneliner else 0
                n_off = _mq_tick(name_mq, name_span, now) if long_name else None
                render_frame(active_name, ol_off,
                             draw_oneliner=long_oneliner, name_offset=n_off)

            elif volume_just_cleared:
                displa_cached_scroll(active_name)
                marquee_name = None

            else:
                marquee_name = None
        else:
            marquee_name = None

        time.sleep(0.01)

except KeyboardInterrupt:
    if mpv_process:
        mpv_process.terminate()

    WIDTH = disp.width
    HEIGHT = disp.height
    img = Image.new("RGB", (320, 240), color="black")
    draw = ImageDraw.Draw(img)
    #disp.display(img)
    disp.ShowImage(img) # for 2 inch
