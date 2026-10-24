#!/usr/bin/env python3
"""Generate Otis's system screens (boot, setup, errors, goodbye, updating) and
the Otis face used by the setup portal and the phone remote.

Run from the repo root:   python3 tools/make_screens.py
Edit the COPY / colours below and re-run; every file is regenerated.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / 'assets'
W, H = 320, 240

BLACK, WHITE, YELLOW = (0, 0, 0), (255, 255, 255), (255, 255, 0)
MUTED = (150, 150, 150)
SETUP_SSID = 'Otis-Setup'          # keep in sync with AP_SSID in net-controller.sh

FACE = Image.open(A / 'otis_face.png').convert('RGBA')      # black line art, transparent


def archivo(size, weight=800):
    f = ImageFont.truetype(str(A / 'Archivo/Archivo-VariableFont_wdth,wght.ttf'), size)
    f.set_variation_by_axes([weight, 100])
    return f


def favorit(size):
    return ImageFont.truetype(str(A / 'Favorit/ABCFavoritMono-Regular.otf'), size)


def face(size, color=BLACK):
    """Otis's face cropped to its ink, scaled to `size` px wide, in `color`."""
    art = FACE.crop(FACE.getbbox())
    art = art.resize((size, round(size * art.height / art.width)), Image.LANCZOS)
    solid = Image.new('RGBA', art.size, color + (255,))
    solid.putalpha(art.getchannel('A'))
    return solid


def centred_text(d, y, text, font, fill):
    l, t, r, b = font.getbbox(text)
    d.text(((W - (r - l)) / 2 - l, y), text, font=font, fill=fill)


def brand_screen(caption):
    """Yellow screen with Otis and a caption (boot + connecting share this layout)."""
    im = Image.new('RGB', (W, H), YELLOW)
    f = face(150)
    im.paste(f, ((W - f.width) // 2, 26), f)
    centred_text(ImageDraw.Draw(im), 194, caption, archivo(18, 700), BLACK)
    return im


def message_screen(title, lines, face_on_top=False):
    """Dark screen: big Archivo headline, Favorit body in muted grey."""
    im = Image.new('RGB', (W, H), BLACK)
    d = ImageDraw.Draw(im)
    x, y = 24, 44
    if face_on_top:
        f = face(56, WHITE)
        im.paste(f, (x, 26), f)
        y = 26 + f.height + 18
    d.text((x, y), title, font=archivo(34), fill=WHITE)
    y += 54
    for ln in lines:
        d.text((x, y), ln, font=favorit(17), fill=MUTED)
        y += 24
    return im


def setup_screen():
    im = Image.new('RGB', (W, H), BLACK)
    d = ImageDraw.Draw(im)
    f = face(56, WHITE)
    im.paste(f, (24, 22), f)
    d.text((24, 22 + f.height + 14), "Hi, I'm Otis", font=archivo(34), fill=WHITE)
    steps = [('1', ['Join the', f'"{SETUP_SSID}" Wi-Fi']),
             ('2', ['Follow the steps', 'that pop up'])]
    y = 22 + f.height + 66
    for num, lines in steps:
        d.text((24, y - 4), num, font=archivo(26), fill=WHITE)
        for k, ln in enumerate(lines):
            d.text((54, y + k * 21), ln, font=favorit(17), fill=WHITE)
        y += 52
    return im


def to_raw(im):
    """Big-endian RGB565, same as driver._rgb565 -- for splash.py's early boot frame."""
    px = im.convert('RGB').load()
    out = bytearray()
    for yy in range(H):
        for xx in range(W):
            r, g, b = px[xx, yy]
            out.append((r & 0xF8) | (g >> 5))
            out.append(((g << 3) & 0xE0) | (b >> 3))
    return bytes(out)


SCREENS = {
    # file name (kept so the code that loads them doesn't change) -> image
    'scud_splash_1.png': brand_screen('Waking up'),
    'success.png':       brand_screen('Connecting to One Radio'),
    'hello.png':         setup_screen(),
    'failure.png':       message_screen("That didn't work", ["Couldn't join that Wi-Fi.", 'Check the password and', 'try again.']),
    'goodbye.png':       message_screen('Goodbye', ['See you soon.'], face_on_top=True),
    'updating.png':      message_screen('Updating', ['Be right back.', "Please don't unplug me."], face_on_top=True),
}

if __name__ == '__main__':
    for name, im in SCREENS.items():
        im.save(A / name)
        print('wrote', A / name)
    (A / 'scud_splash_1.raw').write_bytes(to_raw(SCREENS['scud_splash_1.png']))
    print('wrote', A / 'scud_splash_1.raw')
    # Otis for the setup portal and the phone remote (black line art, transparent)
    portal = Image.new('RGBA', (400, 400), (0, 0, 0, 0))
    f = face(340)
    portal.paste(f, ((400 - f.width) // 2, (400 - f.height) // 2), f)
    portal.save(ROOT / 'portal-static/css/logo.png')
    print('wrote', ROOT / 'portal-static/css/logo.png')
    remote = Image.new('RGBA', (224, 224), (0, 0, 0, 0))
    f = face(200)
    remote.paste(f, ((224 - f.width) // 2, (224 - f.height) // 2), f)
    remote.save(ROOT / 'templates/assets/otis_face.png')
    print('wrote', ROOT / 'templates/assets/otis_face.png')
