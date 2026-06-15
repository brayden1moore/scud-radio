#!/usr/bin/python3
import os
# Force a specific pin factory BEFORE importing anything that uses gpiozero.
# lgpio is the Bookworm default and usually the most reliable early in boot.
os.environ.setdefault('GPIOZERO_PIN_FACTORY', 'lgpio')

import time
t0 = time.monotonic()

def up():
    return open('/proc/uptime').read().split()[0]

def log(msg):
    with open('/tmp/splash-debug.log', 'a') as f:
        f.write(f"[{time.monotonic()-t0:.2f}s into script | uptime {up()}s] {msg}\n")

log("script start")

try:
    import driver as LCD_2inch
    log("imported driver")

    disp = LCD_2inch.LCD_2inch()
    log("LCD object created")

    disp.Init()
    log("Init() done")

    disp.bl_DutyCycle(100)
    log("backlight on")

    with open('assets/scud_splash_1.raw', 'rb') as f:
        buf = f.read()
    log(f"raw loaded ({len(buf)} bytes)")

    disp.command(0x36)
    disp.data(0x70)
    disp.SetWindows(0, 0, disp.height, disp.width)
    disp.digital_write(disp.DC_PIN, True)
    for i in range(0, len(buf), 4096):
        disp.spi_writebyte(list(buf[i:i+4096]))
    log("frame written")

except Exception:
    import traceback
    with open('/tmp/splash-debug.log', 'a') as f:
        f.write("EXCEPTION:\n")
        traceback.print_exc(file=f)

# keep the splash up
while True:
    time.sleep(3600)