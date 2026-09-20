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
    log(f"LCD object created ({disp.width}x{disp.height}, rotation={disp.rotation})")

    disp.Init()
    log("Init() done")

    disp.bl_DutyCycle(100)
    log("backlight on")

    with open('assets/scud_splash_1.raw', 'rb') as f:
        buf = f.read()

    expected = disp.width * disp.height * 2
    log(f"raw loaded ({len(buf)} bytes, expected {expected})")
    if len(buf) != expected:
        raise ValueError(
            f"raw file is {len(buf)} bytes but the panel needs {expected} "
            f"({disp.width}x{disp.height} at 2 bytes/px) -- regenerate it"
        )

    # width/height are already rotation-aware in this driver, so pass them
    # in that order. Passing (height, width) asks for a 240x320 window,
    # which SetWindows clamps to 240x240 -- the frame then wraps and
    # nothing lands where you expect.
    disp.SetWindows(0, 0, disp.width, disp.height)
    disp.data_bytes(list(buf))
    log("frame written")

except Exception:
    import traceback
    with open('/tmp/splash-debug.log', 'a') as f:
        f.write("EXCEPTION:\n")
        traceback.print_exc(file=f)

# keep the splash up
while True:
    time.sleep(3600)