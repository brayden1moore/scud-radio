#!/usr/bin/python

import socket
import json
import sys

CONTROL_SOCKET = "/tmp/radio_control"

def send_command(command, **kwargs):
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(CONTROL_SOCKET)
        
        cmd_data = {'command': command, **kwargs}
        sock.sendall((json.dumps(cmd_data) + '\n').encode('utf-8'))
        
        response = sock.recv(4096).decode('utf-8')
        sock.close()
        
        return json.loads(response)
    except FileNotFoundError:
        print("Error: Radio service not running or socket not found")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

def main():
    if len(sys.argv) < 2:
        print("""Scud Radio Remote Control

Usage:
    radio status              Show current status
    radio list                List all stations
    radio next                Next station
    radio prev                Previous station
    radio play <station>      Play a specific station
    radio random              Play a random station         
    radio volume <0-100>      Set volume
    radio up                  Increase volume
    radio down                Decrease volume
    radio favorite            Toggle favorite on current station
    radio off                 Put the radio to sleep
    radio on                  Wake the radio up
    radio restart             Restart the radio and gather updates
""")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == 'status':
        result = send_command('status')
        if result['status'] == 'ok':
            print(f"Station: {result['station']}")
            print(f"Now Playing: {result['now_playing']}")
            print(f"Volume: {result['volume']}/100 ({round(result['volume']/100)}%)")
            print(f"Battery: {result.get('battery', 'N/A')}%")
            print(f"Charging: {result.get('charging', False)}")
    
    elif command == 'list':
        result = send_command('list')
        if result['status'] == 'ok':
            print(f"\nStations ({len(result['stations'])}):")
            for station in result['stations']:
                marker = "★" if station in result['favorites'] else " "
                print(f"  {marker} {station}")
    
    elif command == 'next':
        result = send_command('next')
        print(f"Now playing: {result.get('station', 'N/A')}")
    
    elif command == 'prev':
        result = send_command('prev')
        print(f"Now playing: {result.get('station', 'N/A')}")
    
    elif command == 'play':
        if len(sys.argv) < 3:
            print("Error: Please specify station name")
            sys.exit(1)
        station = ' '.join(sys.argv[2:])
        result = send_command('play', station=station)
        if result['status'] == 'ok':
            print(f"Now playing: {result['station']}")
        else:
            print(f"Error: {result['message']}")
    
    elif command == 'random':
        result = send_command('play_random')
    
    elif command == 'volume':
        if len(sys.argv) < 3:
            print("Error: Please specify volume (0-150)")
            sys.exit(1)
        try:
            vol = int(sys.argv[2])
            vol = round(vol*150/100)
            result = send_command('set_volume', value=vol)
            print(f"Volume set to: {result['volume']}/100 ({round(result['volume']/100)}%)")
        except ValueError:
            print("Error: Volume must be a number")
            sys.exit(1)
    
    elif command in ['volume_up', 'vol_up', 'up']:
        result = send_command('volume_up')
        print(f"Volume: {result['volume']}/150 ({round(result['volume']/150*100)}%)")
    
    elif command in ['volume_down', 'vol_down', 'down']:
        result = send_command('volume_down')
        print(f"Volume: {result['volume']}/150 ({round(result['volume']/150*100)}%)")
    
    elif command in ['favorite', 'fav']:
        result = send_command('favorite')
        print(f"Favorites: {', '.join(result['favorites'])}")

    elif command == 'off':
        result = send_command('off')

    elif command == 'on':
        result = send_command('on')

    elif command == 'restart':
        result = send_command('restart')

    elif command == 'power':
        result = send_command('power')

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == '__main__':
    main()