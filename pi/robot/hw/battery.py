"""UPS-Lite battery: MAX17040G fuel gauge over I2C, plus the charger-present pin.

Test on its own:
    python -m robot.hw.battery
"""

import logging

from robot import config

log = logging.getLogger(__name__)

VCELL_REG = 0x02
SOC_REG = 0x04


class BatteryMissing(RuntimeError):
    pass


class Battery:
    def __init__(self):
        from smbus2 import SMBus

        self._bus = SMBus(config.I2C_BUS)
        try:
            self._read(VCELL_REG)
        except OSError as e:
            self._bus.close()
            raise BatteryMissing(
                f"No fuel gauge at 0x{config.FUEL_GAUGE_ADDR:02X} on I2C bus {config.I2C_BUS} "
                f"({e}). Is I2C enabled and the UPS-Lite pressed onto the header?") from e

        self._charger = None
        try:
            from gpiozero import DigitalInputDevice
            self._charger = DigitalInputDevice(config.CHARGER_PIN, pull_up=False)
        except Exception as e:  # pin busy, no GPIO...: battery reading still works
            log.warning("Charger-present pin unavailable: %s", e)

    def _read(self, reg):
        msb, lsb = self._bus.read_i2c_block_data(config.FUEL_GAUGE_ADDR, reg, 2)
        return msb, lsb

    @property
    def volts(self):
        msb, lsb = self._read(VCELL_REG)
        return (((msb << 8) | lsb) >> 4) * 1.25 / 1000

    @property
    def percent(self):
        msb, lsb = self._read(SOC_REG)
        return min(100.0, msb + lsb / 256)

    @property
    def charging(self):
        """True when external power is plugged in (None if the pin isn't readable)."""
        return None if self._charger is None else bool(self._charger.value)

    def close(self):
        if self._charger is not None:
            self._charger.close()
        self._bus.close()


if __name__ == "__main__":
    b = Battery()
    try:
        print(f"{b.volts:.3f} V, {b.percent:.1f} %, charger plugged in: {b.charging}")
    finally:
        b.close()
