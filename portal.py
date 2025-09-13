from flask import Flask,request, render_template, session, redirect, url_for, jsonify
from PIL import Image, ImageDraw, ImageFont, ImageSequence
from gpiozero import Device
import driver as LCD_2inch
import subprocess
import socket
import sys
import time
import threading
import logging
import os

from pathlob import Path

STATE_FILE = Path("/var/lib/scud-radio/first_boot.flag")

def is_first_boot():
    return STATE_FILE.exists()

def clear_first_boot():
    STATE_FILE.unlink(missing_ok=True)

def set_first_boot():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.touch()

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

def display_setup():
    image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))
    bg = Image.open(f'assets/hello.png')
    image.paste(bg, (0, 0))
    disp.ShowImage(image)

def display_splash():
    image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))

    # splash one
    bg = Image.open(f'assets/scud_splash_1.png')
    image.paste(bg, (0, 0))
    disp.ShowImage(image)
    time.sleep(2)

    # splash two
    bg = Image.open(f'assets/scud_splash_2.png')
    image.paste(bg, (0, 0))
    disp.ShowImage(image)
    time.sleep(2)

def display_result(type):
    image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))
    bg = Image.open(f'assets/{"success" if type=="success" else "failure"}.png') 
    image.paste(bg, (0, 0))
    disp.ShowImage(image)

app = Flask(__name__,
            static_folder='assets',
            template_folder='templates'
            )
app.secret_key = 'sticky-lemon'

def start_hotspot():
    subprocess.run(['sudo', 'nmcli','device', 'wifi', 'hotspot', 'ssid', 'Scud Radio', 'password', 'scudhouse'])

def wait_for_wifi_interface(timeout=30):
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

def internet(host="8.8.8.8", port=53, timeout=4, retries=3):
    for attempt in range(retries):
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except socket.error as ex:
            logging.info(f"Internet check attempt {attempt + 1} failed: {ex}")
            if attempt < retries - 1:
                time.sleep(2) 
    return False

def display_wifi_waiting():
    """Display WiFi waiting animation in sequence"""
    wifi_images = ['scud_wifi_3.png', 'scud_wifi_2.png', 'scud_wifi_1.png']
    
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

def scan_wifi():
    options = []
    result = subprocess.run(["nmcli", "--fields", "SSID", "device", "wifi", "list"],
                                    stdout=subprocess.PIPE,
                                    text=True, check=True)
    scanoutput = result.stdout.strip()
    for line in scanoutput.split('\n')[1:]:
        ssid = line.strip()
        if ssid != '--':
            options.append(ssid)
    return options

@app.route('/')
def index():
    wifi_networks = scan_wifi()
    return render_template('index.html', wifi_networks=wifi_networks, message="")

@app.route('/submit', methods=['POST','GET'])
def submit():
    global disp
    if request.method == 'POST':
        try:
            ssid = request.form['ssid']
            password = request.form['password']
            
            result = subprocess.run(['nmcli', 'dev', 'wifi', 'connect', ssid, 'password', password],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, check=True)
            
            assert internet()
            display_result('success')
            time.sleep(3)
            disp.clear()
            disp.reset()
            disp.close()
            logging.info('Killing self')
            result = subprocess.run(['sudo','netstat','-tulnp','|','grep','8888'],stdout=subprocess.PIPE,
                                    text=True, check=True)
            id = result.stdout.strip().split('\t')[-1].replace('/python3','').strip()
            logging.info(id)
            subprocess.run(['sudo','kill',id])
            
            clear_first_boot()
            subprocess.run(['sudo','systemctl','restart','radio'])
            sys.exit(0)
        except:
            return redirect(url_for('index', wifi_networks=scan_wifi(), message="That didn't work. Try again?"))

    else:
        return redirect(url_for('index', wifi_networks=scan_wifi(), message=""))

if is_first_boot:
    display_splash()

    wifi_waiting = True
    wifi_thread = threading.Thread(target=display_wifi_waiting, daemon=True)
    wifi_thread.start()
    
    if not wait_for_wifi_interface():
        wifi_waiting = False
        logging.error("WiFi interface not available")
        sys.exit(1)
    
    connected = internet(retries=5)

    if not connected:
        display_setup()
        start_hotspot()
        app.run(host='0.0.0.0', port=8888, use_reloader=False)
    else:
        clear_first_boot()
        subprocess.run(['sudo','systemctl','restart','radio'])
        sys.exit(0)