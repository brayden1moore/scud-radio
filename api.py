from flask import Flask, jsonify, request
import subprocess
import sys
app = Flask(__name__)

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
        'status': 'status',
        'random': 'random',
        'up': 'volume_up',
        'down': 'volume_down',
        'power': 'power'
    }
    
    if command not in allowed_commands:
        return jsonify({'error': 'Invalid command'}), 400
    
    try:
        station = request.args.get('station') or request.args.get('', None)
        
        if station:
            cmd_list = ['sudo', 'python', '/home/scud/scud-radio/control.py', allowed_commands[command], station]
        else:
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
            'station': station.replace('+', ' ') if station else None,
            'output': str(result.stdout).replace('\n', ''),
            'error': result.stderr
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8887)