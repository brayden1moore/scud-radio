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

# --- CONFIGURATION ---
BASE_DIR = '/home/scud/scud-radio'
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
# ---------------------

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

disp = None
app = Flask(__name__, static_folder=ASSETS_DIR, template_folder=os.path.join(BASE_DIR, 'templates'))
app.secret_key = 'sticky-lemon'

def start_radio_service():
    """Stops the launcher and starts the main radio service"""
    logging.info("Starting Radio Service...")

    subprocess.run(['sudo', 'systemctl', 'start', 'radio'])
    sys.exit(0)

def init_display_for_portal():
    global disp
    disp = LCD_2inch.LCD_2inch()
    disp.Init()
    disp.bl_DutyCycle(100)
    
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

def internet(host="8.8.8.8", port=53, timeout=3):
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error:
        return False

def check_wifi_loop():
    while True:
        time.sleep(5)
        if internet():
            display_status('success')
            time.sleep(2)
            start_radio_service()

def scan_wifi():
    options = []
    try:
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
    return render_template('index.html', wifi_networks=scan_wifi(), message="")

@app.route('/submit', methods=['POST'])
def submit():
    ssid = request.form.get('ssid')
    password = request.form.get('password')
    
    try:
        subprocess.run(['sudo', 'nmcli', 'dev', 'wifi', 'connect', ssid, 'password', password],
                       check=True)
        if internet(timeout=3):
            display_status('success')
            time.sleep(2)
            start_radio_service()
        else:
            raise Exception("Connected but no internet")
    except:
        return redirect(url_for('index', message="Connection failed. Try again."))

# --- MAIN ENTRY POINT ---
if __name__ == '__main__':
    # 1. Check Internet with more patience
    
    logging.info("Checking for internet connection...")
    for i in range(6):  # Try for ~30 seconds
        if internet(timeout=5):
            logging.info("Internet detected!")
            internet_found = True
            break
        logging.info(f"No internet yet, attempt {i+1}/6")
        time.sleep(5)  # Wait 5 seconds between checks
    
    # If internet found, start radio and exit
    if internet_found:
        start_radio_service()
        sys.exit(0)  # Extra safety'''
    
    # 2. If no internet, start Portal Mode
    logging.info("No internet after 30s. Starting Portal.")
    init_display_for_portal()
    subprocess.run(['sudo', 'nmcli', 'device', 'wifi', 'hotspot', 'ifname', 'wlan0', 'ssid', 'One-Radio', 'password', 'scudworks'])
    
    t = threading.Thread(target=check_wifi_loop, daemon=True)
    t.start()
    
    app.run(host='0.0.0.0', port=8888, use_reloader=False)