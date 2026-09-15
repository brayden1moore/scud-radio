import time
import lcdconfig


class LCD_2inch(lcdconfig.RaspberryPi):
    """ST7789 240x320 driver.

    Changes vs. the Waveshare original:
      * SetWindows computes both bytes of the end address from (end - 1).
        The original took the high byte from `end` and the low byte from
        `end - 1`, which disagree whenever `end` is a multiple of 256.
        Full-screen writes (320/240) never hit that case; partial windows do.
      * Window coordinates are clamped to the panel and validated, so a bad
        window raises in Python instead of silently leaving the controller
        pointing at the previous region.
      * MADCTL is written once, in Init(). Draw calls no longer change
        orientation as a side effect.
      * X_OFFSET / Y_OFFSET let you compensate for panels whose glass does
        not start at GRAM (0, 0).
      * 120 ms delay after sleep-out, as the datasheet requires.
    """

    # Native controller geometry, before rotation.
    PANEL_WIDTH = 240
    PANEL_HEIGHT = 320

    # MADCTL values. Bit 3 (0x08) selects BGR; OR it in if red and blue
    # are swapped on your board. Bit 4 (0x10, ML) only affects panel refresh
    # order, not memory addressing -- 0x70 is kept for rotation 90 to match
    # the value the Waveshare code used.
    MADCTL = {
        0: 0x00,
        90: 0x70,
        180: 0xC0,
        270: 0xA0,
    }

    def __init__(self, *args, rotation=90, x_offset=0, y_offset=0,
                 invert=True, bgr=False, **kwargs):
        super().__init__(*args, **kwargs)
        if rotation not in self.MADCTL:
            raise ValueError("rotation must be one of 0, 90, 180, 270")
        self.rotation = rotation
        self.invert = invert
        self.bgr = bgr

        if rotation in (90, 270):
            self.width = self.PANEL_HEIGHT     # 320
            self.height = self.PANEL_WIDTH     # 240
            self.X_OFFSET = y_offset
            self.Y_OFFSET = x_offset
        else:
            self.width = self.PANEL_WIDTH      # 240
            self.height = self.PANEL_HEIGHT    # 320
            self.X_OFFSET = x_offset
            self.Y_OFFSET = y_offset

    # ------------------------------------------------------------------
    # Low-level
    # ------------------------------------------------------------------

    def command(self, cmd):
        self.digital_write(self.DC_PIN, False)
        self.spi_writebyte([cmd])

    def data(self, val):
        self.digital_write(self.DC_PIN, True)
        self.spi_writebyte([val])

    def data_bytes(self, values):
        self.digital_write(self.DC_PIN, True)
        for i in range(0, len(values), 4096):
            self.spi_writebyte(values[i:i + 4096])

    def reset(self):
        self.digital_write(self.RST_PIN, True)
        time.sleep(0.01)
        self.digital_write(self.RST_PIN, False)
        time.sleep(0.01)
        self.digital_write(self.RST_PIN, True)
        time.sleep(0.12)

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def Init(self):
        self.module_init()
        self.reset()

        madctl = self.MADCTL[self.rotation]
        if self.bgr:
            madctl |= 0x08
        self.command(0x36)
        self.data(madctl)

        self.command(0x3A)      # COLMOD: 16 bit/pixel
        self.data(0x05)

        self.command(0x21 if self.invert else 0x20)

        self.command(0xB2)      # PORCTRL
        for v in (0x0C, 0x0C, 0x00, 0x33, 0x33):
            self.data(v)

        self.command(0xB7)      # GCTRL
        self.data(0x35)

        self.command(0xBB)      # VCOMS
        self.data(0x1F)

        self.command(0xC0)      # LCMCTRL
        self.data(0x2C)

        self.command(0xC2)      # VDVVRHEN
        self.data(0x01)

        self.command(0xC3)      # VRHS
        self.data(0x12)

        self.command(0xC4)      # VDVS
        self.data(0x20)

        self.command(0xC6)      # FRCTRL2
        self.data(0x0F)

        self.command(0xD0)      # PWCTRL1
        self.data(0xA4)
        self.data(0xA1)

        self.command(0xE0)      # PVGAMCTRL
        for v in (0xD0, 0x08, 0x11, 0x08, 0x0C, 0x15, 0x39,
                  0x33, 0x50, 0x36, 0x13, 0x14, 0x29, 0x2D):
            self.data(v)

        self.command(0xE1)      # NVGAMCTRL
        for v in (0xD0, 0x08, 0x10, 0x08, 0x06, 0x06, 0x39,
                  0x44, 0x51, 0x0B, 0x16, 0x14, 0x2F, 0x31):
            self.data(v)

        self.command(0x11)      # SLPOUT
        time.sleep(0.12)        # datasheet-mandated; the original omitted it

        self.command(0x29)      # DISPON
        time.sleep(0.02)

        self.SetWindows(0, 0, self.width, self.height)

    # ------------------------------------------------------------------
    # Addressing
    # ------------------------------------------------------------------

    def SetWindows(self, Xstart, Ystart, Xend, Yend):
        """Set the write window. Xend/Yend are EXCLUSIVE.

        Both bytes of each end address are derived from (end - 1); mixing
        the two is what breaks partial windows on the original driver.
        """
        Xstart = max(0, int(Xstart))
        Ystart = max(0, int(Ystart))
        Xend = min(self.width, int(Xend))
        Yend = min(self.height, int(Yend))

        if Xend <= Xstart or Yend <= Ystart:
            raise ValueError(
                "empty window: x[%d,%d) y[%d,%d)" % (Xstart, Xend, Ystart, Yend)
            )

        x0 = Xstart + self.X_OFFSET
        x1 = Xend - 1 + self.X_OFFSET
        y0 = Ystart + self.Y_OFFSET
        y1 = Yend - 1 + self.Y_OFFSET

        self.command(0x2A)              # CASET
        self.data(x0 >> 8)
        self.data(x0 & 0xFF)
        self.data(x1 >> 8)
        self.data(x1 & 0xFF)

        self.command(0x2B)              # RASET
        self.data(y0 >> 8)
        self.data(y0 & 0xFF)
        self.data(y1 >> 8)
        self.data(y1 & 0xFF)

        self.command(0x2C)              # RAMWR

    # ------------------------------------------------------------------
    # Pixel conversion
    # ------------------------------------------------------------------

    def _rgb565(self, image):
        """PIL image -> flat list of big-endian RGB565 bytes."""
        if image.mode != 'RGB':
            image = image.convert('RGB')
        img = self.np.asarray(image, dtype=self.np.uint8)
        h, w = img.shape[0], img.shape[1]
        pix = self.np.empty((h, w, 2), dtype=self.np.uint8)
        pix[..., 0] = (img[..., 0] & 0xF8) | (img[..., 1] >> 5)
        pix[..., 1] = ((img[..., 1] << 3) & 0xE0) | (img[..., 2] >> 3)
        return pix.reshape(-1).tolist()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def ShowImage(self, Image, Xstart=0, Ystart=0):
        """Blit a full-size image. Orientation comes from Init(), not from
        the image dimensions."""
        if Image.size != (self.width, self.height):
            raise ValueError(
                "image is %dx%d, display is %dx%d -- rotate the image or "
                "re-Init with a different rotation"
                % (Image.width, Image.height, self.width, self.height)
            )
        self.SetWindows(0, 0, self.width, self.height)
        self.data_bytes(self._rgb565(Image))

    def ShowWindow(self, image, x0, y0):
        """Blit `image` with its top-left corner at (x0, y0)."""
        if x0 < 0 or y0 < 0:
            raise ValueError("negative origin: clip the image first")
        if x0 + image.width > self.width or y0 + image.height > self.height:
            raise ValueError(
                "window (%d,%d)+%dx%d does not fit in %dx%d"
                % (x0, y0, image.width, image.height, self.width, self.height)
            )
        self.SetWindows(x0, y0, x0 + image.width, y0 + image.height)
        self.data_bytes(self._rgb565(image))

    def fill(self, x0, y0, w, h, color=(0, 0, 0)):
        """Solid-fill a rectangle without building a PIL image."""
        r, g, b = color
        hi = (r & 0xF8) | (g >> 5)
        lo = ((g << 3) & 0xE0) | (b >> 3)
        self.SetWindows(x0, y0, x0 + w, y0 + h)
        self.data_bytes([hi, lo] * (w * h))

    def clear(self, color=(255, 255, 255)):
        self.fill(0, 0, self.width, self.height, color)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def test_edges(self):
        """Black screen with a 2px white frame and a white 8px square in the
        top-left corner.

        Read it like this:
          * A missing strip on one edge means you need an X_OFFSET or
            Y_OFFSET on that axis.
          * The corner square appearing anywhere other than top-left means
            the MADCTL rotation is wrong (or you are rotating in software
            and shouldn't be).
          * A frame that is present but wrapped or torn means the window
            arithmetic is still off.
        """
        self.fill(0, 0, self.width, self.height, (0, 0, 0))
        self.fill(0, 0, self.width, 2, (255, 255, 255))
        self.fill(0, self.height - 2, self.width, 2, (255, 255, 255))
        self.fill(0, 0, 2, self.height, (255, 255, 255))
        self.fill(self.width - 2, 0, 2, self.height, (255, 255, 255))
        self.fill(0, 0, 8, 8, (255, 255, 255))

    def test_boundary(self):
        """Walk a 16px bar across the full width, one pixel at a time.

        This is the case the original driver got wrong: it exercises every
        window end value, including the multiples of 256 that produced an
        out-of-range CASET.
        """
        for x in range(0, self.width - 16):
            self.fill(x, self.height // 2 - 8, 16, 16, (255, 0, 0))
            if x > 0:
                self.fill(x - 1, self.height // 2 - 8, 1, 16, (0, 0, 0))
            time.sleep(0.005)