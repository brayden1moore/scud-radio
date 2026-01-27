from flask import Flask, request, render_template, redirect, url_for
from PIL import Image
import driver as LCD_2inch
import subprocess
import socket
import sys
import time
import threading
import logging
import os

# get known networks file
from pathlib import Path
import json
LIB_PATH = "/home/scud/scud-radio"
wifi_path = Path(LIB_PATH)
wifi_path.mkdir(parents=True, exist_ok=True)
wifi_file = wifi_path / 'known_networks.json'
if not wifi_file.exists():
    networks = {}
else:
    with open(wifi_file, 'r') as f:
        networks = json.load(f)

# --- CONFIGURATION ---
BASE_DIR = '/home/scud/scud-radio'
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
# ---------------------

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

disp = None
app = Flask(__name__, static_folder=ASSETS_DIR, template_folder=os.path.join(BASE_DIR, 'templates'))
app.secret_key = 'sticky-lemon'

disp = LCD_2inch.LCD_2inch()
disp.Init()
disp.bl_DutyCycle(100)

def start_radio_service():
    """Stops the launcher and starts the main radio service"""
    logging.info("Starting Radio Service...")
    subprocess.run(['sudo', 'systemctl', 'start', 'radio'])
    sys.exit(0)

def init_display_for_portal():
    
    image = Image.new('RGB', (320, 240))
    bg = Image.open(os.path.join(ASSETS_DIR, 'hello.png')) 
    image.paste(bg, (0, 0))
    disp.ShowImage(image)

def display_status(status_type):
    if not disp: return
    image = Image.new('RGB', (320, 240))
    filename = "success.png" if status_type == "success" else "failure.png"
    bg = Image.open(os.path.join(ASSETS_DIR, filename))
    image.paste(bg, (0, 0))
    disp.ShowImage(image)

def check_wifi_loop():
    while True:
        time.sleep(5)
        if currently_connected():
            display_status('success')
            time.sleep(2)
            start_radio_service()

def scan_wifi():
    options = []
    try:
        subprocess.run(["sudo", "nmcli", "dev", "wifi", "rescan"])
        result = subprocess.run(["nmcli", "--fields", "SSID", "device", "wifi", "list"],
                                stdout=subprocess.PIPE, text=True)
        for line in result.stdout.strip().split('\n')[1:]:
            ssid = line.strip()
            if ssid != '--' and ssid not in options:
                options.append(ssid)
    except Exception as e:
        logging.error(f"Scan failed: {e}")
    return options

@app.route('/')
def index():
    return render_template('index.html', wifi_networks=scan_wifi(), message="", known_networks=networks)

@app.route('/submit', methods=['POST'])
def submit():
    ssid = request.form.get('ssid')
    password = request.form.get('password')
    
    try:
        connect_to_wifi(ssid, password)
        if currently_connected():
            display_status('success')
            time.sleep(2)
            start_radio_service()
        else:
            raise Exception("Connected but no internet")
    except:
        return redirect(url_for('index', message="Connection failed. Try again."))

# --- MAIN ENTRY POINT ---
internet_found = False

def display_splash():
    SCREEN_WIDTH = 320
    SCREEN_HEIGHT = 240
    image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))
    bg = Image.open('assets/wifi_splash.png')
    image.paste(bg, (0, 0))
    disp.ShowImage(image)

def currently_connected():
    """Check if WiFi is connected AND has internet access"""
    
    # First check WiFi status
    status = subprocess.run(["nmcli", "dev", "status"],
                           stdout=subprocess.PIPE, text=True)
    statuses = status.stdout.strip().split('\n')
    wifi_connected = False
    
    for i in statuses:
        if 'wlan0' in i:
            wlan_status = i.split()
            if len(wlan_status) > 0 and wlan_status[0] == 'wlan0':
                if 'connected' in wlan_status:
                    wifi_connected = True
                    break
    
    if not wifi_connected:
        logging.info('WiFi not connected')
        return False
    
    # WiFi connected - now verify internet connectivity
    try:
        result = subprocess.run(
            ["nmcli", "networking", "connectivity", "check"],
            stdout=subprocess.PIPE,
            text=True,
            timeout=5
        )
        connectivity = result.stdout.strip()
        
        if connectivity == 'full':
            logging.info('WiFi connected with full internet access')
            return True
        else:
            logging.info(f'WiFi connected but connectivity is: {connectivity}')
            return False
    except Exception as e:
        logging.error(f'Connectivity check failed: {e}')
        return False

def connect_to_wifi(ssid, password):
    result = subprocess.run(['sudo', 'nmcli', 'dev', 'wifi', 'connect', ssid, 'password', password],
                           capture_output=True, text=True)
    return result.returncode == 0

if __name__ == '__main__':
    display_splash()
    logging.info("Starting launcher.")

    # 1. Check if already connected (with retries for network to stabilize)
    max_checks = 6  # 6 checks * 2 seconds = 12 seconds max wait
    for attempt in range(max_checks):
        internet_found = currently_connected()
        if internet_found:
            logging.info(f"Connected after {attempt * 2}s, starting radio service")
            start_radio_service()
            sys.exit(0)
        if attempt < max_checks - 1:
            logging.info(f"No connection yet, waiting... (attempt {attempt + 1}/{max_checks})")
            time.sleep(2)
    
    logging.info("No existing connection found after checks")
    
    # 2. Try known networks
    if networks:
        for ssid, password in networks.items():
            logging.info(f"Trying known network: {ssid}")
            if connect_to_wifi(ssid, password):
                # Wait for connection to fully establish
                for attempt in range(5):
                    time.sleep(2)
                    if currently_connected():
                        logging.info(f"Connected to {ssid}, starting radio service")
                        start_radio_service()
                        sys.exit(0)
            logging.info(f"Failed to connect to {ssid}")

    # 3. No internet, start Portal Mode - this runs forever
    logging.info("No connection available. Starting Portal Mode.")
    init_display_for_portal()
    subprocess.run(['sudo', 'nmcli', 'device', 'wifi', 'hotspot', 'ifname', 'wlan0', 'ssid', 'One-Radio', 'password', ''])
    
    t = threading.Thread(target=check_wifi_loop, daemon=True)
    t.start()
    
    app.run(host='0.0.0.0', port=8888, use_reloader=False)