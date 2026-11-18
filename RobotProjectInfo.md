# Robot project — Pi Zero: hardware and project info

Small battery-powered robot built on a Raspberry Pi Zero. This file covers the hardware,
the pin map, the I2C addresses and the constraints for the project.

## Hardware stack (bottom to top)

1. **UPS-Lite** (V1.2/V1.3 clone, MAX17040G fuel gauge, 1000 mAh LiPo). It mounts *under* the Pi and
   connects through 5 pogo pins that press on the header's solder joints. It has a hard power switch
   and can't power the Pi on or off from software.
2. **Raspberry Pi Zero** with a soldered stacking header.
3. **Keyestudio ReSpeaker 2-Mic Pi HAT** (Seeed clone: WM8960 codec, 2 mics, 3 APA102 LEDs,
   button). It plugs onto the stacking header.
4. Wired off the stacking header:
   - **DRV8833** dual H-bridge (blue module, pins labelled IN1–IN4 / OUT1–OUT4 / EEP / ULT)
     driving **2 small DC motors rated 3.3 V**.
   - **I2C OLED**, 128x64, SSD1306 or SH1106 (not yet confirmed which; see "Open questions").
   - **Sensors**: not chosen yet. They will go on the shared I2C bus and/or free GPIOs.

## Pin map (BCM numbering, physical pin in parentheses)

### Taken — do not reuse

| Function | GPIO (pin) |
|---|---|
| I2C SDA / SCL, shared bus | GPIO2 (3), GPIO3 (5) |
| UPS charger-present detect | GPIO4 (7) |
| ReSpeaker I2S audio | GPIO18 (12), GPIO19 (35), GPIO20 (38), GPIO21 (40) |
| ReSpeaker button | GPIO17 (11) |
| ReSpeaker APA102 LEDs (SPI0) | GPIO10 (19), GPIO11 (23) |

### Motors (DRV8833)

| DRV8833 | Pi | Notes |
|---|---|---|
| VCC (motor supply, VM) | 5V (pin 4) | |
| GND | GND (pin 6) | |
| EEP (nSLEEP) | 3.3V (pin 1) | Tied high, so the driver is always enabled |
| IN1 / IN2 → OUT1/OUT2 | GPIO5 (29) / GPIO6 (31) | Left motor (Motor A) |
| IN3 / IN4 → OUT3/OUT4 | GPIO12 (32) / GPIO13 (33) | Right motor (Motor B) |
| ULT (nFAULT) | not connected | Open-drain, active LOW. It can be wired to a free GPIO later |

If a motor turns the wrong way, swap its two wires or swap forward/backward in the config.
Left/right assignment still needs to be checked on the real robot.

### Free for sensors and other uses

GPIO16 (36), GPIO22 (15), GPIO23 (16), GPIO24 (18), GPIO25 (22), GPIO26 (37), GPIO27 (13).
GPIO12/13 are used by the right motor, so the ReSpeaker's Grove digital port can't be used.
GPIO14/15 (UART) are free if the serial console is disabled.

## I2C bus (bus 1)

| Address | Device |
|---|---|
| 0x1A | WM8960 audio codec (ReSpeaker) |
| 0x36 | MAX17040G fuel gauge (UPS) |
| 0x3C | OLED (possibly 0x3D) |

- Before adding a sensor, check its address against this table. Known conflicts: MPU6050 and DS3231 both use 0x68;
  BME280 uses 0x76 or 0x77.
- Sensors **must be powered from 3.3V**. If a module has pull-ups to 5V, those pull-ups put 5V on the Pi's I2C pins.
- 1-Wire defaults to GPIO4, which the UPS uses, so move it with `dtoverlay=w1-gpio,gpiopin=22`.
- The Pi has no ADC. Analog sensors need an ADS1115 (0x48).
- Bus speed can be 400 kHz (`dtparam=i2c_arm_baudrate=400000` in `/boot/firmware/config.txt`).

## Hard constraints

- **Motor voltage.** VM is 5V but the motors are rated 3.3V. **Cap PWM duty at 0.65.** Put
  this cap in one config constant and enforce it in the motor wrapper, never in calling code.
- **Power budget.** One 1000 mAh cell powers the Pi, the codec and both motors.
  Motor inrush or stall current can brown out the Pi and make it reboot. Ramp the speed up over about 200–300 ms
  instead of stepping straight to full, and avoid stalling the motors.
- **Shutdown.** Low battery has to trigger `sudo shutdown now` cleanly, because the UPS switch is a hard
  cut. Shut down at about 5% capacity or about 3.4V.
- **Audio noise.** Motor PWM can be heard in the mics. Don't trust audio captured while the motors run
  until this has been tested.
- **Fail safe.** Motors must stop on exit, on an exception and on SIGINT/SIGTERM. Use `try/finally`
  and signal handlers, plus a watchdog that stops the motors if the control loop stops sending commands.

## Software environment

- Raspberry Pi OS (Bookworm or later), Python 3. The Pi Zero has a single slow core, so keep
  things light: no heavy frameworks, no busy loops, and prefer `asyncio` or simple threads.
- Virtualenv with system packages, so the apt-installed gpiozero stays visible:
  ```bash
  python3 -m venv --system-site-packages ~/robot-env
  source ~/robot-env/bin/activate
  pip install luma.oled smbus2
  ```
- Libraries:
  - Motors: `gpiozero.Motor` (software PWM, so any GPIO works).
  - OLED: `luma.oled` (`ssd1306` or `sh1106` device class).
  - Fuel gauge: `smbus2`, reading the MAX17040 at 0x36:
    - VCELL register 0x02 (2 bytes, big-endian): `voltage = (raw >> 4) * 1.25 / 1000` V
    - SOC register 0x04 (2 bytes): `percent = msb + lsb / 256`
  - Charger present: read GPIO4 as an input (HIGH = external power connected, V1.3+; confirm on the hardware).
  - Audio: the ReSpeaker needs the WM8960 driver or overlay. It isn't installed yet.
  - LEDs: APA102 over SPI0 (`spidev`), with SPI enabled in raspi-config.
- Interfaces to enable in `raspi-config`: I2C, SPI.

## Suggested project layout

```
robot/
  config.py        # every pin, address, the duty cap and timing constant, in one place
  hw/
    motors.py      # wrapper around gpiozero Motor: duty cap, ramping, stop()
    battery.py     # MAX17040 reader + charger-present + low-battery shutdown
    display.py     # OLED helper (status screen: battery %, state, IP)
    sensors/       # one module per sensor
  main.py          # control loop
  tests/           # hardware smoke tests runnable one at a time
```

- Pins and addresses live **only** in `config.py`. Never hard-code a pin number anywhere else.
- Each `hw/` module should be importable and testable on its own, e.g. `python -m hw.motors` runs a
  short, safe test (low speed, about 1 s per direction, then stop).
- Code that needs hardware should fail clearly when the device is missing (for example, an I2C address
  that doesn't respond) instead of hanging.

## Bring-up checklist

- [ ] `sudo i2cdetect -y 1` shows 0x36 and 0x3C (and 0x1A once the codec driver is installed)
- [ ] Battery reader prints a sensible voltage and percentage
- [ ] OLED shows text (pick ssd1306 or sh1106)
- [ ] Each motor spins forward and backward at capped duty, and the direction is correct
- [ ] Both motors together on battery don't reboot the Pi
- [ ] Low-battery shutdown works
- [ ] ReSpeaker driver installed; record and playback work

## Open questions

- OLED controller: SSD1306 or SH1106? Does it use address 0x3C or 0x3D?
- Which sensors? Check each one's address and voltage against this file before wiring it.
- Which motor is left and which is right, and which way is forward?
- What the robot should actually do (remote control, autonomous, voice commands) still needs deciding.
