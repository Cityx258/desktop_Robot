"""128x64 SH1106 I2C OLED: shows the robot's face (robot/face.py).

Talks to the screen directly with smbus2 (no luma.oled: its dependencies can't be
installed on a Pi Zero). Pictures are Pillow images, mode "1", 128x64.

The Display class runs in its own thread so drawing never slows the main loop: call
set_face() whenever you like, the screen is only redrawn when the picture changes.

Test on its own:
    python -m robot.hw.display                   # cycles through every expression
    python -m robot.hw.display --text Hello Pi   # shows text and leaves it on screen
"""

import logging
import random
import threading
import time

from robot import config

log = logging.getLogger(__name__)

W, H = 128, 64
BLINK_EVERY = (2.5, 6.0)       # s between blinks
BLINK_LENGTH = 0.15            # s
COLUMN_OFFSET = 2              # SH1106 RAM is 132 wide, the 128 visible columns start at 2


class SH1106:
    """Bare SH1106 driver over I2C."""

    def __init__(self):
        from smbus2 import SMBus

        self._bus = SMBus(config.I2C_BUS)
        try:
            self._command(
                0xAE,               # display off
                0xD5, 0x80,         # clock
                0xA8, 0x3F,         # multiplex: 64 rows
                0xD3, 0x00,         # no vertical offset
                0x40,               # start line 0
                0xAD, 0x8B,         # DC-DC on
                0xA1,               # mirror horizontally (screen the right way round)
                0xC8,               # scan rows top to bottom
                0xDA, 0x12,         # COM pins layout
                0x81, 0xCF,         # contrast
                0xD9, 0x22,         # pre-charge
                0xDB, 0x40,         # VCOM level
                0xA4,               # show RAM content
                0xA6,               # not inverted
            )
        except OSError as e:
            self._bus.close()
            raise RuntimeError(f"No OLED at 0x{config.OLED_ADDR:02X} on I2C bus {config.I2C_BUS} ({e})") from e
        self.show(None)
        self._command(0xAF)         # display on

    def _command(self, *cmds):
        for c in cmds:
            self._bus.write_byte_data(config.OLED_ADDR, 0x00, c)

    def show(self, image):
        """Send a 128x64 mode-"1" Pillow image (None = blank)."""
        px = image.load() if image is not None else None
        for page in range(H // 8):
            self._command(0xB0 + page, COLUMN_OFFSET & 0x0F, 0x10 | (COLUMN_OFFSET >> 4))
            row = bytearray(W)
            if px is not None:
                y0 = page * 8
                for x in range(W):
                    b = 0
                    for bit in range(8):
                        if px[x, y0 + bit]:
                            b |= 1 << bit
                    row[x] = b
            for i in range(0, W, 32):  # I2C block writes are limited to 32 bytes
                self._bus.write_i2c_block_data(config.OLED_ADDR, 0x40, list(row[i:i + 32]))

    def off(self):
        self._command(0xAE)

    def close(self):
        self._bus.close()


def text_image(lines):
    from PIL import Image, ImageDraw

    img = Image.new("1", (W, H), 0)
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines[:5]):
        d.text((0, i * 12), str(line)[:21], fill=1)
    return img


class Display:
    def __init__(self):
        from robot import face

        self._face = face
        self._oled = SH1106()
        self._expression, self._look, self._text = "normal", 0, None
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="display", daemon=True)
        self._thread.start()

    def set_face(self, expression, look=0):
        """expression: one of face.EXPRESSIONS. look: -1 left, 0 ahead, 1 right."""
        self._expression, self._look = expression, look

    def show_text(self, lines):
        """Replace the face with up to 5 lines of text (e.g. the low-battery message)."""
        self._text = tuple(str(l)[:21] for l in lines[:5])

    def _loop(self):
        next_blink = time.monotonic() + random.uniform(*BLINK_EVERY)
        last = None
        while self._running:
            now = time.monotonic()
            blink = now >= next_blink
            if now >= next_blink + BLINK_LENGTH:
                next_blink = now + random.uniform(*BLINK_EVERY)
            key = (self._text,) if self._text else (self._expression, self._look, blink)
            if key != last:
                last = key
                try:
                    self._oled.show(text_image(self._text) if self._text
                                    else self._face.render(self._expression, self._look, blink))
                except OSError as e:
                    log.warning("OLED write failed: %s", e)
            time.sleep(0.05)

    def close(self):
        self._running = False
        self._thread.join(timeout=1)
        if not self._text:          # keep a last message (e.g. "battery empty") on screen
            try:
                self._oled.off()
            except OSError:
                pass
        self._oled.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 2 and sys.argv[1] == "--text":
        oled = SH1106()
        oled.show(text_image(sys.argv[2:]))
        oled.close()                # the screen keeps the picture after we exit
        sys.exit()

    from robot import face

    d = Display()
    try:
        for e in face.EXPRESSIONS:
            print(e)
            d.set_face(e)
            time.sleep(2)
        for look in (-1, 1, 0):
            d.set_face("normal", look)
            time.sleep(1)
    finally:
        d.close()
