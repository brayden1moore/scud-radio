import subprocess
import socket

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

connected = internet()
while not connected:

    options = scan_wifi()
    print("Which wifi?")

    for idx, i in enumerate(options):
        print(idx, ' -- ', i)

    ssid = options[int(input())]
    print("Password?")
    password = input()
    print('Thx')

    try:
        result = subprocess.run(['nmcli', 'dev','wifi' ,'connect' ,ssid ,'password' ,password],
                    stdout=subprocess.PIPE,
                    text=True, check=True)

        print("Success")
        connected = internet()
    except:
        print("That didn't work")