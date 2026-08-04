from flask import Flask, jsonify, request, render_template, redirect, Response
import subprocess
import os

# --- CONFIGURATION ---
BASE_DIR = '/home/scud/scud-radio'
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
PORTAL_IP = "192.168.4.1"
AP_CON = "scud-ap"
CONTROLLER = os.path.join(BASE_DIR, 'net-controller.sh')
# ---------------------

app = Flask(__name__,
            static_folder=ASSETS_DIR,
            template_folder=os.path.join(BASE_DIR, 'templates'))

# Persistent port-80 -> 888 redirect, scoped to wlan0. Installed once, idempotently.
# Safe to leave up in both modes because Flask is mode-aware below: in AP mode it
# serves the setup page + 302s captive checks; when connected it serves the normal
# control UI + returns proper 204s, so nothing on a home LAN is hijacked.
# Users reach the radio at http://radio-<suffix>.local (avahi) on port 80.
def _ensure_redirect():
    rule = ['-t', 'nat', 'PREROUTING', '-i', 'wlan0', '-p', 'tcp',
            '--dport', '80', '-j', 'REDIRECT', '--to-ports', '888']
    exists = subprocess.run(['sudo', 'iptables', rule[0], rule[1], '-C', *rule[2:]],
                            stderr=subprocess.DEVNULL).returncode == 0
    if not exists:
        subprocess.run(['sudo', 'iptables', rule[0], rule[1], '-A', *rule[2:]])

_ensure_redirect()


# ---------- helpers ----------
def in_ap_mode():
    """True when our own AP connection is active."""
    out = subprocess.run(["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"],
                         capture_output=True, text=True).stdout
    return any(line.strip() == AP_CON for line in out.splitlines())


def list_networks():
    """Visible SSIDs, de-duplicated, preserving signal order from nmcli."""
    out = subprocess.run(["nmcli", "-t", "-f", "SSID", "device", "wifi", "list"],
                         capture_output=True, text=True).stdout
    seen, nets = set(), []
    for line in out.splitlines():
        s = line.strip()
        if s and s not in seen:
            seen.add(s)
            nets.append(s)
    return nets


def setup_page():
    """The Wi-Fi setup page shown while in AP mode."""
    nets = list_networks()
    options = "".join(f'<option value="{n}">{n}</option>' for n in nets)
    setup_tpl = os.path.join(BASE_DIR, 'templates', 'setup.html')
    if os.path.exists(setup_tpl):
        return render_template('setup.html', options=options)
    # Fallback inline page if no styled template is present yet.
    return Response(
        "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "</head><body style='font-family:sans-serif;max-width:24rem;margin:2rem auto;padding:0 1rem'>"
        "<h1>Scud Radio setup</h1>"
        "<p>Choose your Wi-Fi network and enter its password.</p>"
        "<form action='/connect' method='post'>"
        f"<select name='ssid' style='width:100%;padding:.5rem'>{options}</select><br><br>"
        "<input name='password' type='password' placeholder='Wi-Fi password' "
        "style='width:100%;padding:.5rem;box-sizing:border-box'><br><br>"
        "<button type='submit' style='padding:.6rem 1.2rem'>Connect</button>"
        "</form></body></html>",
        mimetype="text/html")


# ---------- captive-portal probe URLs ----------
# A 302 (instead of the empty 204 the OS expects when online) is the signal that
# makes Android/iOS/Windows pop the "sign in to network" sheet. Only do this in
# AP mode; when connected we return the real 204 so we never hijack a home LAN.
@app.route('/generate_204')
@app.route('/gen_204')
@app.route('/ncsi.txt')
@app.route('/connecttest.txt')
@app.route('/hotspot-detect.html')
@app.route('/library/test/success.html')
@app.route('/redirect')
def captive_check():
    if in_ap_mode():
        return redirect(f"http://{PORTAL_IP}/", code=302)
    return ('', 204)


# ---------- home ----------
@app.route('/', methods=['GET'])
def home():
    if in_ap_mode():
        return setup_page()
    return render_template('home.html')


# ---------- credential submission ----------
@app.route('/connect', methods=['POST'])
def connect():
    ssid = request.form.get('ssid', '')
    pw = request.form.get('password', '')
    # Create the profile and attempt association (bounded so a bad password
    # fails fast instead of hanging the request).
    subprocess.run(["nmcli", "--wait", "20", "device", "wifi", "connect", ssid, "password", pw],
                   capture_output=True, text=True)
    # Hand control back to the single brain to verify + start radio, or fall back to AP.
    subprocess.Popen([CONTROLLER, "retry"])
    return Response(
        "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "</head><body style='font-family:sans-serif;max-width:24rem;margin:2rem auto;padding:0 1rem'>"
        "<h1>Connecting&hellip;</h1>"
        "<p>If the radio joins your network it will start playing shortly. "
        "If it doesn't, reconnect to <b>Scud House</b> and try again.</p>"
        "</body></html>",
        mimetype="text/html")


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
    # threaded=True so parallel captive-probe requests from a phone don't queue.
    app.run(host='0.0.0.0', port=888, threaded=True)