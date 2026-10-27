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


# =============================================================================
# Portal API (templates/home.html). JSON in, JSON out.
# Talks to radio.py over its control socket, reads the listening log, and runs
# nmcli / git / systemctl for the Wi-Fi and Device pages. api.py runs as root.
# =============================================================================
import json
import socket
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from flask import send_file

LIB_PATH = Path('/var/lib/scud-radio')
CONTROL_SOCKET = '/tmp/radio_control'
LISTEN_DB = LIB_PATH / 'listening.db'


def radio(command, value=None, timeout=6):
    """One request/response over radio.py's control socket."""
    msg = {'command': command}
    if value is not None:
        msg['value'] = value
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(CONTROL_SOCKET)
        s.sendall((json.dumps(msg) + '\n').encode('utf-8'))
        buf = b''
        while not buf.endswith(b'\n'):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode('utf-8') or '{}')
    finally:
        s.close()


def radio_or_503(command, value=None):
    try:
        out = radio(command, value)
    except (FileNotFoundError, ConnectionRefusedError, socket.timeout, OSError):
        return jsonify({'status': 'error', 'message': 'The radio isn’t running right now.'}), 503
    return jsonify(out if out is not None else {'status': 'ok'})


def _safe(name):
    return name.replace(' ', '_')


def _run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 1, '', str(e)


# ---------- now playing + controls ----------
@app.route('/api/state')
def api_state():
    return radio_or_503('state')


@app.route('/api/stations')
def api_stations():
    return radio_or_503('stations')


@app.route('/api/control', methods=['POST'])
def api_control():
    body = request.get_json(silent=True) or {}
    cmd = body.get('cmd')
    value = body.get('value')
    simple = {'next': 'next', 'prev': 'prev', 'random': 'play_random', 'favorite': 'favorite',
              'mute': 'mute_toggle', 'wake': 'wake'}
    if cmd in simple:
        return radio_or_503(simple[cmd])
    if cmd == 'play' and isinstance(value, str):
        return radio_or_503('play', value)
    if cmd == 'volume':
        return radio_or_503('set_volume_notch', int(value or 0))
    if cmd == 'sleep_timer':
        return radio_or_503('sleep_timer', int(value or 0))
    if cmd == 'favorites' and isinstance(value, list):
        return radio_or_503('set_favorites', [str(v) for v in value])
    if cmd == 'hidden' and isinstance(value, list):
        return radio_or_503('set_hidden', [str(v) for v in value])
    return jsonify({'status': 'error', 'message': 'Unknown command'}), 400


@app.route('/api/logo')
def api_logo():
    """Station logos from the radio's own cache, so the portal works even
    when the phone can't reach one.radio."""
    name = request.args.get('name', '')
    size = request.args.get('size', '96')
    if size not in ('25', '60', '96', '216', '320') or not name or '/' in name or '..' in name:
        return ('', 404)
    p = LIB_PATH / f'{_safe(name)}_{size}.png'
    if not p.exists():
        return ('', 404)
    resp = send_file(str(p), mimetype='image/png')
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


# ---------- settings ----------
@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'GET':
        return radio_or_503('get_settings')
    return radio_or_503('set_settings', request.get_json(silent=True) or {})


# ---------- Wi-Fi ----------
_wifi_job = {'state': 'idle', 'ssid': None, 'message': ''}


def _wifi_profiles(active_only=False):
    cmd = ['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'] + (['--active'] if active_only else [])
    _, out, _ = _run(cmd)
    names = []
    for line in out.splitlines():
        name, _, typ = line.replace('\\:', '\x00').rpartition(':')
        name = name.replace('\x00', ':')
        if typ == '802-11-wireless' and name != AP_CON:
            names.append(name)
    return names


@app.route('/api/wifi')
def api_wifi():
    if request.args.get('rescan'):
        _run(['nmcli', 'device', 'wifi', 'rescan'], timeout=10)
        time.sleep(3)
    current, nets, seen = None, [], set()
    _, out, _ = _run(['nmcli', '-t', '-f', 'ACTIVE,SIGNAL,SECURITY,SSID', 'device', 'wifi', 'list'])
    for line in out.splitlines():
        parts = line.replace('\\:', '\x00').split(':')
        if len(parts) < 4:
            continue
        active, signal, sec, ssid = [p.replace('\x00', ':') for p in parts[:4]]
        if not ssid:
            continue
        try:
            signal = int(signal)
        except ValueError:
            signal = 0
        item = {'ssid': ssid, 'signal': signal, 'locked': bool(sec and sec != '--')}
        if active == 'yes':
            current = item
        elif ssid not in seen:
            nets.append(item)
        seen.add(ssid)
    nets = [n for n in nets if not current or n['ssid'] != current['ssid']]
    nets.sort(key=lambda n: -n['signal'])
    _, ip, _ = _run(['hostname', '-I'])
    return jsonify({'status': 'ok', 'current': current, 'networks': nets[:20],
                    'saved': _wifi_profiles(), 'ip': (ip.split() or [''])[0],
                    'hostname': socket.gethostname() + '.local', 'job': _wifi_job})


def _join(ssid, password):
    active = _wifi_profiles(active_only=True)
    old = active[0] if active else None
    existed = ssid in _wifi_profiles()
    _wifi_job.update(state='joining', ssid=ssid, message='')
    cmd = ['nmcli', '--wait', '20', 'device', 'wifi', 'connect', ssid]
    if password:
        cmd += ['password', password]
    code, _, _ = _run(cmd, timeout=30)
    if code == 0:
        # the controller owns connections; keep NM from autoconnecting this one
        _run(['nmcli', 'connection', 'modify', 'id', ssid, 'connection.autoconnect', 'no'])
        _wifi_job.update(state='joined', message='')
        return
    # didn't work: put things back how they were
    if not existed:
        _run(['nmcli', 'connection', 'delete', 'id', ssid])
    restored = bool(old) and _run(['nmcli', '--wait', '15', 'connection', 'up', 'id', old], timeout=25)[0] == 0
    if not restored:
        subprocess.Popen([CONTROLLER, 'retry'])
    _wifi_job.update(state='failed', message='Couldn’t join ' + ssid + '. Check the password and try again.')


@app.route('/api/wifi/join', methods=['POST'])
def api_wifi_join():
    body = request.get_json(silent=True) or {}
    ssid = str(body.get('ssid') or '').strip()
    if not ssid:
        return jsonify({'status': 'error', 'message': 'Pick a network.'}), 400
    if _wifi_job['state'] == 'joining':
        return jsonify({'status': 'error', 'message': 'Already joining a network.'}), 409
    threading.Thread(target=_join, args=(ssid, str(body.get('password') or '')), daemon=True).start()
    return jsonify({'status': 'ok', 'job': {'state': 'joining', 'ssid': ssid}})


@app.route('/api/wifi/forget', methods=['POST'])
def api_wifi_forget():
    """Forget the current network; Otis joins another saved one, or opens setup."""
    active = _wifi_profiles(active_only=True)
    if not active:
        return jsonify({'status': 'error', 'message': 'Not connected to a saved network.'}), 400
    def go():
        time.sleep(1)                      # let this response reach the phone first
        _run(['nmcli', 'connection', 'delete', 'id', active[0]])
        subprocess.Popen([CONTROLLER, 'retry'])
    threading.Thread(target=go, daemon=True).start()
    return jsonify({'status': 'ok'})


# ---------- device ----------
def _git(*args, timeout=30):
    # the repo belongs to scud; running git as root trips "dubious ownership"
    return _run(['runuser', '-u', 'scud', '--', 'git', '-C', BASE_DIR, *args], timeout=timeout)


def _restart_services(include_api=True):
    def go():
        time.sleep(1.5)
        subprocess.run(['systemctl', 'restart', 'radio.service'])
        if include_api:
            subprocess.run(['systemctl', 'restart', 'api.service'])
    threading.Thread(target=go, daemon=True).start()


@app.route('/api/device')
def api_device():
    up = ''
    try:
        secs = int(float(open('/proc/uptime').read().split()[0]))
        d, rem = divmod(secs, 86400)
        h, rem = divmod(rem, 3600)
        up = f'{d} d {h} h' if d else f'{h} h {rem // 60} m'
    except Exception:
        pass
    temp = ''
    try:
        temp = f"{int(open('/sys/class/thermal/thermal_zone0/temp').read()) / 1000:.0f}°C"
    except Exception:
        pass
    _, rev, _ = _git('rev-parse', '--short', 'HEAD')
    _, date, _ = _git('log', '-1', '--format=%cd', '--date=short')
    return jsonify({'status': 'ok', 'uptime': up, 'temperature': temp,
                    'version': rev, 'version_date': date, 'hostname': socket.gethostname() + '.local'})


@app.route('/api/device/update', methods=['GET', 'POST'])
def api_device_update():
    """GET: is there anything new? POST: install it (git pull, then restart)."""
    code, _, _ = _git('fetch', '--quiet', timeout=40)
    if code != 0:
        return jsonify({'status': 'error', 'message': 'Couldn’t reach the update server.'}), 502
    _, behind, _ = _git('rev-list', '--count', 'HEAD..@{u}')
    try:
        behind = int(behind or 0)
    except ValueError:
        behind = 0
    if request.method == 'GET':
        return jsonify({'status': 'ok', 'available': behind})
    if not behind:
        return jsonify({'status': 'ok', 'installed': False, 'message': 'Already up to date.'})
    code, _, err = _git('pull', '--ff-only', '--quiet', timeout=90)
    if code != 0:
        return jsonify({'status': 'error', 'message': 'Update failed: ' + err[-200:]}), 500
    subprocess.run(['chmod', '+x', CONTROLLER])      # keep the boot script runnable
    _restart_services()
    return jsonify({'status': 'ok', 'installed': True})


@app.route('/api/device/restart', methods=['POST'])
def api_device_restart():
    _restart_services(include_api=False)
    return jsonify({'status': 'ok'})


@app.route('/api/device/setup', methods=['POST'])
def api_device_setup():
    """Forget every network and bring back the Otis-Setup network."""
    def go():
        time.sleep(1)
        for name in _wifi_profiles():
            _run(['nmcli', 'connection', 'delete', 'id', name])
        subprocess.Popen([CONTROLLER, 'portal'])
    threading.Thread(target=go, daemon=True).start()
    return jsonify({'status': 'ok'})


@app.route('/api/device/reset', methods=['POST'])
def api_device_reset():
    """Favorites, hidden stations, settings and listening history. Wi-Fi stays."""
    for f in ('config.json', 'favorites.txt', 'hidden.txt', 'listening.db', 'listening.db-wal', 'listening.db-shm'):
        try:
            (LIB_PATH / f).unlink()
        except FileNotFoundError:
            pass
    _restart_services(include_api=False)
    return jsonify({'status': 'ok'})


# ---------- listening stats ----------
def _listener_tz():
    try:
        import pytz
        tz = json.loads((LIB_PATH / 'config.json').read_text()).get('timezone')
        return pytz.timezone(tz) if tz else None
    except Exception:
        return None


@app.route('/api/stats')
def api_stats():
    days = {'week': 7, 'month': 30, 'year': 365}.get(request.args.get('period', 'week'), 7)
    now = time.time()
    t0, prev0 = now - days * 86400, now - 2 * days * 86400
    if not LISTEN_DB.exists():
        return jsonify({'status': 'ok', 'empty': True, 'days': days})
    con = sqlite3.connect(str(LISTEN_DB), timeout=5)
    rows = con.execute('SELECT station, city, genres, status, source, started, seconds FROM plays '
                       'WHERE started >= ? AND seconds > 0', (prev0,)).fetchall()
    first = dict(con.execute("SELECT station, MIN(started) FROM plays WHERE source='radio' GROUP BY station").fetchall())
    con.close()
    tz = _listener_tz()
    cur = [r for r in rows if r[5] >= t0]
    prev_total = sum(r[6] for r in rows if r[5] < t0)
    total = sum(r[6] for r in cur)
    radio_rows = [r for r in cur if r[4] == 'radio']
    radio_total = sum(r[6] for r in radio_rows)
    by_station, by_city, by_genre = {}, {}, {}
    for st, city, genres, status, source, started, secs in radio_rows:
        by_station[st] = by_station.get(st, 0) + secs
        if city:
            by_city[city] = by_city.get(city, 0) + secs
        try:
            for gname in json.loads(genres or '[]'):
                by_genre[gname] = by_genre.get(gname, 0) + secs
        except Exception:
            pass
    hours = [0.0] * 24
    for r in cur:                          # spread each stretch over the hours it covered
        t, end = r[5], r[5] + r[6]
        while t < end:
            dt = datetime.fromtimestamp(t, tz) if tz else datetime.fromtimestamp(t)
            nxt = t + (3600 - (dt.minute * 60 + dt.second))
            hours[dt.hour] += min(end, nxt) - t
            t = nxt
    longest = max(radio_rows, key=lambda r: r[6], default=None)
    top = sorted(by_station.items(), key=lambda kv: -kv[1])[:5]
    h = lambda s: round(s / 3600, 1)
    out = {
        'status': 'ok', 'empty': not cur, 'days': days,
        'hours': h(total), 'hours_change': h(total - prev_total), 'has_previous': prev_total > 0,
        'stations': len(by_station),
        'new': sorted(st for st, ts in first.items() if ts >= t0),
        'live_share': round(100 * sum(r[6] for r in radio_rows if r[3] == 'Live') / radio_total) if radio_total else 0,
        'top': [{'name': n, 'hours': h(s)} for n, s in top],
        'by_hour': [round(x / 60) for x in hours],
        'airplay_share': round(100 * (total - radio_total) / total) if total else 0,
        'cities': [{'city': c, 'hours': h(s)} for c, s in sorted(by_city.items(), key=lambda kv: -kv[1])[:8]],
        'genres': [g for g, _ in sorted(by_genre.items(), key=lambda kv: -kv[1])[:8]],
        'city_count': len(by_city),
    }
    if longest:
        day = datetime.fromtimestamp(longest[5], tz) if tz else datetime.fromtimestamp(longest[5])
        out['longest'] = {'station': longest[0], 'minutes': round(longest[6] / 60), 'day': day.strftime('%A')}
    return jsonify(out)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=888, threaded=True)