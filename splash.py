#!/usr/bin/python3
import time
t0 = time.monotonic()
import driver as LCD_2inch

disp = LCD_2inch.LCD_2inch()
disp.Init()
disp.bl_DutyCycle(100)

with open('assets/scud_splash_1.raw', 'rb') as f:
    buf = f.read()

# replicate ShowImage's landscape setup exactly
disp.command(0x36)
disp.data(0x70)
disp.SetWindows(0, 0, disp.height, disp.width)   # (0,0,320,240)
disp.digital_write(disp.DC_PIN, True)

for i in range(0, len(buf), 4096):
    disp.spi_writebyte(list(buf[i:i+4096]))

with open('/tmp/splash-boot.log', 'w') as f:
    f.write(f"[{time.monotonic()-t0:.2f}s] frame up\n")

while True:
    time.sleep(3600)