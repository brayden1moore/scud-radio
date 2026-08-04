from flask import (Flask, jsonify, request, render_template,
                   redirect, Response, send_from_directory)
import subprocess
import urllib.parse
import os

# --- CONFIGURATION ---
BASE_DIR = '/home/scud/scud-radio'
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
PORTAL_STATIC = os.path.join(BASE_DIR, 'portal-static')   # css/, js/, img/ for the setup portal
PORTAL_IP = "192.168.4.1"
AP_CON = "scud-ap"
CONTROLLER = os.path.join(BASE_DIR, 'net-controller.sh')
# ---------------------

app = Flask(__name__,
            static_folder=ASSETS_DIR,          # your existing radio UI assets
            template_folder=os.path.join(BASE_DIR, 'templates'))


# Persistent port-80 -> 888 redirect, scoped to wlan0. Installed once, idempotently.
# Safe in both modes because Flask is mode-aware: AP mode serves the setup portal and
# 302s captive checks; connected mode serves the control UI and returns real 204s.
def _ensure_redirect():
    rule = ['PREROUTING', '-i', 'wlan0', '-p', 'tcp', '--dport', '80',
            '-j', 'REDIRECT', '--to-ports', '888']
    exists = subprocess.run(['sudo', 'iptables', '-t', 'nat', '-C', *rule],
                            stderr=subprocess.DEVNULL).returncode == 0
    if not exists:
        subprocess.run(['sudo', 'iptables', '-t', 'nat', '-A', *rule])

_ensure_redirect()


# ---------- helpers ----------
def in_ap_mode():
    """True when our own AP connection is active."""
    out = subprocess.run(["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"],
                         capture_output=True, text=True).stdout
    return any(line.strip() == AP_CON for line in out.splitlines())


def scan_points():
    """
    Build the 'points' list the index template expects.
    Each point has: ssid, ssid_encoded, security ('encrypted' or '').
    De-duplicated, strongest signal first.
    """
    out = subprocess.run(
        ["nmcli", "-t", "-f", "SIGNAL,SECURITY,SSID", "device", "wifi", "list"],
        capture_output=True, text=True).stdout

    seen, points = set(), []
    for line in out.splitlines():
        # nmcli -t escapes ':' inside fields as '\:'; protect those before split.
        parts = line.replace('\\:', '\x00').split(':')
        if len(parts) < 3:
            continue
        security = parts[1].replace('\x00', ':')
        ssid = parts[2].replace('\x00', ':').strip()
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        points.append({
            "ssid": ssid,
            "ssid_encoded": urllib.parse.quote(ssid, safe=''),
            "security": "encrypted" if security and security != "--" else "",
        })
    return points


# ---------- static assets for the setup portal ----------
@app.route('/static/<path:filename>')
def portal_static(filename):
    return send_from_directory(PORTAL_STATIC, filename)


# ---------- captive-portal probe URLs ----------
# A 302 (instead of the empty 204 the OS expects when online) makes the phone pop
# the "sign in to network" sheet. Only in AP mode; connected mode returns real 204.
@app.route('/generate_204')
@app.route('/gen_204')
@app.route('/ncsi.txt')
@app.route('/connecttest.txt')
@app.route('/hotspot-detect.html')
@app.route('/library/test/success.html')
@app.route('/redirect')
def captive_check():
    if in_ap_mode():
        return redirect("http://" + PORTAL_IP + "/", code=302)
    return ('', 204)


# ---------- portal: page 1, network list ----------
@app.route('/', methods=['GET'])
def home():
    if in_ap_mode():
        return render_template('index.html', points=scan_points())
    return render_template('home.html')


# ---------- portal: page 2, password entry ----------
@app.route('/confirm', methods=['GET'])
def confirm():
    ssid_encoded = request.args.get('ssid', '')
    return render_template('confirm.html', ssid_encoded=ssid_encoded)


# ---------- portal: page 3, perform connection ----------
@app.route('/connect', methods=['POST'])
def connect():
    ssid_encoded = request.form.get('ssid', '')
    pw = request.form.get('password', '')
    ssid = urllib.parse.unquote(ssid_encoded)

    # Create the profile and attempt association (bounded so a bad password
    # fails fast instead of hanging the page).
    if pw:
        subprocess.run(["nmcli", "--wait", "20", "device", "wifi", "connect",
                        ssid, "password", pw], capture_output=True, text=True)
    else:
        subprocess.run(["nmcli", "--wait", "20", "device", "wifi", "connect", ssid],
                       capture_output=True, text=True)

    # Hand control to the single brain to verify + start radio, or fall back to AP.
    subprocess.Popen([CONTROLLER, "retry"])

    # Show the "attempting to connect" page (it meta-refreshes back to / after 8s).
    return render_template('connect.html', ssid=ssid)


# ---------- radio control (unchanged) ----------
@app.route('/control/<command>', methods=['POST', 'GET'])
def control(command):
    allowed_commands = {
        'favorite': 'favorite',
        'hide': 'hide',
        'off': 'off',
        'on': 'on',
        'volume_up': 'volume_up',
        'volume_down': 'volume_down',
        'prev': 'prev',
        'next': 'next',
        'play': 'play',
        'play_random': 'play_random',
        'random': 'play_random',
        'status': 'status',
        'up': 'volume_up',
        'down': 'volume_down',
        'power': 'power',
        'toggle': 'toggle',
        'pause': 'pause',
        'resume': 'resume',
        'list': 'list',
        'favorites': 'favorites',
        'restart': 'restart',
        'mute': 'mute'
    }

    if command not in allowed_commands:
        return jsonify({'error': 'Invalid command'}), 400

    try:
        station = request.args.get('station') or request.args.get('', None)
        cmd_list = ['sudo', 'python', '/home/scud/scud-radio/control.py', allowed_commands[command]]
        if station:
            cmd_list.append(station.replace('+', ' '))
        result = subprocess.run(cmd_list, capture_output=True, text=True, timeout=5)
        return jsonify({
            'success': True,
            'command': command,
            'output': str(result.stdout).replace('\n', ''),
            'error': result.stderr
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=888, threaded=True)