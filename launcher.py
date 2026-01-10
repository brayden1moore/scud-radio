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

def setup_redirect(port):
    for i in range(4):
        try:
            subprocess.run(['sudo', 'iptables','-t', 'nat','-D', 'PREROUTING', '1'])
        except:
            pass
    subprocess.run(['sudo', 'iptables', '-t', 'nat', '-A', 'PREROUTING', '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-ports', port])

disp = None
app = Flask(__name__, static_folder=ASSETS_DIR, template_folder=os.path.join(BASE_DIR, 'templates'))
app.secret_key = 'sticky-lemon'

def start_radio_service():
    """Stops the launcher and starts the main radio service"""
    logging.info("Starting Radio Service...")
    setup_redirect("7777")
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

def connect_to_wifi(ssid, password):
    subprocess.run(['sudo', 'nmcli', 'dev', 'wifi', 'connect', ssid, 'password', password],
            check=True)

@app.route('/')
def index():
    setup_redirect("8888")
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

def currently_connected():
    status = subprocess.run(["nmcli", "dev", "status"],
                                stdout=subprocess.PIPE, text=True)
    statuses = status.stdout.strip().split('\n')
    for i in statuses: # for each line in the stdout
        if 'wlan0' in i: # if the line has wlan0
            wlan_status = i.split(' ')
            if wlan_status[0] == 'wlan0': # if the line IS wlan0
                if 'connected' in wlan_status: # if status is connected
                    logging.info('Wifi is connected')
                    return True
                else:
                    return False

if __name__ == '__main__':
    subprocess.run(['sudo', 'iptables', '-t', 'nat', '-A', 'PREROUTING', '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-ports', '8888'])

    # 1. Check Internet with more patience
    internet_found = currently_connected()

    # If internet found, start radio and exit
    #if internet_found:
    #    start_radio_service()
    #    sys.exit(0)  # Extra safety'''
    
    # if not, try known networks
    if (not internet_found) and networks: # try connecting to other known
        for ssid, password in networks.items():
            connect_to_wifi(ssid, password)

    # 2. If no internet, start Portal Mode
    logging.info("Starting Portal.")
    init_display_for_portal()
    subprocess.run(['sudo', 'nmcli', 'device', 'wifi', 'hotspot', 'ifname', 'wlan0', 'ssid', 'One-Radio', 'ifname', '$WIFI_INTERFACE', 'ip4-method shared'])
    subprocess.run(['sudo', 'nmcli', 'connection', 'modify', 'One-Radio', 'wlan0', 'ssid', 'One-Radio', 'wifi-sec.key-mgmt', 'none'])
    subprocess.run(['sudo', 'nmcli', 'connection', 'up', 'One-Radio'])
    
    #t = threading.Thread(target=check_wifi_loop, daemon=True)
    #t.start()
    
    app.run(host='0.0.0.0', port=8888, use_reloader=False)