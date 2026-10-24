## upon startup
import time 
import driver as LCD_2inch
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageSequence, ImageOps

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

def display_scud():
    global currently_displaying, current_image
    currently_displaying = 'scud'

    image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))
    bg = Image.open(f'assets/success.png') 
    image.paste(bg, (0, 0))
    disp.ShowImage(image)
    current_image = image.copy()

# 2 inch
RST = 27
DC = 25
BL = 9
bus = 0 
device = 0 
current_bl = 100
disp = LCD_2inch.LCD_2inch()
disp.Init()
disp.bl_DutyCycle(current_bl)
display_scud()

import pytz
import requests

def get_timezone_from_ip():
    try:
        response = requests.get('http://ip-api.com/json/')
        data = response.json()
        return data['timezone']
    except:
        return 'UTC' 
    
user_tz = pytz.timezone(get_timezone_from_ip())

from concurrent.futures import ThreadPoolExecutor, as_completed
from subprocess import Popen, run
from datetime import datetime
from pathlib import Path
from io import BytesIO
import spidev as SPI
import numpy as np
import subprocess
import threading
import traceback
import platform
import logging
import random
import pickle
import signal
import json
import math
import html
import sys
import re
import base64
import os

from functools import lru_cache
from collections import OrderedDict

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

MAX_VOL = 150

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

# ---- theme: "dark" (default) or "light"; set "theme" in /var/lib/scud-radio/config.json ----
THEMES = {
    'dark':  {'bg': BLACK,      'fg': WHITE, 'muted': (150, 150, 150), 'faint': (90, 90, 90),   'wedge_off': (45, 45, 45)},
    'light': {'bg': DARK_WHITE, 'fg': BLACK, 'muted': (95, 95, 95),    'faint': (175, 175, 175), 'wedge_off': (215, 215, 215)},
}

def _startup_theme():
    try:
        with open('/var/lib/scud-radio/config.json') as f:
            return json.load(f).get('theme', 'dark')
    except Exception:
        return 'dark'

THEME = THEMES.get(_startup_theme(), THEMES['dark'])
BG_COLOR = THEME['bg']
SECONDARY_COLOR = THEME['fg']
MUTED_COLOR = THEME['muted']          # station time
FAINT_COLOR = THEME['faint']          # unlit dial letters
WEDGE_OFF_COLOR = THEME['wedge_off']  # unlit volume cells
STATUS_OFF_COLOR = (120, 120, 120)    # offline dot
LIVE_COLOR = YELLOW                   # live dot / re-run ring

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

print('LOADING SMALL',time.monotonic())
#SMALL_LIGHT = load_font('Noto', 17, weight=400)  
SMALL_LIGHT = load_font('Favorit', 20, weight=400)  

print('LOADING LARGE',time.monotonic())
EXTRALARGE_LIGHT = load_font('Archivo',42, weight=800)  
CLOCK_FONT = load_font('Favorit', 17)

# ---- one-liner font fallback: Favorit first, then Noto Sans (Cyrillic, Greek,
# extended Latin), then a CJK font if one is installed (apt: fonts-noto-cjk) ----
def _load_fallback(path, size, weight=400):
    try:
        f = ImageFont.truetype(path, size)
    except Exception:
        return None
    try:
        axes = f.get_variation_axes()
        f.set_variation_by_axes([weight if a['name'] in (b'Weight', 'Weight') else a['default'] for a in axes])
    except Exception:
        pass                                  # static font, nothing to set
    return f

OL_FONTS = [SMALL_LIGHT]
for _path, _size in [
    ('assets/Noto_Sans/NotoSans-VariableFont_wdth,wght.ttf', 19),
    ('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', 18),
    ('/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc', 18),
    ('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', 18),
]:
    _f = _load_fallback(_path, _size)
    if _f is not None:
        OL_FONTS.append(_f)
OL_BASELINE = SMALL_LIGHT.getmetrics()[0]     # every run shares Favorit's baseline

_tofu_masks = {}
_glyph_cache = {}
def _has_glyph(font, ch):
    key = (id(font), ch)
    hit = _glyph_cache.get(key)
    if hit is None:
        if ch.isspace():
            hit = True
        else:
            tofu = _tofu_masks.get(id(font))
            if tofu is None:
                tofu = _tofu_masks[id(font)] = bytes(font.getmask('\uffff'))
            try:
                hit = bytes(font.getmask(ch)) != tofu
            except Exception:
                hit = False
        _glyph_cache[key] = hit
    return hit

@lru_cache(maxsize=512)
def _runs(text):
    """Split text into (chunk, font) runs, using the first font that has each glyph."""
    runs = []
    for ch in text:
        f = next((f for f in OL_FONTS if _has_glyph(f, ch)), OL_FONTS[0])
        if runs and runs[-1][1] is f:
            runs[-1][0] += ch
        else:
            runs.append([ch, f])
    return tuple((t, f) for t, f in runs)

@lru_cache(maxsize=512)
def text_width(text):
    return round(sum(f.getlength(t) for t, f in _runs(text or '')))

def draw_text_mixed(draw, xy, text, fill):
    """Draw like draw.text(xy, text, font=SMALL_LIGHT) but with per-glyph fallback."""
    x, y = xy
    by = y + OL_BASELINE
    for t, f in _runs(text or ''):
        draw.text((x, by), t, font=f, fill=fill, anchor='ls')
        x += f.getlength(t)
DIAL_FONT = load_font('Favorit', 14)
TIME_FONT = load_font('Archivo', 48, weight=800)   # station local time on the settled screen


def replace_font(font):
    replacement = 'Noto'
    size = 17
    weight = 400
    if font == SMALL_LIGHT:
        weight = 400
        size = 17
    elif font == EXTRALARGE_LIGHT:
        weight = 400
        size = 38
    return load_font(replacement, size, weight)

LIB_PATH = "/var/lib/scud-radio"

## functions

import tempfile

def atomic_write(path, data, mode='w'):
    """Write data to path atomically"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix='.tmp-', suffix=path.name)
    try:
        with os.fdopen(fd, mode) as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())       
        os.replace(tmp, path)           
    except:
        try: os.unlink(tmp)
        except OSError: pass
        raise
    
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
    if isinstance(config, dict):
        atomic_write(Path(LIB_PATH) / 'config.json', json.dumps(config))

def set_favorites(favorites):
    atomic_write(Path(LIB_PATH) / 'favorites.txt', '\n'.join(favorites))

def set_hidden(hidden):
    atomic_write(Path(LIB_PATH) / 'hidden.txt', '\n'.join(hidden))
    return hidden

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

def safe_display(image):
    global current_image
    with display_lock:
        disp.ShowImage(image)
    current_image = image.copy()

def backlight_on():
    global screen_on
    if disp:
        if not restarting:
            if currently_displaying == 'airplay':
                display_airplay()
            elif stream:
                display_cached_scroll(stream)
            else:
                display_scud()
        time.sleep(0.1)
        disp.bl_DutyCycle(100)
        screen_on = True

def backlight_off():
    global screen_on
    if disp:
        disp.bl_DutyCycle(0)
        screen_on = False

def backlight_dim():
    if disp:
        disp.bl_DutyCycle(20)

from gpiozero import Button
import socket

def send_mpv_command(cmd, max_retries=2, retry_delay=0.05):
    for attempt in range(max_retries):
        try:
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
                time.sleep(retry_delay)
            else:
                return False
    return False

def mpv_get(prop, timeout=0.3):
    """Read an mpv property over the IPC socket; None if mpv doesn't answer."""
    try:
        with socket.socket(socket.AF_UNIX) as sk:
            sk.settimeout(timeout)
            sk.connect("/tmp/mpvsocket")
            sk.sendall((json.dumps({"command": ["get_property", prop], "request_id": 7}) + '\n').encode())
            buf, deadline = b'', time.monotonic() + timeout
            while time.monotonic() < deadline:
                chunk = sk.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    try:
                        msg = json.loads(line)
                    except ValueError:
                        continue                      # an event line, not our reply
                    if msg.get('request_id') == 7:
                        return msg.get('data') if msg.get('error') == 'success' else None
    except (OSError, socket.timeout):
        return None
    return None

# "Tuning in..." -- from loadfile until mpv is actually playing audio
TUNING_TIMEOUT = 12                     # seconds before we say the station isn't answering
tuning = {'name': None, 'since': 0.0, 'state': None}     # state: None | 'tuning' | 'failed'

def _start_tuning(name):
    tuning.update(name=name, since=time.monotonic(), state='tuning')

def _update_tuning(now, active_name, can_draw):
    """Called from the main loop a few times a second while a station is tuning."""
    name, state = tuning['name'], tuning['state']
    # playing = mpv has OUR stream loaded and its core isn't idle (core-idle goes
    # False once audio actually flows); the path check ignores the old stream's tail
    url = (streams.get(name) or {}).get('streamLink')
    playing = mpv_get('core-idle') is False and mpv_get('path') == url
    if playing:
        tuning['state'] = None
    elif state == 'tuning' and now - tuning['since'] > TUNING_TIMEOUT:
        tuning['state'] = 'failed'
    changed = tuning['state'] != state
    if can_draw and active_name == name and (changed or tuning['state'] == 'tuning'):
        push_status_strip(name)                        # 'tuning' redraws each tick to pulse the dot

SUMMARY_URL = 'https://one.radio/summary'
LOGO_SIZES = ['25', '60', '96', '216','320']  
 
def _safe(name):
    return name.replace(' ', '_')
 
def _cached_hash(name):
    p = Path(LIB_PATH) / f'{_safe(name)}.hash'
    try:
        return p.read_text().strip()
    except Exception:
        return None
 
def _write_hash(name, h):
    (Path(LIB_PATH) / f'{_safe(name)}.hash').write_text(h)
 
def _load_cached_pngs(name, target):
    """Load all cached PNG sizes for `name` into target dict. Returns True if all present."""
    ok = True
    for i in LOGO_SIZES:
        p = Path(LIB_PATH) / f'{_safe(name)}_{i}.png'
        if p.exists():
            try:
                target[f'logo_{i}'] = Image.open(p).convert('RGB')
            except Exception:
                try: p.unlink()          # delete the corrupt file so it re-downloads
                except OSError: pass
                ok = False
        else:
            ok = False
    return ok
 
def fetch_logos(name, base_url, logo_hash):
    """Download the PNG set for one station, cache to disk, return in-memory images."""
    imgs = {}
    for i in LOGO_SIZES:
        resp = requests.get(f'{base_url}_{i}.png', timeout=5)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert('RGB')
        imgs[f'logo_{i}'] = img
        # cache to disk as PNG
        path = Path(LIB_PATH) / f'{_safe(name)}_{i}.png'
        atomic_write(path, resp.content, mode='wb')
    _write_hash(name, logo_hash)
    return name, imgs
 
def get_streams():
    global hidden
 
    Path(LIB_PATH).mkdir(parents=True, exist_ok=True)
 
    summary = requests.get(
        f'{SUMMARY_URL}?cacheBuster={random.randint(0,10000)}', timeout=5
    ).json()
 
    active = {}
    for st in summary['stations']:
        if st.get('hidden') is True:
            continue
        name = st['name']
        active[name] = dict(st)   
        active[name]['oneLinerWidth'] = text_width(active[name]['oneLiner'].replace('&amp;', '&').strip())
 
    # Decide which stations need a logo download: missing files or changed hash.
    need_imgs = []
    for name, v in active.items():
        server_hash = v.get('logo_hash')
        have_all = _load_cached_pngs(name, active[name])
        if (not have_all) or (server_hash and server_hash != _cached_hash(name)):
            need_imgs.append(name)
 
    # Fetch only the ones that changed, in parallel.
    if need_imgs:
        with ThreadPoolExecutor(max_workers=8) as exe:
            futures = [
                exe.submit(fetch_logos, name,
                           active[name]['logo_png_base'],
                           active[name].get('logo_hash', ''))
                for name in need_imgs
            ]
            for f in as_completed(futures):
                try:
                    name, imgs = f.result()
                    active[name].update(imgs)
                except Exception as e:
                    logging.error(f'logo fetch failed: {e}')
 
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
    play_status = 'pause'


def play(name, toggled=False):
    global play_status, stream, first_boot, currently_displaying
    if not toggled and airplay_drop():
        currently_displaying = 'everything'
    play_status = 'play'
    stream = name

    if toggled:
        safe_display(saved_image_while_paused)
    else:
        stream_url = streams[name]['streamLink']
        _start_tuning(name)
        ensure_show_art(name)              # ready by the time ambient comes up
        if first_boot:
            send_mpv_command({"command": ["loadfile", stream_url]})
            first_boot = False
        else:
            logging.info(f"PLAYING {name}")
            send_mpv_command({"command": ["loadfile", stream_url, 'replace']})

    global pending_last_played
    pending_last_played = name          # written once tuning settles (main loop)


def play_random():
    global stream, play_status, readied_stream
    with state_lock:
        available = [i for i in stream_list if i != stream and streams[i]['status'] != 'Offline']
    chosen = random.choice(available)
    display_cached_scroll(chosen)
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

@lru_cache(maxsize=256)
def _name_line_cached(name):
    line, font = calculate_text(name, EXTRALARGE_LIGHT, 350, 1)
    return line[0], font

start_x = 0
logo_chunk_start = 35
logo_chunk_start_x = 12 + start_x
TILE = 120                                   # station logo tile size
og_logo_position = (100, logo_chunk_start - 14 - 20)
logo_position = og_logo_position
#logo_position = (0, -100)

tick_width = 0
padding = 10
square_start = padding 
total_span = SCREEN_WIDTH - (2 * padding)
tick_start = 0  
tick_bar_height = 25
tick_bar_start = logo_chunk_start + 90 - 15
tick_height = 1
tick_start_y = (tick_bar_start + tick_bar_height / 2) 
tick_image = None
tick_locations = {}

def _star(draw, cx, cy, r, fill):
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    draw.polygon(pts, fill=fill)

def _dial_glyph(name):
    c = name[:1].upper()
    return c if c.isalpha() else '#'

dial_slots = {}                  # glyph -> (x0, x1, centre x)

def calculate_ticks():
    """Alphabet dial: a star for favourites (they sort first), then the first
    letters of the remaining stations in list order. Unlit layer only."""
    global tick_image, dial_slots
    image = Image.new('RGBA', (SCREEN_WIDTH, SCREEN_HEIGHT), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    glyphs = ['★'] if favorites else []
    for s in stream_list:
        if s in favorites:
            continue
        g = _dial_glyph(s)
        if g not in glyphs:
            glyphs.append(g)
    slots = {}
    if glyphs:
        step = (SCREEN_WIDTH - 24) / max(1, len(glyphs) - 1)
        for k, g in enumerate(glyphs):
            cx = 12 + k * step
            if g == '★':
                _star(draw, cx, DIAL_Y + 9, 5, FAINT_COLOR)
                x0, x1 = cx - 5, cx + 5
            else:
                w = width(g, DIAL_FONT)
                x0 = cx - w / 2
                x1 = x0 + w
                draw.text((x0, DIAL_Y), g, font=DIAL_FONT, fill=FAINT_COLOR)
            slots[g] = (x0, x1, cx)
    dial_slots = slots
    tick_image = image


def draw_tick(draw, name, origin_y=0):
    """Light the current station's glyph and underline it."""
    g = '★' if name in favorites else _dial_glyph(name)
    if g not in dial_slots:
        calculate_ticks()
        if g not in dial_slots:
            return
    x0, x1, cx = dial_slots[g]
    y = DIAL_Y - origin_y
    if g == '★':
        _star(draw, cx, y + 9, 5, SECONDARY_COLOR)
    else:
        draw.text((x0, y), g, font=DIAL_FONT, fill=SECONDARY_COLOR)
    draw.rectangle([x0 - 2, y + 19, x1 + 2, y + 21], fill=SECONDARY_COLOR)

FONT_HEIGHTS = {
    'SMALL_LIGHT' : height('Sg',SMALL_LIGHT),
    'EXTRALARGE_LIGHT' : height('Sg',EXTRALARGE_LIGHT),
}

NAME_Y = 240 - 100
 
# Precompute strip geometry once (module level)
NAME_STRIP_TOP    = NAME_Y - 2
NAME_STRIP_BOTTOM = NAME_Y + FONT_HEIGHTS['EXTRALARGE_LIGHT'] + 9
_name_chunk_start = NAME_Y
OL_STRIP_TOP    = _name_chunk_start + FONT_HEIGHTS['EXTRALARGE_LIGHT'] + 5
OL_STRIP_BOTTOM = OL_STRIP_TOP + FONT_HEIGHTS['SMALL_LIGHT'] + 5

# Volume strip geometry (module level, next to the other strip constants)
# bottom row: station clock when idle, alphabet dial while tuning, volume wedge while turning volume
CLOCK_Y = round(OL_STRIP_TOP + FONT_HEIGHTS['SMALL_LIGHT'] + 14) + 1
VOL_STRIP_TOP    = CLOCK_Y - 4
VOL_STRIP_BOTTOM = SCREEN_HEIGHT
DIAL_Y = VOL_STRIP_TOP + 2       # top of the dial letters
_vol_strip = Image.new('RGB', (SCREEN_WIDTH, VOL_STRIP_BOTTOM - VOL_STRIP_TOP), BLACK)

# ambient strip
AMB_BAR_Y        = 214                
AMB_STRIP_TOP    = AMB_BAR_Y - 1
AMB_STRIP_BOTTOM = AMB_BAR_Y + 25      
AMB_TEXT_X       = 9                  
AMB_RULE_H       = 1                   
_amb_strip = Image.new('RGB', (SCREEN_WIDTH, AMB_STRIP_BOTTOM - AMB_STRIP_TOP),
                       BLACK)

ambient_bar_color  = WHITE
ambient_text_color = BLACK
ambient_name = None
ambient_text_on_screen = None
 
ambient_mq = {'offset': 0, 'pause_until': 0, 'needed': False}

# Persistent scratch strips (allocated once, reused)
_name_strip = Image.new('RGB', (SCREEN_WIDTH, NAME_STRIP_BOTTOM - NAME_STRIP_TOP), BLACK)
_ol_strip   = Image.new('RGB', (SCREEN_WIDTH, OL_STRIP_BOTTOM - OL_STRIP_TOP), BLACK)

_name_metrics_cache = {}              

def _name_metrics(name):
    if name not in _name_metrics_cache:
        _, f = calculate_text(name, EXTRALARGE_LIGHT, 10**9, 1)
        _name_metrics_cache[name] = (f, width(name, f))
    return _name_metrics_cache[name]

def _name_dy(font):
    """Smaller name sizes shift down so every name sits on the 42px baseline."""
    return FONT_HEIGHTS['EXTRALARGE_LIGHT'] - height('Sg', font)

def _ol_text(info):
    """Canonical one-liner string. Must be the single source of truth --
    display_cached_scroll, the main loop, and _render_ol_strip all have to
    agree, or text_changed fires on every pass forever."""
    return (info.get('oneLiner') or '').replace('&amp;', '&').strip()

oneliner_mq  = {'offset': 0, 'pause_until': 0, 'needed': False}
name_mq  = {'offset': 0, 'pause_until': 0, 'needed': False}

def _mq_reset(mq, now):
    mq['offset'] = 0
    mq['pause_until'] = now + 3

PIXELS_PER_SEC = 50
WRAP_PAUSE = 5

def _joint_offsets(name_span, text_span, long_name, long_oneliner, now, mq):
    """Both tracks share one cycle clock so they restart together.
    mq holds the shared cycle start + initial pause. Returns (name_off, ol_off)."""
    # per-track scroll durations
    name_scroll_t = (name_span / PIXELS_PER_SEC) if long_name else 0
    ol_scroll_t   = (text_span / PIXELS_PER_SEC) if long_oneliner else 0

    # the joint cycle: slower track's scroll, then the shared wrap pause
    cycle_scroll = max(name_scroll_t, ol_scroll_t)
    cycle_len = cycle_scroll + WRAP_PAUSE

    # initial 3s lead-in before the very first scroll
    start = mq.get('cycle_start')
    if start is None:
        mq['cycle_start'] = now + 3      # matches your old _mq_reset lead-in
        return (0 if long_name else None), 0

    t = now - mq['cycle_start']
    if t < 0:
        # still in lead-in pause
        return (0 if long_name else None), 0

    phase = t % cycle_len   # where we are within the shared cycle

    def track_off(scroll_t, span, is_long):
        if not is_long:
            return None
        if phase >= scroll_t:
            return 0            # this track finished; wait at start for the cycle to roll
        return int(PIXELS_PER_SEC * phase)

    name_off = track_off(name_scroll_t, name_span, long_name)
    ol_off   = track_off(ol_scroll_t,   text_span, long_oneliner)
    # ol_off must be an int (0) not None when long_oneliner, matches render_frame's contract
    if long_oneliner and ol_off is None:
        ol_off = 0
    return name_off, ol_off

marquee_name = None
seek_token = 0
text_on_screen = None

MARQUEE_X = 12 + start_x                      # name_chunk_start_x
MARQUEE_GAP = 30                              # blank gap before the text repeats

FADE_W = 28
_fade_ramp = np.linspace(0.0, 1.0, FADE_W, dtype=np.float32)[None, :, None]

def _fade_right(img, y0, y1, x_end=SCREEN_WIDTH, color=None):
    """Fade the FADE_W px before x_end into `color` (default: background), so text slides out softly."""
    box = (int(x_end) - FADE_W, int(y0), int(x_end), int(y1))
    region = np.asarray(img.crop(box).convert('RGB'), dtype=np.float32)
    bg = np.array(color if color is not None else BG_COLOR, dtype=np.float32)
    out = region * (1 - _fade_ramp) + bg * _fade_ramp
    img.paste(Image.fromarray(out.astype(np.uint8), 'RGB'), box[:2])

def _render_vol_strip(volume):
    """Volume wedge: one cell per click of the knob, growing taller toward max."""
    d = ImageDraw.Draw(_vol_strip)
    h = _vol_strip.height
    d.rectangle([0, 0, SCREEN_WIDTH, h], fill=BG_COLOR)
    cells = max(1, MAX_VOL // volume_step)
    lit = round(volume / volume_step)
    gap = 4
    cw = (SCREEN_WIDTH - 2 * padding - (cells - 1) * gap) // cells
    x0 = (SCREEN_WIDTH - (cells * cw + (cells - 1) * gap)) // 2
    bottom = h - 3
    for k in range(cells):
        ch = 4 + round(16 * k / max(1, cells - 1))
        x = x0 + k * (cw + gap)
        d.rectangle([x, bottom - ch, x + cw - 1, bottom],
                    fill=SECONDARY_COLOR if k < lit else WEDGE_OFF_COLOR)
    return _vol_strip

# ---- station clock row: status dot + city, local time at the station ----
CLOCK_STRIP_TOP = VOL_STRIP_TOP
CLOCK_STRIP_BOTTOM = SCREEN_HEIGHT
_clock_strip = Image.new('RGB', (SCREEN_WIDTH, CLOCK_STRIP_BOTTOM - CLOCK_STRIP_TOP), BLACK)

def station_time(name):
    tz = (streams.get(name) or {}).get('timezone')
    if not tz:
        return ''
    try:
        return datetime.now(pytz.timezone(tz)).strftime('%I:%M%p').lstrip('0').lower()
    except Exception:
        return ''

def _draw_clock_row(draw, name, origin_y=0):
    """Live = yellow square, Re-Run = yellow outline square, anything else = grey square."""
    info = streams.get(name) or {}
    y = CLOCK_Y - origin_y
    cy = y + height('Sg', CLOCK_FONT) // 2 + 2
    cx, r = MARQUEE_X + 5, 4          # 9 px square: same visual weight as the old 11 px dot
    status = info.get('status')
    edge = None if BG_COLOR == BLACK else (60, 60, 60)
    if status == 'Live':
        draw.rectangle([cx - r, cy - r, cx + r, cy + r], fill=LIVE_COLOR, outline=edge, width=1)
    elif status == 'Re-Run':
        if edge:
            draw.rectangle([cx - r, cy - r, cx + r, cy + r], outline=edge, width=1)
            draw.rectangle([cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1], outline=LIVE_COLOR, width=2)
        else:
            draw.rectangle([cx - r, cy - r, cx + r, cy + r], outline=LIVE_COLOR, width=2)
    else:
        draw.rectangle([cx - r, cy - r, cx + r, cy + r], fill=STATUS_OFF_COLOR)
    draw.text((MARQUEE_X + 17, y), info.get('homeLocation') or info.get('location') or '', font=CLOCK_FONT, fill=SECONDARY_COLOR)
    t = station_time(name)
    if t:
        draw.text((SCREEN_WIDTH - 10 - width(t, CLOCK_FONT), y), t, font=CLOCK_FONT, fill=MUTED_COLOR)

SETTLED_LOGO_POS = (12, og_logo_position[1])
PANEL_X = SETTLED_LOGO_POS[0] + TILE + 16
PANEL_BOTTOM = og_logo_position[1] + TILE + 4
_panel = Image.new('RGB', (SCREEN_WIDTH - PANEL_X, PANEL_BOTTOM), BLACK)
_status_strip = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT - CLOCK_STRIP_TOP), BLACK)

def station_time_parts(name):
    tz = (streams.get(name) or {}).get('timezone')
    if not tz:
        return None
    try:
        now = datetime.now(pytz.timezone(tz))
    except Exception:
        return None
    return now.strftime('%I:%M').lstrip('0'), now.strftime('%p').lower()

def _draw_panel(draw, name, ox=0):
    """Big local time, then 'in <city>' (wraps to two lines) and 'from <guest city>'
    when a show comes from somewhere else; the whole block is
    vertically centred against the logo, so one- and two-line cities both sit right."""
    info = streams.get(name) or {}
    city = (info.get('homeLocation') or info.get('location') or '').strip()
    parts = station_time_parts(name)
    label = (f'in {city}' if city else '') if parts else city
    max_w = SCREEN_WIDTH - PANEL_X - 8
    lines, f = calculate_text(label, CLOCK_FONT, max_w, 2) if label else ([], CLOCK_FONT)
    # where tonight's show is coming from, when it isn't the station's home (NTS guests)
    guest = (info.get('location') or '').strip()
    if guest and city and guest.casefold() != city.casefold():
        g = f'from {guest}'
        if width(g, f) > max_w and ',' in guest:
            g = f"from {guest.split(',')[0].strip()}"      # 'Rio de Janeiro, Brazil' -> 'Rio de Janeiro'
        while width(g, f) > max_w and len(g) > 6:
            g = g[:-4].rstrip(' ,') + '...'
        lines = list(lines) + [g]
    line_h = height('Sg', f) + 5

    # lay out relative to y = 0, measure the inked block, then shift it to centre
    if parts:
        hm, ap = parts
        top = TIME_FONT.getbbox(hm)[1]
        baseline = TIME_FONT.getmetrics()[0]
        city_y = baseline + 13
        bottom = baseline
    else:
        top, city_y, bottom = f.getbbox('Sg')[1], 0, 0
    if lines:
        bottom = city_y + (len(lines) - 1) * line_h + f.getbbox(lines[-1].strip())[3]   # real ink, not a descender guess
    centre = SETTLED_LOGO_POS[1] + TILE / 2
    y0 = round(centre - (bottom - top) / 2 - top)

    x = PANEL_X - ox
    if parts:
        draw.text((x, y0), hm, font=TIME_FONT, fill=SECONDARY_COLOR)
        draw.text((x + width(hm, TIME_FONT) + 5, y0 + baseline), ap, font=CLOCK_FONT,
                  fill=SECONDARY_COLOR, anchor='ls')
    for i, ln in enumerate(lines):
        draw.text((x, y0 + city_y + i * line_h), ln.strip(), font=f, fill=MUTED_COLOR)

def push_panel(name):
    """Redraw just the time panel (the minute ticked over)."""
    d = ImageDraw.Draw(_panel)
    d.rectangle([0, 0, _panel.width, _panel.height], fill=BG_COLOR)
    _draw_panel(d, name, ox=PANEL_X)
    if display_lock.acquire(timeout=0.5):
        try:
            disp.ShowWindow(_panel, PANEL_X, 0)
        finally:
            display_lock.release()

def render_status_strip(name):
    """Settled bottom row: status square + word, then genres in muted text."""
    d = ImageDraw.Draw(_status_strip)
    d.rectangle([0, 0, SCREEN_WIDTH, _status_strip.height], fill=BG_COLOR)
    info = streams.get(name) or {}
    status = info.get('status') or 'Offline'
    y = CLOCK_Y - CLOCK_STRIP_TOP
    cy = y + height('Sg', CLOCK_FONT) // 2 + 2
    cx, r = MARQUEE_X + 5, 4          # 9 px square: same visual weight as the old 11 px dot
    edge = None if BG_COLOR == BLACK else (60, 60, 60)
    tstate = tuning['state'] if tuning['name'] == name else None
    if tstate:
        if tstate == 'tuning':
            lit = int(time.monotonic() * 2.5) % 2 == 0                      # gentle pulse
            dot = LIVE_COLOR if lit else _mix(LIVE_COLOR, BG_COLOR, 0.7)
            label = 'Tuning in...'
        else:
            dot, label = STATUS_OFF_COLOR, "Station isn't answering"
        d.rectangle([cx - r, cy - r, cx + r, cy + r], fill=dot, outline=edge, width=1)
        d.text((MARQUEE_X + 17, y - 1), label, font=CLOCK_FONT, fill=MUTED_COLOR)
        return _status_strip
    if status == 'Live':
        d.rectangle([cx - r, cy - r, cx + r, cy + r], fill=LIVE_COLOR, outline=edge, width=1)
    elif status == 'Re-Run':
        d.rectangle([cx - r, cy - r, cx + r, cy + r], outline=edge or LIVE_COLOR, width=1 if edge else 2)
        if edge:
            d.rectangle([cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1], outline=LIVE_COLOR, width=2)
    else:
        d.rectangle([cx - r, cy - r, cx + r, cy + r], fill=STATUS_OFF_COLOR)
    x = MARQUEE_X + 17
    d.text((x, y - 1), status, font=CLOCK_FONT, fill=SECONDARY_COLOR)
    genres = ' · '.join(info.get('genres') or [])
    if genres:
        gx = x + width(status, CLOCK_FONT) + 10
        d.text((gx, y - 1), genres, font=CLOCK_FONT, fill=MUTED_COLOR)
        if gx + width(genres, CLOCK_FONT) > SCREEN_WIDTH:
            _fade_right(_status_strip, 0, _status_strip.height)
    return _status_strip

def push_status_strip(name):
    strip = render_status_strip(name)
    if display_lock.acquire(timeout=0.5):
        try:
            disp.ShowWindow(strip, 0, CLOCK_STRIP_TOP)
        finally:
            display_lock.release()

def render_clock_strip(name):
    d = ImageDraw.Draw(_clock_strip)
    d.rectangle([0, 0, SCREEN_WIDTH, _clock_strip.height], fill=BG_COLOR)
    _draw_clock_row(d, name, origin_y=CLOCK_STRIP_TOP)
    return _clock_strip

def push_clock_strip(name):
    """Redraw only the clock row, e.g. when the minute changes."""
    strip = render_clock_strip(name)
    if display_lock.acquire(timeout=0.5):
        try:
            disp.ShowWindow(strip, 0, CLOCK_STRIP_TOP)
        finally:
            display_lock.release()

def _render_name_strip(name, offset):
    font, full_w = _name_metrics(name)
    d = ImageDraw.Draw(_name_strip)
    d.rectangle([0, 0, SCREEN_WIDTH, _name_strip.height], fill=BG_COLOR)  # clear
    span = full_w + MARQUEE_GAP
    start = MARQUEE_X - (offset % span)
    y = (NAME_Y - 1) - NAME_STRIP_TOP + _name_dy(font)  # absolute y minus strip origin
    d.text((start - 1, y), name, font=font, fill=SECONDARY_COLOR)
    d.text((start - 1 + span, y), name, font=font, fill=SECONDARY_COLOR)
    d.rectangle([0, 0, MARQUEE_X - 1, _name_strip.height], fill=BG_COLOR)  # left gutter
    _fade_right(_name_strip, 0, _name_strip.height)
    return _name_strip

_text_tile_cache = {}

def text_tile(text, height, fg, bg):
    """The text rendered ONCE into its own image (advance width + MARQUEE_GAP).
    Marquee frames just paste this bitmap at an offset -- no font rendering per
    frame, which is what made Cyrillic/CJK (fallback fonts) scroll choppily."""
    key = (text, height, fg, bg)
    tile = _text_tile_cache.get(key)
    if tile is None:
        tile = Image.new('RGB', (max(1, text_width(text) + MARQUEE_GAP), height), bg)
        draw_text_mixed(ImageDraw.Draw(tile), (0, 0), text, fg)
        if len(_text_tile_cache) > 64:
            _text_tile_cache.clear()
        _text_tile_cache[key] = tile
    return tile

def _paste_marquee(strip, tile, start, y=0):
    x = start
    while x < SCREEN_WIDTH:
        strip.paste(tile, (int(x), y))
        x += tile.width

def _render_ol_strip(name, offset):
    text = _ol_text(streams[name])
    tile = text_tile(text, _ol_strip.height, SECONDARY_COLOR, BG_COLOR)
    _ol_strip.paste(BG_COLOR, (0, 0, SCREEN_WIDTH, _ol_strip.height))
    _paste_marquee(_ol_strip, tile, MARQUEE_X - (offset % tile.width))
    _ol_strip.paste(BG_COLOR, (0, 0, MARQUEE_X, _ol_strip.height))      # left gutter
    _fade_right(_ol_strip, 0, _ol_strip.height)
    return _ol_strip

def _mix(a, b, t):
    return tuple(round(a[k] * (1 - t) + b[k] * t) for k in range(3))

def _amb_time_text():
    parts = station_time_parts(ambient_name) if ambient_name else None
    return (parts[0] + parts[1]) if parts else ''

def _amb_seg_w():
    """Width of the time segment at the right end of the ambient bar (0 if no time)."""
    t = _amb_time_text()
    return width(t, CLOCK_FONT) + 20 if t else 0

def _render_amb_strip(text, offset=None):
    """The ambient screen's bottom bar.
 
    offset=None draws the text once, flush left -- the static bar.
    offset=N draws it twice, span apart, scrolled by N -- one marquee frame.
    display_bar renders through this too, so the static bar and the
    scrolling bar line up to the pixel and the handoff is invisible.
    """
    d = ImageDraw.Draw(_amb_strip)
    h = _amb_strip.height
 
    d.rectangle([0, 0, SCREEN_WIDTH, h], fill=ambient_bar_color)
 
    y = (AMB_BAR_Y + 1) - AMB_STRIP_TOP     # absolute y minus strip origin
 
    if offset is None:
        draw_text_mixed(d, (AMB_TEXT_X, y), text, ambient_text_color)
    else:
        tile = text_tile(text, h - y, ambient_text_color, ambient_bar_color)
        _paste_marquee(_amb_strip, tile, AMB_TEXT_X - (offset % tile.width), y)
        # left gutter, so text never touches the panel edge
        d.rectangle([0, 0, AMB_TEXT_X - 1, h], fill=ambient_bar_color)
 
    # station time in its own segment on the right; the one-liner fades out before it
    rule = _mix(ambient_text_color, ambient_bar_color, 0.55)       # softer than full contrast
    seg = _amb_seg_w()
    if seg:
        x0 = SCREEN_WIDTH - seg
        _fade_right(_amb_strip, AMB_RULE_H, h, x_end=x0, color=ambient_bar_color)
        d.rectangle([x0, 0, SCREEN_WIDTH, h], fill=ambient_bar_color)
        d.rectangle([x0, 5, x0, h - 4], fill=rule)
        t = _amb_time_text()
        d.text((x0 + 10, y + 1), t, font=CLOCK_FONT, fill=ambient_text_color)
    elif offset is not None:
        _fade_right(_amb_strip, AMB_RULE_H, h, color=ambient_bar_color)

    # rule last, so neither the text nor the gutter can clip it
    d.rectangle([0, 0, SCREEN_WIDTH, AMB_RULE_H - 1], fill=rule)
    return _amb_strip
 
 
def render_ambient_frame(text, offset=None):
    """Push one ambient bar frame. Non-blocking on the lock: a dropped
    marquee frame is invisible, a stalled main loop is not."""
    if currently_displaying != 'ambient':
        return
    if not display_lock.acquire(blocking=False):
        return
    try:
        if currently_displaying != 'ambient':
            return
        if ambient_show:
            disp.ShowWindow(_render_show_l1(text, offset), SHOW_TEXT_X, SHOW_L1_Y)
        else:
            disp.ShowWindow(_render_amb_strip(text, offset), 0, AMB_STRIP_TOP)
    finally:
        display_lock.release()

def render_frame(name, offset=0, volume=None, draw_oneliner=True, name_offset=None, must_show=False):
    # guard unchanged
    if (readied_stream if readied_stream else stream) != name:
        return

    if must_show or volume is not None:
        acquired = display_lock.acquire(timeout=0.5)
    else:
        acquired = display_lock.acquire(blocking=False)
    if not acquired:
        return
    try:
        if (readied_stream if readied_stream else stream) != name:
            return
        if name_offset is not None:
            disp.ShowWindow(_render_name_strip(name, name_offset), 0, NAME_STRIP_TOP)
        if draw_oneliner:
            disp.ShowWindow(_render_ol_strip(name, offset), 0, OL_STRIP_TOP)
        if volume is not None:
            # volume bar strip — same treatment
            disp.ShowWindow(_render_vol_strip(volume), 0, VOL_STRIP_TOP)
    finally:
        display_lock.release()

DIM = 0.40                     # default fade amount toward the background
FADE = {1: 0.45, 2: 0.72}      # neighbours, then the outer pair

_logo_size_cache = {}
def logo_at(name, size):
    """Station logo at `size`; sizes the server doesn't ship are scaled from the 216px PNG."""
    info = streams[name]
    key = f'logo_{size}'
    if key in info:
        return info[key]
    src = info['logo_216']
    hit = _logo_size_cache.get((name, size))
    if hit is not None and hit[0] is src:
        return hit[1]
    out = src.resize((size, size), Image.LANCZOS)
    _logo_size_cache[(name, size)] = (src, out)
    return out

_dim_cache = {}

def dim_logo(name, size, factor=DIM):
    """Darkened copy of a station logo. Cached, and keyed on the source
    image's identity so it re-dims automatically when fetch_logos swaps
    in a new PNG."""
    src = logo_at(name, size)
    key = (name, size, factor)
    hit = _dim_cache.get(key)
    if hit is not None and hit[0] is src:
        return hit[1]
    out = Image.blend(src.convert('RGB'), Image.new('RGB', src.size, BG_COLOR), factor)
    _dim_cache[key] = (src, out)
    return out

_dim_rgba_cache = {}

def dim_rgba(img, factor=DIM):
    """Darken an RGBA overlay without touching its alpha channel.
    ImageEnhance.Brightness scales every band, so running it on RGBA
    directly would fade the mask and leave the star translucent."""
    key = (id(img), factor)
    hit = _dim_rgba_cache.get(key)
    if hit is not None and hit[0] is img:
        return hit[1]
    r, g, b, a = img.split()
    rgb = Image.blend(Image.merge('RGB', (r, g, b)), Image.new('RGB', img.size, BG_COLOR), factor)
    out = Image.merge('RGBA', (*rgb.split(), a))
    _dim_rgba_cache[key] = (img, out)
    return out

def draw_tile(image, draw, station, pos, star=None, size=TILE, dim=True, fade=None):
    """Logo (faded toward the background unless active), star, then the double border."""
    amount = 0 if not dim else (FADE[1] if fade is None else fade)
    image.paste(dim_logo(station, size, amount) if amount
                else logo_at(station, size), pos)

    if star is not None and station in favorites:
        s = dim_rgba(star, amount) if amount else star
        image.paste(s, (pos[0] + size - s.width, pos[1]), s)   # star stays top-right

    x0, y0 = pos
    x1, y1 = x0 + size, y0 + size
    outline = tuple(round(SECONDARY_COLOR[k] * (1 - amount) + BG_COLOR[k] * amount) for k in range(3))
    draw.rectangle([x0, y0, x1, y1], outline=outline, width=2)   # thin frame
    # background gap just outside the frame (2 px, so it doesn't eat the frame itself)
    draw.rectangle([x0 - 2, y0 - 2, x1 + 2, y1 + 2], outline=BG_COLOR, width=2)

def display_scroll(name, silent=False):
    global streams, play_status, first_display, selector, start_x, currently_displaying
    
    if not restarting:

        first_display = False
        len_stream_list = len(stream_list)
        i = stream_list.index(name)
        n = len_stream_list
        prev_stream        = stream_list[(i - 1) % n]
        double_prev_stream = stream_list[(i - 2) % n]
        next_stream        = stream_list[(i + 1) % n]
        double_next_stream = stream_list[(i + 2) % n]

        image = Image.new('RGBA', (SCREEN_WIDTH, SCREEN_HEIGHT), color=BG_COLOR)
        draw = ImageDraw.Draw(image) 
        
        if not silent:
            currently_displaying = 'everything'

        # logos
        prev_position        = (og_logo_position[0] - 70, og_logo_position[1])
        next_position        = (og_logo_position[0] + 70, og_logo_position[1])
        double_prev_position = (prev_position[0] - 49, prev_position[1])
        double_next_position = (next_position[0] + 43, prev_position[1])

        # back to front, so each tile's border is trimmed by the one in front
        draw_tile(image, draw, double_prev_stream, double_prev_position, star_96, fade=FADE[2])
        draw_tile(image, draw, double_next_stream, double_next_position, star_96, fade=FADE[2])
        draw_tile(image, draw, prev_stream,        prev_position,        star_96)
        draw_tile(image, draw, next_stream,        next_position,        star_96)
        draw_tile(image, draw, name,               logo_position,        star_96,
                  dim=False)

        # draw name and underline
        name_chunk_start = NAME_Y
        name_chunk_start_x = 12 + start_x
        name_font = EXTRALARGE_LIGHT

        name_font, name_w = _name_metrics(name)
        draw.text((name_chunk_start_x - 1, name_chunk_start - 1 + _name_dy(name_font)), name, font=name_font, fill=SECONDARY_COLOR)
        if name_chunk_start_x + name_w > SCREEN_WIDTH:
            _fade_right(image, NAME_STRIP_TOP, NAME_STRIP_BOTTOM)

        # draw info
        info_font = SMALL_LIGHT
        y_offset = 0
        everything_info_y = name_chunk_start + FONT_HEIGHTS['EXTRALARGE_LIGHT'] + 5
        info_line = streams[name]['oneLiner']
        info_line = _ol_text(streams[name])
        draw_text_mixed(draw, (name_chunk_start_x, everything_info_y + y_offset), info_line, SECONDARY_COLOR)
        if name_chunk_start_x + text_width(info_line) > SCREEN_WIDTH:
            _fade_right(image, OL_STRIP_TOP, OL_STRIP_BOTTOM)
        y_offset += 20

        # station clock row (replaces the tags)
        _draw_clock_row(draw, name)

        # the alphabet dial and seek arrows are overlays, shown only while scrolling (show_seek_overlay)
        
        if BRIGHTNESS != 1:
            image = ImageEnhance.Brightness(image).enhance(BRIGHTNESS)

        if not silent: 
            with display_lock:
                    disp.ShowImage(image)   
        return image
        #safe_display(image)

def display_bar(image, text, color=WHITE):
    global ambient_bar_color, ambient_text_color
    if image is None:
        return
 
    r, g, b = color[:3]
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    ambient_bar_color = (r, g, b)
    ambient_text_color = WHITE if luminance < 128 else BLACK
 
    image.paste(_render_amb_strip(text), (0, AMB_STRIP_TOP))
 
 
def _mode_color(img):
    arr = np.asarray(img.convert('RGB')).reshape(-1, 3)
    colors, counts = np.unique(arr, axis=0, return_counts=True)
    return tuple(int(c) for c in colors[counts.argmax()])


# ---- show art on ambient ----------------------------------------------------
# When the station publishes art for the show that's on, ambient looks like the
# show cards in the One Radio app: the image fills the screen, a dark gradient
# rises from the bottom, and the station logo sits in the corner beside the
# now-playing line and the station name + local time. No art -> classic ambient.
# /summary passes the station's own (dynamic) `showLogo` URL; we fetch it,
# cover-crop to 320x240 here, and skip images that would look bad.
SHOW_ART_ON = get_config().get('show_art', True)   # "show_art": false in config.json turns it off
SHOW_LOGO = 48
SHOW_PAD = 12
SHOW_TEXT_X = SHOW_PAD + SHOW_LOGO + 12
SHOW_L1_Y, SHOW_L1_H = SCREEN_HEIGHT - SHOW_PAD - SHOW_LOGO - 3, 26   # now-playing line
SHOW_L2_Y, SHOW_L2_H = SHOW_L1_Y + SHOW_L1_H, 24                      # station + local time
SHOW_GRAD_TOP = 100
SHOW_SUB = (205, 205, 205)
ART_CACHE_MAX = 12

art_lock = threading.Lock()
show_art_cache = OrderedDict()      # url -> 320x240 RGB image
_art_inflight = set()
_art_failed = {}                    # url -> monotonic time of the failure
ambient_show = False                # ambient is currently in show-art mode
ambient_art_url = None
_show_base = None                   # art + gradient + logo, no text

SHOW_ART_MAX_BYTES = 8_000_000

def _prepare_show_art(data):
    """Raw image bytes -> 320x240 cover crop, or None if it would look bad."""
    img = Image.open(BytesIO(data))
    img.draft('RGB', (SCREEN_WIDTH * 2, SCREEN_HEIGHT * 2))    # JPEGs decode at reduced size (fast on the Pi)
    img = ImageOps.exif_transpose(img)
    if img.mode in ('RGBA', 'LA', 'P') or 'transparency' in img.info:
        img = img.convert('RGBA')
        img = Image.alpha_composite(Image.new('RGBA', img.size, (0, 0, 0, 255)), img)
    img = img.convert('RGB')
    w, h = img.size
    if min(w, h) < 200:                  # too small: mushy full-screen
        return None
    if max(w, h) / min(w, h) > 2.4:      # long banners crop badly
        return None
    if max(w, h) > 1400:                 # big PNGs: shrink before the high-quality fit
        img.thumbnail((1400, 1400), Image.BILINEAR)
    img = ImageOps.fit(img, (SCREEN_WIDTH, SCREEN_HEIGHT), Image.LANCZOS)
    lo, hi = img.convert('L').getextrema()
    if hi - lo < 12:                     # flat placeholder
        return None
    return img

def _fetch_show_art(url):
    try:
        with requests.get(url, timeout=6, stream=True,
                          headers={'User-Agent': 'Mozilla/5.0 (Otis radio)'}) as resp:
            resp.raise_for_status()
            data = bytearray()
            for chunk in resp.iter_content(65536):
                data += chunk
                if len(data) > SHOW_ART_MAX_BYTES:
                    raise ValueError('image too large')
        img = _prepare_show_art(bytes(data))
        if img is None:
            raise ValueError('image unsuitable for full-screen')
        with art_lock:
            show_art_cache[url] = img
            show_art_cache.move_to_end(url)
            while len(show_art_cache) > ART_CACHE_MAX:
                show_art_cache.popitem(last=False)
    except Exception as e:
        _art_failed[url] = time.monotonic()
        logging.error(f'show art fetch failed ({url}): {e}')
    finally:
        _art_inflight.discard(url)

def ensure_show_art(name):
    """Start fetching the current show's art in the background (no-op if cached/in flight)."""
    if not SHOW_ART_ON:
        return
    url = (streams.get(name) or {}).get('showLogo')
    if not url or url in show_art_cache or url in _art_inflight:
        return
    if time.monotonic() - _art_failed.get(url, -1e9) < 1800:     # failed/unsuitable: wait 30 min
        return
    _art_inflight.add(url)
    threading.Thread(target=_fetch_show_art, args=(url,), daemon=True).start()

def show_art(name):
    """The current show's art if it's ready, else None (and start fetching it)."""
    if not SHOW_ART_ON:
        return None
    url = (streams.get(name) or {}).get('showLogo')
    if not url:
        return None
    img = show_art_cache.get(url)
    if img is None:
        ensure_show_art(name)
    return img

_show_grad = None
def _show_gradient():
    """Darkening per row, like the app's card overlay: clear at the top, 70% a bit
    past halfway down, 85% at the bottom edge."""
    global _show_grad
    if _show_grad is None:
        a = np.zeros((SCREEN_HEIGHT, 1, 1), np.float32)
        span = SCREEN_HEIGHT - SHOW_GRAD_TOP
        for y in range(SHOW_GRAD_TOP, SCREEN_HEIGHT):
            t = (y - SHOW_GRAD_TOP) / span
            a[y] = 0.7 * (t / 0.55) ** 1.4 if t < 0.55 else 0.7 + 0.15 * (t - 0.55) / 0.45
        _show_grad = a
    return _show_grad

def _compose_show_base(name, art):
    arr = np.asarray(art.convert('RGB'), np.float32) * (1 - _show_gradient())
    base = Image.fromarray(arr.astype(np.uint8), 'RGB')
    base.paste(logo_at(name, SHOW_LOGO), (SHOW_PAD, SCREEN_HEIGHT - SHOW_PAD - SHOW_LOGO))
    if BRIGHTNESS != 1:
        base = ImageEnhance.Brightness(base).enhance(BRIGHTNESS)
    return base

_mask_tile_cache = {}
def text_mask_tile(text, height):
    """Like text_tile, but an alpha mask, so text can sit on a photo instead of a flat bar."""
    key = (text, height)
    tile = _mask_tile_cache.get(key)
    if tile is None:
        tile = Image.new('L', (max(1, text_width(text) + MARQUEE_GAP), height), 0)
        draw_text_mixed(ImageDraw.Draw(tile), (0, 0), text, 255)
        if len(_mask_tile_cache) > 32:
            _mask_tile_cache.clear()
        _mask_tile_cache[key] = tile
    return tile

def _fade_mask_right(mask):
    m = np.asarray(mask, np.float32).copy()
    m[:, -FADE_W:] *= (1 - _fade_ramp[0, :, 0])
    return Image.fromarray(m.astype(np.uint8), 'L')

def _render_show_l1(text, offset=None):
    """The now-playing line over the art; offset=N is one marquee frame."""
    w = SCREEN_WIDTH - SHOW_TEXT_X
    strip = _show_base.crop((SHOW_TEXT_X, SHOW_L1_Y, SCREEN_WIDTH, SHOW_L1_Y + SHOW_L1_H))
    tile = text_mask_tile(text, SHOW_L1_H)
    mask = Image.new('L', (w, SHOW_L1_H), 0)
    if offset is None:
        mask.paste(tile, (0, 0))
    else:
        x = -(offset % tile.width)
        while x < w:
            mask.paste(tile, (int(x), 0))
            x += tile.width
    if offset is not None or text_width(text) > w - SHOW_PAD:
        mask = _fade_mask_right(mask)
    strip.paste(WHITE, (0, 0, w, SHOW_L1_H), mask)
    return strip

def _render_show_l2(name):
    """Station name and its local time, under the now-playing line."""
    w = SCREEN_WIDTH - SHOW_TEXT_X
    strip = _show_base.crop((SHOW_TEXT_X, SHOW_L2_Y, SCREEN_WIDTH, SHOW_L2_Y + SHOW_L2_H))
    parts = station_time_parts(name)
    label = name + (f' · {parts[0]} {parts[1]}' if parts else '')
    mask = Image.new('L', (w, SHOW_L2_H), 0)
    ImageDraw.Draw(mask).text((0, 1), label, font=CLOCK_FONT, fill=255)
    if width(label, CLOCK_FONT) > w - SHOW_PAD:
        mask = _fade_mask_right(mask)
    strip.paste(SHOW_SUB, (0, 0, w, SHOW_L2_H), mask)
    return strip

def push_show_l2(name):
    if currently_displaying != 'ambient' or not ambient_show:
        return
    if not display_lock.acquire(blocking=False):
        return
    try:
        if currently_displaying == 'ambient' and ambient_show:
            disp.ShowWindow(_render_show_l2(name), SHOW_TEXT_X, SHOW_L2_Y)
    finally:
        display_lock.release()

def _amb_avail_w():
    """Room for the one-liner before it has to scroll."""
    if ambient_show:
        return SCREEN_WIDTH - SHOW_TEXT_X - SHOW_PAD
    return SCREEN_WIDTH - AMB_TEXT_X - 6 - _amb_seg_w()

def _display_show_ambient(name, info, art):
    global currently_displaying, last_ambient_display, ambient_name, ambient_text_on_screen
    global ambient_show, ambient_art_url, _show_base
    _show_base = _compose_show_base(name, art)
    text = _ol_text(info)
    image = _show_base.copy()
    image.paste(_render_show_l1(text), (SHOW_TEXT_X, SHOW_L1_Y))
    image.paste(_render_show_l2(name), (SHOW_TEXT_X, SHOW_L2_Y))
    currently_displaying = 'ambient'
    ambient_name = name
    ambient_show = True
    ambient_art_url = info.get('showLogo')
    ambient_text_on_screen = text
    ambient_mq['cycle_start'] = None
    logging.info('DISPLAY AMBIENT (show art) %s', name)
    safe_display(image)
    last_ambient_display = time.monotonic()


def display_ambient(name):
    global currently_displaying, last_ambient_display
    global ambient_name, ambient_text_on_screen
 
    global ambient_show, ambient_art_url
    info = streams.get(name)
    if info is None:
        return

    art = show_art(name)
    if art is not None:
        _display_show_ambient(name, info, art)
        return
    ambient_show = False
    ambient_art_url = None

    logo = info['logo_216']
    logo_w, logo_h = logo.size
    # sides take the logo's most common edge colour; repeating the edge pixel column streaked busy logos
    first_pixel = _mode_color(logo.crop((0, 0, 3, logo_h)))
    right_color = _mode_color(logo.crop((logo_w - 3, 0, logo_w, logo_h)))
    image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT), color=first_pixel)
    ImageDraw.Draw(image).rectangle([52 + logo_w, 0, SCREEN_WIDTH, SCREEN_HEIGHT], fill=right_color)
    image.paste(logo, (52, 2))
 
    currently_displaying = 'ambient'
    ambient_name = name
    logging.info('DISPLAY AMBIENT BEING CALLED')
 
    text = _ol_text(info)
    ambient_text_on_screen = text
    ambient_mq['cycle_start'] = None          # marquee starts from the top
 
    if BRIGHTNESS != 1:
        image = ImageEnhance.Brightness(image).enhance(BRIGHTNESS)
 
    # Bar AFTER the brightness pass. The marquee strips that replace it
    # later are never brightness-scaled, so scaling it here would make the
    # bar visibly jump the moment the marquee takes over.
    display_bar(image, text, color=first_pixel)
 
    safe_display(image)
    last_ambient_display = time.monotonic()


# ---- AirPlay (shairport-sync) ------------------------------------------------
# shairport-sync receives AirPlay and plays through its own ALSA device
# ("airplay" in /etc/asound.conf: a soft-volume control in front of the shared
# dmix), so it never fights mpv for the DAC. We read its metadata pipe for
# play begin/end, track info and cover art. While AirPlay plays, the radio
# steps aside: mpv stops, the screen shows the cover in the show-art layout,
# the volume knob sets the AirPlay level, and the station knob (or picking a
# station anywhere) ends the session and brings the radio back. When the phone
# pauses or disconnects, nothing happens: the last track stays on screen and
# the radio stays quiet until someone touches it.
AIRPLAY_PIPE = '/tmp/shairport-sync-metadata'
AIRPLAY_CARD = 'sndrpihifiberry'
AIRPLAY_CONTROL = 'AirPlay'
AIRPLAY_BG = (26, 26, 26)

airplay_lock = threading.Lock()
airplay = {'active': False, 'title': '', 'artist': '', 'album': '', 'sender': '',
           'art': None, 'thumb': None, 'dirty': False, 'pending': {}}
airplay_mq = {'offset': 0, 'pause_until': 0, 'needed': False}
airplay_volume = get_config().get('airplay_volume')     # None -> start from the radio's level
airplay_vol_until = 0.0
_airplay_t1 = ''

_AP_ITEM = re.compile(r'<type>([0-9a-f]{8})</type><code>([0-9a-f]{8})</code><length>(\d+)</length>'
                      r'(?:\s*<data encoding="base64">\s*(.*?)</data>)?', re.S)

def _ap_word(hexstr):
    return bytes.fromhex(hexstr).decode('latin-1')

def _prepare_cover(data):
    """Cover art bytes -> (320x240 full-bleed crop, uncropped square for the corner tile)."""
    try:
        img = Image.open(BytesIO(data))
        img.draft('RGB', (SCREEN_WIDTH * 2, SCREEN_WIDTH * 2))
        img = img.convert('RGB')
        if min(img.size) < 32:
            return None, None
        return (ImageOps.fit(img, (SCREEN_WIDTH, SCREEN_HEIGHT), Image.LANCZOS),
                ImageOps.fit(img, (SHOW_LOGO, SHOW_LOGO), Image.LANCZOS))
    except Exception as e:
        logging.error(f'airplay cover: {e}')
        return None, None

def _airplay_event(typ, code, data):
    text = lambda: data.decode('utf-8', 'replace').strip()
    with airplay_lock:
        p = airplay['pending']
        if typ == 'core':
            if code == 'minm':
                p['title'] = text()
            elif code == 'asar':
                p['artist'] = text()
            elif code == 'asal':
                p['album'] = text()
        elif typ == 'ssnc':
            if code == 'mdst':                       # a metadata bundle begins
                airplay['pending'] = {}
            elif code == 'mden':                     # ...and ends: commit it
                for k in ('title', 'artist', 'album'):
                    airplay[k] = p.get(k, '')
                airplay['dirty'] = True
            elif code == 'PICT':
                airplay['art'], airplay['thumb'] = _prepare_cover(data) if data else (None, None)
                airplay['dirty'] = True
            elif code in ('pbeg', 'prsm'):           # play begins / resumes
                if not airplay['active']:
                    airplay.update(active=True, title='', artist='', album='', art=None, thumb=None)
                airplay['dirty'] = True
            elif code == 'pend':                     # sender disconnected
                airplay['active'] = False
                airplay['dirty'] = True
            elif code == 'snam':
                airplay['sender'] = text()

def _airplay_reader():
    while True:
        try:
            if not os.path.exists(AIRPLAY_PIPE):
                time.sleep(2)
                continue
            with open(AIRPLAY_PIPE, 'r', encoding='ascii', errors='ignore') as f:   # blocks until shairport writes
                buf = ''
                for line in f:
                    buf += line
                    while '</item>' in buf:
                        item, buf = buf.split('</item>', 1)
                        m = _AP_ITEM.search(item)
                        if not m:
                            continue
                        data = b''
                        if m.group(4):
                            try:
                                data = base64.b64decode(re.sub(r'\s', '', m.group(4)))
                            except Exception:
                                pass
                        _airplay_event(_ap_word(m.group(1)), _ap_word(m.group(2)), data)
            time.sleep(0.5)        # shairport closed the pipe (restart): reopen
        except Exception as e:
            logging.error(f'airplay reader: {e}')
            time.sleep(2)

def _bg(cmd):
    try:
        Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        logging.error(f'{cmd[0]}: {e}')

def _set_airplay_volume(v):
    """Knob units (0..MAX_VOL, same notches as the radio) -> AirPlay soft volume.
    Same cubic curve mpv uses, so a notch sounds alike on radio and AirPlay;
    above 100 there's no headroom to boost, so it stays at 0 dB."""
    if v <= 0:
        level = '0%'
    else:
        level = f'{max(-60.0, 60 * math.log10(min(v, 100) / 100)):.1f}dB'
    _bg(['amixer', '-q', '-c', AIRPLAY_CARD, 'sset', AIRPLAY_CONTROL, '--', level])

def _airplay_init_volume():
    """The soft-volume control only exists once its device has been opened, so
    open it with a second of silence at startup, then set the saved level --
    otherwise the first AirPlay track could start at full volume."""
    try:
        run(['aplay', '-q', '-D', 'airplay', '-f', 'S16_LE', '-r', '44100', '-c', '2', '-d', '1', '/dev/zero'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except Exception:
        pass
    _set_airplay_volume(airplay_volume if airplay_volume is not None else current_volume)

def _airplay_glyph(draw, box, color, width):
    """The AirPlay mark: a screen with a triangle rising into its bottom edge."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    sy1 = y0 + round(h * 0.68)
    draw.rounded_rectangle([x0, y0, x1, sy1], radius=max(2, w // 12), outline=color, width=width)
    cx, tw = (x0 + x1) / 2, w * 0.46
    gap = width + 2
    halo = [(cx, y0 + h * 0.50 - gap), (cx + tw / 2 + gap * 1.4, y1 + 1), (cx - tw / 2 - gap * 1.4, y1 + 1)]
    return halo, [(cx, y0 + h * 0.50), (cx + tw / 2, y1), (cx - tw / 2, y1)]

def _airplay_tile(size):
    t = Image.new('RGB', (size, size), WHITE)
    d = ImageDraw.Draw(t)
    m = round(size * 0.2)
    halo, tri = _airplay_glyph(d, (m, m + 1, size - m - 1, size - m), BLACK, max(2, size // 16))
    d.polygon(halo, fill=WHITE)
    d.polygon(tri, fill=BLACK)
    return t

def _compose_airplay_base(art, thumb=None):
    if art is None:                           # no cover yet / none sent: big faint AirPlay mark
        art = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT), AIRPLAY_BG)
        d = ImageDraw.Draw(art)
        halo, tri = _airplay_glyph(d, (110, 34, 210, 124), (70, 70, 70), 6)
        d.polygon(halo, fill=AIRPLAY_BG)
        d.polygon(tri, fill=(70, 70, 70))
    arr = np.asarray(art.convert('RGB'), np.float32) * (1 - _show_gradient())
    base = Image.fromarray(arr.astype(np.uint8), 'RGB')
    # the cover itself in the corner (uncropped), the AirPlay mark only when there's no cover
    corner = thumb if thumb is not None else _airplay_tile(SHOW_LOGO)
    base.paste(corner, (SHOW_PAD, SCREEN_HEIGHT - SHOW_PAD - SHOW_LOGO))
    if BRIGHTNESS != 1:
        base = ImageEnhance.Brightness(base).enhance(BRIGHTNESS)
    return base

_small_fallbacks = None
def _render_ap_l2(text):
    """Artist line under the title: Favorit 17 like the station line, with
    per-glyph fallback (artists are often Japanese, Korean, Cyrillic...)."""
    global _small_fallbacks
    if _small_fallbacks is None:
        _small_fallbacks = [f for f in (_load_fallback(p, 16) for p in (
            'assets/Noto_Sans/NotoSans-VariableFont_wdth,wght.ttf',
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc')) if f is not None]
    w = SCREEN_WIDTH - SHOW_TEXT_X
    strip = _show_base.crop((SHOW_TEXT_X, SHOW_L2_Y, SCREEN_WIDTH, SHOW_L2_Y + SHOW_L2_H))
    mask = Image.new('L', (w, SHOW_L2_H), 0)
    d = ImageDraw.Draw(mask)
    x, base_y = 0, 1 + CLOCK_FONT.getmetrics()[0]
    for ch in text:
        f = CLOCK_FONT if _has_glyph(CLOCK_FONT, ch) else next(
            (f for f in _small_fallbacks if _has_glyph(f, ch)), CLOCK_FONT)
        d.text((x, base_y), ch, font=f, fill=255, anchor='ls')
        x += f.getlength(ch)
        if x > w:
            break
    if x > w - SHOW_PAD:
        mask = _fade_mask_right(mask)
    strip.paste(SHOW_SUB, (0, 0, w, SHOW_L2_H), mask)
    return strip

def _render_ap_vol(v):
    """Volume wedge beside the AirPlay tile, in place of the title/artist."""
    x0, y0 = SHOW_TEXT_X, SHOW_L1_Y
    region = _show_base.crop((x0, y0, SCREEN_WIDTH, SHOW_L2_Y + SHOW_L2_H))
    d = ImageDraw.Draw(region)
    cells = max(1, MAX_VOL // volume_step)
    lit = round(v / volume_step)
    gap = 3
    cw = (SCREEN_WIDTH - x0 - SHOW_PAD - (cells - 1) * gap) // cells
    bottom = region.height - 8
    for k in range(cells):
        ch = 5 + round(25 * k / max(1, cells - 1))
        x = k * (cw + gap)
        d.rectangle([x, bottom - ch, x + cw - 1, bottom], fill=WHITE if k < lit else (85, 85, 85))
    return region

def display_airplay():
    global currently_displaying, _show_base, _airplay_t1
    with airplay_lock:
        art, thumb = airplay['art'], airplay['thumb']
        title, artist, sender = airplay['title'], airplay['artist'], airplay['sender']
    _show_base = _compose_airplay_base(art, thumb)
    _airplay_t1 = title or 'AirPlay'
    t2 = artist or (f'from {sender}' if sender and not title else '')
    image = _show_base.copy()
    if airplay_vol_until:
        image.paste(_render_ap_vol(airplay_volume or 0), (SHOW_TEXT_X, SHOW_L1_Y))
    else:
        image.paste(_render_show_l1(_airplay_t1), (SHOW_TEXT_X, SHOW_L1_Y))
        image.paste(_render_ap_l2(t2), (SHOW_TEXT_X, SHOW_L2_Y))
    currently_displaying = 'airplay'
    airplay_mq['cycle_start'] = None
    safe_display(image)

def _push_window(img, x, y):
    if not display_lock.acquire(blocking=False):
        return
    try:
        if currently_displaying == 'airplay':
            disp.ShowWindow(img, x, y)
    finally:
        display_lock.release()

def airplay_volume_step(direction):
    global airplay_volume, airplay_vol_until, last_input_time
    if airplay_volume is None:
        airplay_volume = current_volume
    airplay_volume = min(MAX_VOL, max(0, airplay_volume + direction * volume_step))
    _set_airplay_volume(airplay_volume)
    airplay_vol_until = time.monotonic() + 3
    last_input_time = time.monotonic()
    if _show_base is not None:
        _push_window(_render_ap_vol(airplay_volume), SHOW_TEXT_X, SHOW_L1_Y)

def airplay_drop():
    """The listener picked the radio: end the AirPlay session (the phone just
    sees the speaker disconnect). Returns True if a session was playing."""
    with airplay_lock:
        if not airplay['active']:
            return False
        airplay['active'] = False
    logging.info('AIRPLAY DROPPED for the radio')
    _bg(['systemctl', 'restart', 'shairport-sync'])
    return True

def _airplay_enter():
    global currently_displaying, last_input_time, seek_overlay_name, readied_stream
    logging.info('AIRPLAY START')
    send_mpv_command({"command": ["stop"]})
    tuning['state'] = None
    seek_overlay_name = None
    readied_stream = None
    last_input_time = time.monotonic()
    _set_airplay_volume(airplay_volume if airplay_volume is not None else current_volume)
    currently_displaying = 'airplay'
    if not screen_on:
        wake_screen()                         # redraws through display_current
    else:
        display_airplay()

def _airplay_resume_radio():
    logging.info('AIRPLAY END -> radio')
    with state_lock:
        target = stream if stream in streams else (stream_list[0] if stream_list else None)
    if target is None:
        return
    display_cached_scroll(target)
    if not put_to_sleep:
        play(target)

def airplay_tick(now):
    """Called every main-loop pass. Returns None when AirPlay isn't involved,
    else how long the main loop should sleep."""
    global airplay_vol_until
    with airplay_lock:
        active, dirty = airplay['active'], airplay['dirty']
        airplay['dirty'] = False
    showing = currently_displaying == 'airplay'
    if active and not showing:
        _airplay_enter()
        return 0.15
    if not active and not showing:
        return None
    # Not active but still showing: the phone paused or disconnected. Leave the
    # last track on screen and the radio silent until someone touches a knob
    # (handle_rotation / play() bring the radio back).
    if not screen_on or sleeping or freeze_for_task:
        return 0.15
    if airplay_vol_until and now > airplay_vol_until:
        airplay_vol_until = 0.0
        cfg = get_config()
        cfg['airplay_volume'] = airplay_volume
        set_config(cfg)
        dirty = True
    if dirty:
        display_airplay()
        return 0.05
    if airplay_vol_until:
        return 0.1
    w = text_width(_airplay_t1)
    if w > SCREEN_WIDTH - SHOW_TEXT_X - SHOW_PAD:
        _, off = _joint_offsets(0, w + MARQUEE_GAP, False, True, now, airplay_mq)
        _push_window(_render_show_l1(_airplay_t1, off), SHOW_TEXT_X, SHOW_L1_Y)
        return 0.02
    return 0.15


def display_current():

    if currently_displaying == 'everything':
        display_cached_scroll(stream)

    elif currently_displaying == 'one':
        display_cached_scroll(stream)

    elif currently_displaying == 'ambient':
        display_ambient(stream)

    elif currently_displaying == 'airplay':
        display_airplay()


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

def toggle_stream(name):
    global play_status
    if name:
        if play_status == 'play':
            pause(show_icon=True)
        else:
            play(name, toggled=True)

freeze_for_task = False
# ---- seek overlay: alphabet dial + a direction arrow, only while scrolling ----
SEEK_OVERLAY_SECS = 1.5
seek_overlay_until = 0
seek_overlay_name = None
_dial_strip = Image.new('RGB', (SCREEN_WIDTH, VOL_STRIP_BOTTOM - VOL_STRIP_TOP), BLACK)
ARROW_W, ARROW_H = 7, 24                      # small, thin, shallow chevron
ARROW_CY = og_logo_position[1] + TILE // 2
LEFT_ARROW_X = og_logo_position[0] - 15       # over the neighbour, just outside the active tile
RIGHT_ARROW_X = og_logo_position[0] + TILE + 8

def _render_dial_strip(name):
    if tick_image is None or not dial_slots:
        calculate_ticks()
    d = ImageDraw.Draw(_dial_strip)
    d.rectangle([0, 0, SCREEN_WIDTH, _dial_strip.height], fill=BG_COLOR)
    layer = tick_image.crop((0, VOL_STRIP_TOP, SCREEN_WIDTH, VOL_STRIP_BOTTOM))
    _dial_strip.paste(layer, (0, 0), layer)
    draw_tick(d, name, origin_y=VOL_STRIP_TOP)
    return _dial_strip

def _arrow_box(direction):
    x = RIGHT_ARROW_X if direction > 0 else LEFT_ARROW_X
    return (x - 4, ARROW_CY - ARROW_H // 2 - 4, x + ARROW_W + 4, ARROW_CY + ARROW_H // 2 + 5)

def _render_arrow(base, direction):
    box = _arrow_box(direction)
    tile = base.crop(box).convert('RGB')
    d = ImageDraw.Draw(tile)
    x0, cy, half = 4, ARROW_CY - box[1], ARROW_H // 2
    if direction > 0:
        pts = [(x0, cy - half), (x0 + ARROW_W, cy), (x0, cy + half)]
    else:
        pts = [(x0 + ARROW_W, cy - half), (x0, cy), (x0 + ARROW_W, cy + half)]
    d.line(pts, fill=BG_COLOR, width=6, joint='curve')         # halo so it reads over any logo
    d.line(pts, fill=SECONDARY_COLOR, width=2, joint='curve')
    return tile, box

def clear_seek_overlay():
    """Knob has rested: switch from the carousel to the settled screen."""
    global seek_overlay_name
    name, seek_overlay_name = seek_overlay_name, None
    if not name or currently_displaying != 'everything':
        return
    if (readied_stream if readied_stream else stream) != name:
        return
    display_cached_scroll(name)
    if volume_overlay_showing:
        render_frame(name, 0, volume=current_volume, draw_oneliner=False, must_show=True)

def seek_stream(direction):
    global readied_stream, seek_overlay_until, seek_overlay_name
    if freeze_for_task:
        return
    with state_lock:
        sl = stream_list
        cur = readied_stream if readied_stream else stream
        idx = sl.index(cur)
        if currently_displaying == 'ambient':
            readied_stream = cur
        else: 
            readied_stream = sl[(idx + direction) % len(sl)]
    arrow_dir = direction if currently_displaying == 'everything' else 0
    display_cached_scroll(readied_stream, seek_direction=arrow_dir)
    seek_overlay_until = time.monotonic() + SEEK_OVERLAY_SECS
    seek_overlay_name = readied_stream
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
    last_input_time = time.monotonic()

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
    last_volume_change = time.monotonic()

def safe_restart():
    global restarting
    print("RESTARTING")
    if put_to_sleep:
        print("NOW")
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


def on_volume_button_pressed():
    global button_press_time, rotated, button_press_times, held, button_released_time, last_input_time, currently_displaying, readied_stream
    held = True
    if not put_to_sleep:
        last_input_time = time.monotonic()
        button_press_time = time.monotonic()
        button_released_time = None
        toggle_favorite()
        rotated = False
    

def on_volume_button_released():
    global button_press_times, rotated, held, button_released_time, last_input_time, current_volume, screen_on, sleeping, put_to_sleep, muted, volume_held
    held = False


def switch_off():
    global button_press_times, rotated, held, button_released_time, last_input_time, current_volume, screen_on, sleeping, put_to_sleep, switch_off_time, currently_displaying
    current_time = time.monotonic()
    last_input_time = current_time
    button_released_time = current_time
    switch_off_time = current_time
    backlight_off()
    send_mpv_command({"command": ["set_property", "volume", 0]})
    set_last_volume(str(current_volume))
    sleeping = True
    put_to_sleep = True
    # off means off: stop AirPlay too, so Otis also leaves the phone's AirPlay list
    with airplay_lock:
        was_airplay = airplay['active']
        airplay['active'] = False
    _bg(['systemctl', 'stop', 'shairport-sync'])
    if was_airplay or currently_displaying == 'airplay':
        currently_displaying = 'everything'     # switching back on shows the radio

def switch_on():
    global button_press_times, rotated, held, button_released_time, last_input_time, current_volume, screen_on, sleeping, put_to_sleep

    if held:
        safe_restart()
    else:
        current_time = time.monotonic()
        last_input_time = time.monotonic()
        button_released_time = current_time
        _bg(['systemctl', 'start', 'shairport-sync'])
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

def start_priority_refresh(refresh_list=None, center=None, run_ticks=False):
    """Refresh scroll cache for refresh_list (default: all), nearest-first, async."""
    global refresh_generation
    with state_lock:
        refresh_generation += 1
        gen = refresh_generation
        sl = list(stream_list)
    if not sl:
        return
    if center is None:
        center = readied_stream if readied_stream else stream
    if center not in sl:
        center = sl[0]
    # default to full list
    targets = set(refresh_list) if refresh_list is not None else set(sl)
    # proximity order over the whole list, then keep only targets
    ordered = [n for n in proximity_order(sl, center) if n in targets]
    if run_ticks:
        calculate_ticks()
    threading.Thread(target=_refresh_worker, args=(ordered, gen), daemon=True).start()

def _refresh_worker(ordered, gen):
    global refreshing_everything_now
    refreshing_everything_now = True
    try:
        for name in ordered:
            if gen != refresh_generation:
                return
            # yield to the animation: wait while a marquee is running
            while marquee_name is not None and gen == refresh_generation:
                time.sleep(0.05)
            one_cache.pop(name, None)
            img = display_scroll(name, silent=True)
            if gen != refresh_generation:
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
        display_cached_scroll(chosen_stream)  
        start_priority_refresh(chosen_stream)   
        last_input_time = time.monotonic()
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
    if currently_displaying == 'airplay' or airplay['active']:
        last_input_time = time.monotonic()
        airplay_drop()
        _airplay_resume_radio()             # first click just brings the radio back
        return
    seeking = True
    now = time.monotonic()
    last_input_time = now
    rotated = True
    last_rotation = now
    last_seek_rotation = now
    volume_overlay_showing = False
    marquee_name = None
    marquee_offset = 0
    seek_stream(direction)


def volume_handle_rotation(direction):
    global rotated, last_rotation, last_input_time, current_volume
    if currently_displaying == 'airplay':
        airplay_volume_step(direction)
        return
    rotated = True
    last_input_time = time.monotonic()
    last_rotation = time.monotonic()
    if direction == 1:
        new_volume = min(MAX_VOL, current_volume + volume_step)
    else:
        new_volume = max(0, current_volume - volume_step)
    current_volume = new_volume
    send_mpv_command({"command": ["set_property", "volume", current_volume]})
    show_volume_overlay(new_volume)
    active = readied_stream if readied_stream else stream
    if active in scroll_cache_dict and currently_displaying == 'everything':
        render_frame(active, 0, volume=new_volume, draw_oneliner=False, must_show=True)


def compose_frame(name, seek_direction=None):
    """Cached screen + live bottom row (clock, or dial and arrow while seeking),
    composed in memory so the panel gets a single write -- no flash."""
    base = scroll_cache_dict.get(name)
    if base is None:
        base = display_scroll(name, silent=True)
        if base is None:
            return None
        scroll_cache_dict[name] = base
    frame = base.copy()
    if seek_direction is None:
        # settled: only the active logo, pushed left, with the time panel beside it
        d = ImageDraw.Draw(frame)
        d.rectangle([0, 0, SCREEN_WIDTH, PANEL_BOTTOM], fill=BG_COLOR)
        draw_tile(frame, d, name, SETTLED_LOGO_POS, star_96, dim=False)
        _draw_panel(d, name)
        frame.paste(render_status_strip(name), (0, VOL_STRIP_TOP))
    else:
        frame.paste(_render_dial_strip(name), (0, VOL_STRIP_TOP))
        if seek_direction:
            arrow, box = _render_arrow(base, seek_direction)
            frame.paste(arrow, box[:2])
    return frame

def display_cached_scroll(name, pushed=False, seek_direction=None):
    ''' Shows the cached screen (building it if needed) in one write '''
    global currently_displaying, text_on_screen
    currently_displaying = 'everything'
    frame = compose_frame(name, seek_direction)
    if frame is None:
        return
    if pushed:
        draw = ImageDraw.Draw(frame)
        p = SETTLED_LOGO_POS if seek_direction is None else og_logo_position
        draw.rectangle([p[0], p[1], p[0] + TILE, p[1] + TILE], outline=BG_COLOR, width=2)
    with display_lock:
        disp.ShowImage(frame)
    text_on_screen = _ol_text(streams[name])
    

def periodic_update():
    global screen_on, failed_fetches, time_since_last_update, last_successful_fetch, streams, stream_list, scroll_cache_dict, sleeping
    while True:

        time_since_last_success = time.monotonic() - last_successful_fetch
        if sleeping:
            should_fetch = not refreshing_everything_now and ((time_since_last_update >= 120) or (time_since_last_success > 120) or len(scroll_cache_dict)==0)
        else:
            should_fetch = not seeking and \
                        not refreshing_everything_now and \
                            ((((oneliner_mq['offset'] == 0) | (name_mq['offset'] == 0)) and (oneliner_mq['needed']==True and name_mq['needed']==True)) or (((oneliner_mq['offset'] == 0) and (name_mq['offset'] == 0))) or (((oneliner_mq['needed'] == False) and (name_mq['needed'] == False)))) and \
                        ((time_since_last_update >= 30) or (time_since_last_success > 30) or len(scroll_cache_dict)==0)
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
                streams = fetched_streams
                stream_list = get_stream_list(streams)
                if stream:
                    ensure_show_art(stream)          # the show may have changed
                start_priority_refresh(updated_streams, run_ticks=True)
                failed_fetches = 0
                last_successful_fetch = time.monotonic()
                    
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
    global screen_on, last_input_time, current_image, sleeping
    last_input_time = time.monotonic()
    if (not screen_on):
        screen_on = True
        if not put_to_sleep:
            sleeping = False

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

mpv_process = None
stream = None
readied_stream = None
last_rotation = None
last_seek_rotation = None
screen_on = True
saved_image_while_paused = None
play_status = 'pause'
last_input_time = time.monotonic()
first_display = True
volume_step = 10                # 15 clicks from 0 to MAX_VOL; one wedge cell per click
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
last_ambient_display = time.monotonic()
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
    f"--volume-max={MAX_VOL}",
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

star_60 = Image.open('assets/star_60.png').convert('RGBA')
star_96 = Image.open('assets/star_96.png').convert('RGBA')
star_25 = Image.open('assets/star_25.png').convert('RGBA')

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

button_released_time = time.monotonic()
currently_displaying = 'scud'
button_press_times = []

failed_fetches = 0
time_since_last_update = 0

one_cache = {}
scroll_cache_dict = {}

streams = get_streams()
last_successful_fetch = time.monotonic()
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
            vol = max(0, min(MAX_VOL, vol))
            current_volume = vol
            send_mpv_command({"command": ["set_property", "volume", current_volume]})
            show_volume_overlay(current_volume)
            set_last_volume(str(current_volume))
            return {'status': 'ok', 'volume': current_volume}
        
        elif cmd == 'play':
            station_name = command_data.get('value')
            if station_name in stream_list:
                play(station_name)
                display_cached_scroll(station_name)
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
                'volume': round(current_volume*100/MAX_VOL),
                'battery': battery,
                'charging': charging
            }
        
        elif cmd == 'status':
            return {
                'status': 'ok',
                'station': stream,
                'now_playing': streams[stream]['oneLiner'],
                'volume': round(current_volume*100/MAX_VOL),
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
                last_input_time = time.monotonic()
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

click_button = Button(26, bounce_time=0.1, pull_up=True)
click_button.when_pressed = wrapped_action(lambda: play_random())

CLK_PIN = 5 
DT_PIN = 6   
rotor = RotaryEncoder(CLK_PIN, DT_PIN, bounce_time=0.05)
rotor.when_rotated_counter_clockwise = wrapped_action(lambda: handle_rotation(-1), -1)
rotor.when_rotated_clockwise = wrapped_action(lambda: handle_rotation(1), 1)

CLK_PIN = 16
DT_PIN = 12  
volume_rotor = RotaryEncoder(CLK_PIN, DT_PIN, bounce_time=0.05)
volume_rotor.when_rotated_counter_clockwise = wrapped_action(lambda: volume_handle_rotation(-1), -1, True)
volume_rotor.when_rotated_clockwise = wrapped_action(lambda: volume_handle_rotation(1), 1, True)

volume_click_button = Button(17, bounce_time=0.1, pull_up=True)
volume_click_button.when_pressed = on_volume_button_pressed
volume_click_button.when_released = on_volume_button_released

threading.Thread(target=_airplay_reader, daemon=True).start()
threading.Thread(target=_airplay_init_volume, daemon=True).start()

## main loop
print('BEGIN REFRESH', time.monotonic())
calculate_ticks()
scroll_cache_dict[stream] = display_scroll(stream, silent=True)
start_priority_refresh()
display_cached_scroll(stream)
update_thread = threading.Thread(target=periodic_update, daemon=True)
update_thread.start()
 
print('DISPLAYING', time.monotonic())
display_cached_scroll(stream)
last_input_time = time.monotonic()
 
_last_gate_log = 0.0
_last_clock_minute = None
_last_amb_minute = None
last_tune_check = 0.0
pending_last_played = None
needs_scroll = False
 
try:
    while True:
        # Inner try so one bad frame never takes the display thread down.
        # Without this, a KeyError here leaves mpv playing and the panel
        # frozen on its last good frame -- which looks exactly like a
        # driver bug and isn't one.
        try:
            now = time.monotonic()
 
            if now - last_input_time > 10:
                set_last_volume(str(current_volume))

            ap_wait = airplay_tick(now)
            if ap_wait is not None:              # AirPlay owns the screen: no ambient, no radio drawing
                if screen_on and (now - last_input_time > 600):
                    logging.info('TURNING SCREEN OFF (AirPlay)')
                    sleeping = True
                    screen_on = False
                    backlight_off()
                time.sleep(ap_wait)
                continue
 
            # 'and', not '&' -- bitwise on bools works by accident and
            # doesn't short-circuit
            if (now - last_input_time > 60) and (now - last_ambient_display > 30):
                if currently_displaying != 'ambient' or ambient_name != stream:
                    display_ambient(stream)
                last_ambient_display = now
 
            if screen_on and (now - last_input_time > 600):
                logging.info('TURNING SCREEN OFF VIA MAIN LOOP')
                sleeping = True
                screen_on = False
                backlight_off()
 
            active_name = readied_stream if readied_stream else stream
 
            # Snapshot both dicts ONCE. periodic_update rebinds `streams`
            # wholesale and toggle_favorite calls scroll_cache_dict.clear();
            # either can land between a membership test and a lookup.
            info = streams.get(active_name) if active_name else None
            base_img = scroll_cache_dict.get(active_name) if active_name else None
 
            seeking = bool(last_seek_rotation and (now - last_seek_rotation < 1))
 
            # ---- expire the volume overlay after 3s of no volume rotation ----
            if volume_overlay_showing and (now - last_volume_change) > 3:
                volume_overlay_showing = False
                if base_img is not None and currently_displaying == 'everything':
                    push_status_strip(active_name)
 
            on_everything = bool(
                screen_on
                and not sleeping
                and not freeze_for_task
                and not seeking
                and currently_displaying == 'everything'
                and active_name
                and info is not None
                and base_img is not None
            )

            on_ambient = bool(
                screen_on
                and not sleeping
                and not freeze_for_task
                and not seeking
                and currently_displaying == 'ambient'
                and ambient_name
                and streams.get(ambient_name) is not None
            )
 
            # Heartbeat. If this stops appearing the loop is dead; if it
            # keeps appearing, one of these fields explains the freeze.
            if now - _last_gate_log > 2:
                logging.info(
                    'GATE on_everything=%s on_ambient=%s screen_on=%s sleeping=%s freeze=%s '
                    'seeking=%s displaying=%s active=%s info=%s cached=%s '
                    'marquee=%s',
                    on_everything, screen_on, sleeping, freeze_for_task,
                    seeking, currently_displaying, active_name,
                    info is not None, base_img is not None, marquee_name)
                _last_gate_log = now
 
            needs_scroll = False
 
            if pending_last_played and now - last_input_time > 3:
                set_last_played(pending_last_played)
                pending_last_played = None

            if seek_overlay_name and now > seek_overlay_until:
                clear_seek_overlay()

            minute = int(time.time() // 60)        # wall clock: station clocks tick on the real minute
            if on_everything and minute != _last_clock_minute and not volume_overlay_showing and not seek_overlay_name:
                _last_clock_minute = minute
                push_panel(active_name)

            if tuning['state'] and now - last_tune_check > 0.3:
                last_tune_check = now
                _update_tuning(now, active_name,
                               on_everything and not volume_overlay_showing and not seek_overlay_name)

            if on_everything:
                text = _ol_text(info)
                text_w = text_width(text)
                long_oneliner = text_w > (SCREEN_WIDTH - MARQUEE_X)
 
                _, name_w = _name_metrics(active_name)
                long_name = name_w > (SCREEN_WIDTH - MARQUEE_X)
 
                needs_scroll = long_oneliner or long_name
                text_span = text_w + MARQUEE_GAP
                name_span = name_w + MARQUEE_GAP
 
                name_mq['needed'] = long_name
                oneliner_mq['needed'] = long_oneliner
 
                if text_on_screen != text:
                    logging.info('TEXT CHANGED -> %r', text[:60])
                    # Claim the new text FIRST and unconditionally. The old
                    # code only updated it via display_cached_scroll(), which
                    # sat behind `if not long_oneliner` -- so for long text
                    # it never updated, text_changed stayed True forever, and
                    # marquee_name was reset to None on every single pass.
                    text_on_screen = text
                    _mq_reset(oneliner_mq, now)
                    marquee_name = None
                    if not long_oneliner:
                        # pop, not del: toggle_favorite may have cleared it
                        scroll_cache_dict.pop(active_name, None)
                        display_cached_scroll(active_name)
 
                if needs_scroll:
                    if marquee_name != active_name:
                        logging.info('MARQUEE START %s (name=%s ol=%s)',
                                     active_name, long_name, long_oneliner)
                        marquee_name = active_name
                        name_mq['cycle_start'] = None   # reset shared clock
 
                    name_off, ol_off = _joint_offsets(
                        name_span, text_span, long_name, long_oneliner,
                        now, name_mq)
 
                    # Write the offsets back. periodic_update gates fetches
                    # on these being 0; _joint_offsets never set them, so
                    # that guard has been inert and fetches landed mid-scroll.
                    name_mq['offset'] = name_off or 0
                    oneliner_mq['offset'] = ol_off or 0
 
                    render_frame(active_name,
                                 ol_off if long_oneliner else 0,
                                 draw_oneliner=long_oneliner,
                                 name_offset=name_off)
                else:
                    marquee_name = None
                    name_mq['offset'] = 0
                    oneliner_mq['offset'] = 0
            elif on_ambient:
                amb_info = streams.get(ambient_name)
                if amb_info is not None and SHOW_ART_ON:
                    # swap between show art and the classic screen as shows change
                    want = amb_info.get('showLogo')
                    have = want if (want and want in show_art_cache) else None
                    if want and not have:
                        ensure_show_art(ambient_name)
                    if have != ambient_art_url:
                        display_ambient(ambient_name)
                amb_text = _ol_text(amb_info) if amb_info else ''
                amb_w = text_width(amb_text)
                amb_long = amb_w > _amb_avail_w()
                needs_scroll = amb_long
 
                if ambient_text_on_screen != amb_text:
                    logging.info('AMBIENT TEXT CHANGED -> %r', amb_text[:60])
                    ambient_text_on_screen = amb_text
                    ambient_mq['cycle_start'] = None
                    if not amb_long:
                        # short text: one static redraw, no cycle needed
                        render_ambient_frame(amb_text, None)
 
                if minute != _last_amb_minute:
                    _last_amb_minute = minute            # keep the station clock current
                    if ambient_show:
                        push_show_l2(ambient_name)
                    elif not amb_long:
                        render_ambient_frame(amb_text, None)

                if amb_long:
                    # one track only, so declare the name track not-long and
                    # let _joint_offsets drive the one-liner track alone
                    _, amb_off = _joint_offsets(
                        0, amb_w + MARQUEE_GAP, False, True, now, ambient_mq)
                    ambient_mq['offset'] = amb_off or 0
                    render_ambient_frame(amb_text, amb_off)
 
                marquee_name = None
                name_mq['offset'] = 0
                oneliner_mq['offset'] = 0
 
            else:
                marquee_name = None
                name_mq['offset'] = 0
                oneliner_mq['offset'] = 0
 
            time.sleep(0.02 if needs_scroll else 0.15)
 
        except Exception:
            logging.error('MAIN LOOP ERROR:\n%s', traceback.format_exc())
            time.sleep(0.5)

except KeyboardInterrupt:
    if mpv_process:
        mpv_process.terminate()

    WIDTH = disp.width
    HEIGHT = disp.height
    img = Image.new("RGB", (320, 240), color="black")
    draw = ImageDraw.Draw(img)
    disp.ShowImage(img)
