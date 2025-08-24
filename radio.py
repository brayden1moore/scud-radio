from PIL import Image, ImageDraw, ImageFont, ImageSequence
from subprocess import Popen, run
import subprocess
import requests
from datetime import date, datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import signal
from io import BytesIO
import threading
import random
import platform
import math
import os

import driver as LCD_2inch
import spidev as SPI

## scud

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

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240
FONT_SIZE = 6

WHITE = (255,255,255)
BLACK = (0,0,0)
YELLOW = (255,255,0)
GREY = (100,100,100)

BORDER_COLOR = BLACK
TEXT_COLOR = BLACK
TEXT_COLOR_2 = BLACK
BACKGROUND_COLORS = []
BACKGROUND_COLOR = WHITE
SLIDER_BG = WHITE
SLIDER_COLOR = BLACK
BORDER_SIZE = 2

LOGO_SIZE = 120
LOGO_Y = 25
LOGO_X = round(SCREEN_WIDTH/2) - round(LOGO_SIZE/2)

READIED_LOGO_SIZE = 90
READIED_LOGO_Y = LOGO_Y + round((LOGO_SIZE-READIED_LOGO_SIZE) / 2)
READIED_LOGO_X = round(SCREEN_WIDTH/2) - round(READIED_LOGO_SIZE/2)

SMALL_LOGO_SIZE = 60
SMALL_LOGO_Y = LOGO_Y + round(LOGO_SIZE/2) - round(SMALL_LOGO_SIZE/2)
PREV_LOGO_X = LOGO_X - round(SMALL_LOGO_SIZE) + 15 - BORDER_SIZE
NEXT_LOGO_X = LOGO_X + LOGO_SIZE - 15 + BORDER_SIZE

SMALLEST_LOGO_SIZE = 50

TITLE_Y = LOGO_SIZE + LOGO_Y + 10
SUBTITLE_Y = TITLE_Y + 25
LOCATION_Y = SUBTITLE_Y + 15

STATUS_SIZE = 25
STATUS_LOCATION = (LOGO_X+round(LOGO_SIZE/2)-round(STATUS_SIZE/2), LOGO_Y+round(LOGO_SIZE/2)-round(STATUS_SIZE/2))

SMALL_FONT = ImageFont.truetype("assets/Silkscreen-Regular.ttf", 10)
MEDIUM_FONT = ImageFont.truetype("assets/Silkscreen-Regular.ttf", 20)
LARGE_FONT = ImageFont.truetype("assets/Silkscreen-Regular.ttf",28)

SMALL_FONT = ImageFont.truetype("assets/Arial Black.ttf", 10)
MEDIUM_FONT = ImageFont.truetype("assets/andalemono.ttf", 20)
LARGE_FONT = ImageFont.truetype("assets/Arial Black.ttf",28)
BIGGEST_FONT = ImageFont.truetype("assets/Arial Black.ttf",36)

PAUSE_IMAGE = (Image.open('assets/pause.png').convert('RGBA').resize((LOGO_SIZE+BORDER_SIZE*2, LOGO_SIZE+BORDER_SIZE*2)))

ONE_LOGO_X = 15
ONE_LOGO_Y = 18
ONE_NAME_X = 77
ONE_NAME_Y = 12
ONE_LOC_X = ONE_NAME_X
ONE_LOC_Y = ONE_NAME_Y + 31
TOP_DIVIDER_X = 11
TOP_DIVIDER_Y = 80
BOTTOM_DIVIDER_X = TOP_DIVIDER_X
BOTTOM_DIVIDER_Y = 175
SHOW_ROW_1_X = TOP_DIVIDER_X
SHOW_ROW_1_Y = TOP_DIVIDER_Y + 5
BOTTOM_DIVIDER_X = TOP_DIVIDER_X
BOTTOM_DIVIDER_Y = 170
SHOW_INFO_X = TOP_DIVIDER_X
SHOW_INFO_ROW_1_Y = 187

def safe_display(image):
    global current_image
    if screen_on & (image != current_image):
        #disp.display(image)
        disp.ShowImage(image) # for 2 inch
    current_image = image.copy()
    

def display_scud():
    image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))
    rotations = 0
    max_rotations = 2
    while rotations <max_rotations:
        for i in [2,3,4,5,6,7,1]:
             
            bg = Image.open(f'assets/gif/{i}.png') 
            image.paste(bg, (0, 0))
            safe_display(image)  

            if i==1 and rotations==max_rotations-1:
                time.sleep(2)
            else:
                time.sleep(0.02)

        rotations += 1

    bg = Image.open(f'assets/gif/1.png') 
    image.paste(bg, (0, 0))
    safe_display(image)  
            

    '''
    bg = Image.open(f'assets/scudgif/background.png') 
    image.paste(bg, (0, 0))
    draw = ImageDraw.Draw(image)
    safe_display(image)

    img = Image.open(f'assets/scudgif/dancergifgif.gif')

    for frame in ImageSequence.Iterator(img):
        image.paste(img.resize((180,180)), (140, 0))
        draw = ImageDraw.Draw(image)
        safe_display(image)
    '''

def backlight_on():
    if disp:
        if current_image:
            safe_display(current_image)
        else:
            display_scud()
        disp.bl_DutyCycle(MAX_BL)
    #GPIO.output(BACKLIGHT_PIN, GPIO.HIGH)

def backlight_off():
    if disp:
        #display_scud()
        disp.bl_DutyCycle(0)
    #GPIO.output(BACKLIGHT_PIN, GPIO.LOW)

display_scud()


mpv_process = Popen([
    "mpv",
    "--idle=yes",
    "--no-video",
    "--ao=alsa",
    "--audio-device=alsa",
    f"--volume={current_volume}",
    "--volume-max=150",
    "--input-ipc-server=/tmp/mpvsocket"
])

#import st7789
from gpiozero import Button
import socket
import json

def send_mpv_command(cmd):
    with socket.socket(socket.AF_UNIX) as s:
        s.connect("/tmp/mpvsocket")
        s.sendall((json.dumps(cmd) + '\n').encode())

def fetch_logo(name, url):
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    return name, BytesIO(resp.content)

def get_streams():
    global streams

    info = requests.get('https://internetradioprotocol.org/info').json()
    active = {n: v for n, v in info.items() if v['status']=="Online"}
    
    with ThreadPoolExecutor(max_workers=8) as exe:
        futures = [
            exe.submit(fetch_logo, name, v['logo'])
            for name, v in active.items()
        ]
        for f in as_completed(futures):
            name, buf = f.result()
            active[name]['logoBytes'] = buf

            img = Image.open(buf).convert('RGB')
            active[name]['logo_full']  = img.resize((LOGO_SIZE,  LOGO_SIZE))
            active[name]['logo_readied']  = img.resize((READIED_LOGO_SIZE,  READIED_LOGO_SIZE))
            active[name]['logo_small'] = img.resize((SMALL_LOGO_SIZE, SMALL_LOGO_SIZE))
            active[name]['logo_smallest'] = img.resize((SMALLEST_LOGO_SIZE, SMALLEST_LOGO_SIZE))

    return active

streams = get_streams()
stream_list = list(streams.keys())

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

def x(string, font):
    text_width = width(string,font)
    return max((SCREEN_WIDTH - text_width) // 2, 5)

def s(number):
    if number == 1:
        return ''
    else:
        return 's'
    

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

def pause(show_icon=False):
    global play_status, saved_image_while_paused, current_image
    #send_mpv_command({"command": ["stop"]})
    send_mpv_command({"command": ["set_property", "volume", 0]})

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
        stream_url = streams[name]['streamLink']
        send_mpv_command({"command": ["loadfile", stream_url, "replace"]})
        send_mpv_command({"command": ["set_property", "volume", current_volume]})

    write_to_tmp_os_path(name)

def calculate_text(text, font, max_width, lines):
    text = text.strip()

    if width(text, font) <= max_width:
        print("returning just the text")
        return [text]
    
    else:
        current_width = 0
        characters = ''
        line_list = []
        current_line = 1
        dots_width = width('...', font)
        words = text.split(' ')
        for idx, i in enumerate(words):
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

    if readied:
        first_display = False

        prev_stream = stream_list[stream_list.index(name)-1]
        try:
            next_stream = stream_list[stream_list.index(name)+1]
        except:
            next_stream = stream_list[0]

        image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT), color=BACKGROUND_COLOR)
        draw = ImageDraw.Draw(image)

        logo = streams[name]['logo_full']
        readied_logo = streams[name]['logo_readied']
        prev = streams[prev_stream]['logo_small']
        next = streams[next_stream]['logo_small']

        border = Image.new('RGB', (SMALL_LOGO_SIZE+BORDER_SIZE*6, SMALL_LOGO_SIZE+BORDER_SIZE*6), color=BORDER_COLOR)
        border2 = Image.new('RGB', (SMALL_LOGO_SIZE+BORDER_SIZE*4, SMALL_LOGO_SIZE+BORDER_SIZE*4), color=BACKGROUND_COLOR)
        border3 = Image.new('RGB', (SMALL_LOGO_SIZE+BORDER_SIZE*2, SMALL_LOGO_SIZE+BORDER_SIZE*2), color=BORDER_COLOR)

        image.paste(border, (PREV_LOGO_X-BORDER_SIZE*2, SMALL_LOGO_Y-BORDER_SIZE*2))
        image.paste(border2, (PREV_LOGO_X-BORDER_SIZE, SMALL_LOGO_Y-BORDER_SIZE))
        image.paste(border3, (PREV_LOGO_X, SMALL_LOGO_Y))

        image.paste(border, (NEXT_LOGO_X-BORDER_SIZE*2, SMALL_LOGO_Y-BORDER_SIZE*2))    
        image.paste(border2, (NEXT_LOGO_X-BORDER_SIZE, SMALL_LOGO_Y-BORDER_SIZE))
        image.paste(border3, (NEXT_LOGO_X, SMALL_LOGO_Y))

        image.paste(prev, (PREV_LOGO_X+BORDER_SIZE, SMALL_LOGO_Y+BORDER_SIZE))
        image.paste(next, (NEXT_LOGO_X+BORDER_SIZE, SMALL_LOGO_Y+BORDER_SIZE))

        if readied:
            border = Image.new('RGB', (READIED_LOGO_SIZE+BORDER_SIZE*6, READIED_LOGO_SIZE+BORDER_SIZE*6), color=BORDER_COLOR)
            border2 = Image.new('RGB', (READIED_LOGO_SIZE+BORDER_SIZE*4, READIED_LOGO_SIZE+BORDER_SIZE*4), color=BACKGROUND_COLOR)
            border3 = Image.new('RGB', (READIED_LOGO_SIZE+BORDER_SIZE*2, READIED_LOGO_SIZE+BORDER_SIZE*2), color=BORDER_COLOR)
            image.paste(border, (READIED_LOGO_X-BORDER_SIZE*2, READIED_LOGO_Y-BORDER_SIZE*2))
            image.paste(border2, (READIED_LOGO_X-BORDER_SIZE, READIED_LOGO_Y-BORDER_SIZE))
            image.paste(border3, (READIED_LOGO_X, READIED_LOGO_Y))
            image.paste(readied_logo, (READIED_LOGO_X+BORDER_SIZE, READIED_LOGO_Y+BORDER_SIZE))
        else:
            border = Image.new('RGB', (LOGO_SIZE+BORDER_SIZE*6, LOGO_SIZE+BORDER_SIZE*6), color=BORDER_COLOR)
            border2 = Image.new('RGB', (LOGO_SIZE+BORDER_SIZE*4, LOGO_SIZE+BORDER_SIZE*4), color=BACKGROUND_COLOR)
            border3 = Image.new('RGB', (LOGO_SIZE+BORDER_SIZE*2, LOGO_SIZE+BORDER_SIZE*2), color=BORDER_COLOR)
            image.paste(border, (LOGO_X-BORDER_SIZE*2, LOGO_Y-BORDER_SIZE*2))
            image.paste(border2, (LOGO_X-BORDER_SIZE, LOGO_Y-BORDER_SIZE))
            image.paste(border3, (LOGO_X, LOGO_Y))
            image.paste(logo, (LOGO_X+BORDER_SIZE, LOGO_Y+BORDER_SIZE))

        parts = [
            streams[name]['nowPlayingArtist'],
            streams[name]['nowPlayingSubtitle'],
            streams[name]['nowPlayingAdditionalInfo'],
        ]

        title = calculate_text(streams[name]['oneLiner'], LARGE_FONT, 290, 1)[0]
        location = streams[name]['location']

        draw.text((x(title, LARGE_FONT), TITLE_Y), title, font=LARGE_FONT, fill=TEXT_COLOR)
        draw.text((x(f'{name} - {location}', MEDIUM_FONT), LOCATION_Y), f'{name} - {location}', font=MEDIUM_FONT, fill=TEXT_COLOR_2)

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

        safe_display(image) # display 
    
    else:
        display_one(name)

    
def display_one(name):
    image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT), color=BACKGROUND_COLOR)
    draw = ImageDraw.Draw(image)

    # logo
    logo = streams[name]['logo_smallest']
    border = Image.new('RGB', (SMALLEST_LOGO_SIZE+BORDER_SIZE*2, SMALLEST_LOGO_SIZE+BORDER_SIZE*2), color=BORDER_COLOR)
    image.paste(border, (ONE_LOGO_X-BORDER_SIZE*2, ONE_LOGO_Y-BORDER_SIZE*2))
    image.paste(logo, (ONE_LOGO_X-BORDER_SIZE, ONE_LOGO_Y-BORDER_SIZE))

    # name
    draw.text((ONE_NAME_X, ONE_NAME_Y), calculate_text(name, font=LARGE_FONT, max_width=223, lines=1)[0], font=LARGE_FONT, fill=TEXT_COLOR)

    # location
    draw.text((ONE_LOC_X, ONE_LOC_Y), calculate_text(streams[name]['location'], font=MEDIUM_FONT, max_width=223, lines=1)[0], font=MEDIUM_FONT, fill=TEXT_COLOR_2)    

    # top divider
    divider = Image.new('RGB', (290,BORDER_SIZE), color=BORDER_COLOR)
    image.paste(divider, (TOP_DIVIDER_X, TOP_DIVIDER_Y))

    # now playing
    y_offset = 0
    num_title_lines = 2
    info = streams[name]['oneLiner'].split(' - ')
    info = [i for i in info if i in list(set(info))]

    if len(info) == 1:
        num_title_lines = 4

    title_lines = calculate_text(info[0], font=BIGGEST_FONT, max_width=290, lines=num_title_lines)
    for i in title_lines:
        draw.text((SHOW_INFO_X, SHOW_ROW_1_Y + y_offset), i, font=BIGGEST_FONT, fill=TEXT_COLOR)
        y_offset += 32

    # other info
    info_lines = calculate_text(' - '.join(info[1:]), font=MEDIUM_FONT, max_width=290, lines=2)

    if len(info) > 1:
        image.paste(divider, (BOTTOM_DIVIDER_X, y_offset + 5))    

    if info_lines:
        print(info_lines)
        for i in info_lines:
            draw.text((SHOW_INFO_X, y_offset + 5), i, font=MEDIUM_FONT, fill=TEXT_COLOR_2)
            y_offset = 20
        

    safe_display(image)



def toggle_stream(name):
    global play_status
    if name:
        if play_status == 'play':
            pause(show_icon=True)
        else:
            play(name, toggled=True)

    
def play_random():
    global stream, play_status
    pause()
    available_streams = [i for i in stream_list if i != stream]
    chosen = random.choice(available_streams)
    display_everything(chosen)
    play(chosen)
    stream = chosen
    play_status = 'play'


def seek_stream(direction):
    global readied_stream 

    idx = stream_list.index(stream)
    if (readied_stream == None) & (direction==1):
        if idx == len(stream_list)-1:
            readied_stream = stream_list[0]
        else:
            readied_stream = stream_list[stream_list.index(stream)+1]

    elif (readied_stream == None) & (direction==-1):
        if idx == 0:
            readied_stream = stream_list[-1]
        else:
            readied_stream = stream_list[stream_list.index(stream)-1]

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
            pause()
            stream = readied_stream
            play(stream)
        display_everything(stream)
        readied_stream = None

def show_volume_overlay(volume):
    global current_image

    if current_image:
        img = current_image.copy()
        draw = ImageDraw.Draw(img)
        
        bar_width = 320
        bar_height = BORDER_SIZE
        bar_x = 0
        bar_y = 0 
        
        this_border_size = round(BORDER_SIZE/2)
        draw.rectangle([bar_x-this_border_size, bar_y-this_border_size, bar_x+bar_width+this_border_size, bar_y+bar_height+this_border_size], fill=SLIDER_COLOR)
        draw.rectangle([bar_x, bar_y, bar_x+bar_width, bar_y+bar_height], fill=SLIDER_BG)
        
        volume_width = int((volume / 125) * bar_width)
        draw.rectangle([bar_x, bar_y, bar_x+volume_width, bar_y+bar_height], fill=SLIDER_COLOR)
        
        safe_display(img)

def on_button_pressed():
    global button_press_time, rotated
    if readied_stream:
        confirm_seek()
    button_press_time = time.time()
    rotated = False

def on_button_released():
    global button_press_time, rotated
    
    if (time.time() - button_press_time < 0.2) and not rotated:
        if not wake_screen() and readied_stream:
            confirm_seek()


def handle_rotation(direction):
    global rotated, current_volume, button_press_time, last_rotation
    rotated = True

    if click_button.is_pressed:

        if direction == 1: 
            current_volume = min(125, current_volume + volume_step)
        else: 
            current_volume = max(0, current_volume - volume_step)

        send_mpv_command({"command": ["set_property", "volume", current_volume]})
        show_volume_overlay(current_volume)

    else:
        if (time.time() - button_press_time > 1):
            last_rotation = time.time()
            seek_stream(direction)

def shutdown():
    run(['sudo', 'shutdown', 'now'])

def periodic_update():
    global screen_on, last_input_time, streams, stream_list

    if screen_on and (time.time() - last_input_time > 60):
        #screen_on = False
        #backlight_off()
        pass
    else:
        try:
            info = requests.get('https://internetradioprotocol.org/info').json()
            for name, v in info.items():
                if name in streams:
                    streams[name].update(v)
            stream_list = list(streams.keys())

            if play_status != 'pause':
                display_everything(stream, update=True)
                
        except Exception as e:
            print(e)
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

click_button = Button(26)
click_button.when_pressed = on_button_pressed

CLK_PIN = 5 
DT_PIN = 6   
rotor = RotaryEncoder(CLK_PIN, DT_PIN)
rotor.when_rotated_counter_clockwise = wrapped_action(lambda: handle_rotation(-1))
rotor.when_rotated_clockwise = wrapped_action(lambda: handle_rotation(1))

last_played = read_last_played()
if last_played:
    play(last_played)
else:
    play_random()

periodic_update()

try:
    while True:
        if readied_stream and last_rotation and (time.time() - last_rotation > 5):
            readied_stream = None
            if screen_on and stream:
                display_everything(stream)
        time.sleep(0.5)
except KeyboardInterrupt:
    if mpv_process:
        mpv_process.terminate()

    WIDTH = disp.width
    HEIGHT = disp.height
    img = Image.new("RGB", (320, 240), color="black")
    draw = ImageDraw.Draw(img)
    #disp.display(img)
    disp.ShowImage(img) # for 2 inch
