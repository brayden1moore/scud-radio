#!/usr/bin/python3
import time
t0 = time.monotonic()
import driver as LCD_2inch

disp = LCD_2inch.LCD_2inch()
disp.Init()
disp.bl_DutyCycle(100)

with open('assets/scud_splash_1.raw', 'rb') as f:
    buf = f.read()

count = 0
while True:
    disp.Init()                    # full reset + init each time
    disp.bl_DutyCycle(100)
    disp.command(0x36); disp.data(0x70)
    disp.SetWindows(0, 0, disp.height, disp.width)
    disp.digital_write(disp.DC_PIN, True)
    for i in range(0, len(buf), 4096):
        disp.spi_writebyte(list(buf[i:i+4096]))
    with open('/tmp/splash-boot.log','a') as f:
        f.write(f"reinit+draw uptime: {open('/proc/uptime').read().split()[0]}s\n")
    time.sleep(1)