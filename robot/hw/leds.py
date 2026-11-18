"""The ReSpeaker HAT's 3 APA102 RGB LEDs, on SPI0.

Test on its own:
    python -m robot.hw.leds            # cycles through the colours
    python -m robot.hw.leds amber      # set one colour and leave it on (used by firstboot.sh)
"""

from robot import config

COLORS = {
    "off": (0, 0, 0),
    "idle": (0, 0, 0),
    "roam": (0, 40, 0),          # dim green
    "listening": (0, 0, 255),    # blue: talk now
    "thinking": (255, 140, 0),   # amber: recognising
    "ok": (0, 255, 0),
    "error": (255, 0, 0),
    "offline": (60, 0, 60),      # purple: no broker
    "purple": (120, 0, 120),
    "amber": (255, 140, 0),
    "green": (0, 255, 0),
    "red": (255, 0, 0),
}


class Leds:
    def __init__(self):
        import spidev

        self._spi = spidev.SpiDev()
        self._spi.open(*config.LED_SPI)
        self._spi.max_speed_hz = 8_000_000

    def color(self, rgb, count=config.LED_COUNT):
        if isinstance(rgb, str):
            rgb = COLORS[rgb]
        r, g, b = rgb
        frame = [0x00] * 4
        for i in range(config.LED_COUNT):
            if i < count:
                frame += [0xE0 | config.LED_BRIGHTNESS, b, g, r]
            else:
                frame += [0xE0, 0, 0, 0]
        frame += [0xFF] * 4
        self._spi.xfer2(frame)

    def close(self):
        self.color("off")
        self._spi.close()


if __name__ == "__main__":
    import sys
    import time

    leds = Leds()
    if len(sys.argv) > 1:              # set a colour and leave it on
        leds.color(sys.argv[1])
        sys.exit()
    for name in ("listening", "thinking", "ok", "error", "roam"):
        print(name)
        leds.color(name)
        time.sleep(1)
    leds.close()
