from flask import Flask,request, render_template, session, redirect, url_for, jsonify
from PIL import Image, ImageDraw, ImageFont, ImageSequence
from gpiozero import Device
import driver as LCD_2inch
import subprocess
import socket
import sys
import time
import threading
import os

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

# 2 inch
RST = 27
DC = 25
BL = 23
bus = 0 
device = 0 
MAX_BL = 100
disp = None

def display_setup():
    global disp
    if disp is not None:
        return 
    
    disp = LCD_2inch.LCD_2inch()
    disp.Init()
    disp.clear()
    disp.bl_DutyCycle(MAX_BL)
    image = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT))
    bg = Image.open(f'assets/hello.png')
    image.paste(bg, (0, 0))
    disp.ShowImage(image)

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

def internet(host="8.8.8.8", port=53, timeout=3):
    """
    Host: 8.8.8.8 (google-public-dns-a.google.com)
    OpenPort: 53/tcp
    Service: domain (DNS/TCP)
    """
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error as ex:
        print(ex)
        return False

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
        print(*list(request.form.keys()), sep=", ")
        ssid = request.form['ssid']
        password = request.form['password']

        try:
            result = subprocess.run(['nmcli', 'dev', 'wifi', 'connect', ssid, 'password', password],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, check=True)
            
            assert internet()
            display_result('success')
            time.sleep(3)
            disp.clear()
            disp.reset()
            Device.close()
            time.sleep(1)
            subprocess.run(['sudo','systemctl', 'restart','radio'])
               
        except:
            return redirect(url_for('index', wifi_networks=scan_wifi(), message="That didn't work. Try again!"))
            
    else:
        return redirect(url_for('index', wifi_networks=scan_wifi(), message=""))

if __name__ == '__main__':
    connected = internet()

    if not connected:
        display_setup()
        start_hotspot()
        app.run(host='0.0.0.0', port=8888, use_reloader=False)
    else:
        print("Internet connection already available. No configuration needed.")
        print("Starting radio")
        subprocess.run(['python', 'radio.py'])
        time.sleep(1)
        sys.exit(0)