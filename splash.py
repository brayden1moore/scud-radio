#!/usr/bin/python3
import time
import mmap
import os

LOG = '/tmp/splash.log'

try:
    with open(LOG, 'w') as log:
        log.write(f"Started at {time.time()}\n")
        
        while not os.path.exists('/dev/fb1'):
            log.write("Waiting for /dev/fb1...\n")
            time.sleep(0.1)
        
        log.write(f"FB exists at {time.time()}\n")
        
        pid = os.fork()
        if pid > 0:
            exit(0)
        
        with open('/dev/fb1', 'r+b') as fb:
            with open('/home/scud/scud-radio/assets/scud-raw.bin', 'rb') as img:
                mm = mmap.mmap(fb.fileno(), 320*240*2)
                mm[:] = img.read()
                mm.close()
        
        log.write(f"Displayed at {time.time()}\n")
        
except Exception as e:
    with open(LOG, 'a') as log:
        log.write(f"ERROR: {e}\n")

while True:
    time.sleep(1)