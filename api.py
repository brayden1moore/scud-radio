from flask import Flask, jsonify, request, render_template
import subprocess
import sys
import os

# --- CONFIGURATION ---
BASE_DIR = '/home/scud/scud-radio'
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
# ---------------------

app = Flask(__name__, static_folder=ASSETS_DIR, template_folder=os.path.join(BASE_DIR, 'templates'))

subprocess.run(['sudo', 'iptables', '-t', 'nat', '-A', 'PREROUTING', '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-ports', '8888'])

@app.route('/', methods=['GET'])
def home():
    return render_template('home.html')

@app.route('/control/<command>', methods=['POST', 'GET'])
def control(command):
    allowed_commands = {
        'favorite': 'favorite',
        'off': 'off',
        'on': 'on',
        'volume_up': 'volume_up',
        'volume_down': 'volume_down',
        'prev': 'prev',
        'next': 'next',
        'play': 'play',
        'play_random':'play_random',
        'random':'play_random',
        'status': 'status',
        'random': 'random',
        'up': 'volume_up',
        'down': 'volume_down',
        'power': 'power',
        'toggle':'toggle',
        'pause':'pause',
        'resume':'resume',
        'list':'list',
        'favorites':'favorites',
        'restart':'restart'
    }
    
    if command not in allowed_commands:
        return jsonify({'error': 'Invalid command'}), 400
    
    try:
        station = request.args.get('station') or request.args.get('', None)

        cmd_list = ['sudo', 'python', '/home/scud/scud-radio/control.py', allowed_commands[command]]
        
        if station:
            cmd_list.append(station.replace('+', ' '))
        
        result = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        return jsonify({
            'success': True,
            'command': command,
            'output': str(result.stdout).replace('\n', ''),
            'error': result.stderr
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=888)