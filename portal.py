from flask import Flask,request, render_template, session, redirect, url_for, jsonify
import subprocess
import socket
import sys
import time
import threading


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
    if request.method == 'POST':
        print(*list(request.form.keys()), sep=", ")
        ssid = request.form['ssid']
        password = request.form['password']

        session['ssid'] = ssid
        session['password'] = password
        
        return redirect(url_for('success'))
    
    else:
        return redirect(url_for('index', wifi_networks=scan_wifi(), message=""))
    
@app.route('/success', methods=['GET'])
def success():
    return render_template('success.html')

@app.route('/connect', methods=['POST'])
def connect():
    try:
        result = subprocess.run(['nmcli', 'dev', 'wifi', 'connect', session['ssid'], 'password', session['password']],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, check=True)
        
        assert internet()
        start_hotspot()
        response = jsonify({'message': 'success', 'info': 'Device will switch networks in 3 seconds'})
        
        print("Starting radio")
        subprocess.run(['/usr/bin/python3', '/home/scud/scud-radio/radio.py'],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        return response
        
    except:
        print(f"WiFi connection failed")
        return jsonify({'message': 'error', 'error': 'Connection failed'}), 400

if __name__ == '__main__':
    connected = internet()

    if not connected:
        start_hotspot()
        app.run(debug=True, host='0.0.0.0', port=8888)
    else:
        print("Internet connection already available. No configuration needed.")
        print("Starting radio")
        subprocess.run(['/usr/bin/python3', '/home/scud/scud-radio/radio.py'])
        sys.exit(0)