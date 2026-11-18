"""Every pin, address, limit and timing constant lives here, and nowhere else.

Per-robot settings (robot name, broker address, passwords, speech language) are
not in this file: they come from robot.conf at the project root, so two robots
can run exactly the same code. Copy robot.conf.example to robot.conf to start.
"""

import configparser
from pathlib import Path

# ---------------------------------------------------------------------------
# Pins (BCM numbering). Physical pin numbers in comments.
# ---------------------------------------------------------------------------
# DRV8833. EEP (nSLEEP) is tied to 3.3V, so the driver is always enabled.
LEFT_MOTOR_PINS = (5, 6)      # IN1 (29), IN2 (31) -> OUT1/OUT2, motor A
RIGHT_MOTOR_PINS = (12, 13)   # IN3 (32), IN4 (33) -> OUT3/OUT4, motor B

# Not checked on the real robot yet. Fix direction/side here, never in calling code.
SWAP_LEFT_RIGHT = False
INVERT_LEFT = False
INVERT_RIGHT = False

BUTTON_PIN = 17               # ReSpeaker button (11), active low
CHARGER_PIN = 4               # UPS-Lite charger-present (7), HIGH = plugged in

# Taken by other hardware, listed so nobody reuses them:
#   2, 3   I2C bus (OLED, fuel gauge, WM8960 codec)
#   18-21  ReSpeaker I2S audio
#   10, 11 ReSpeaker APA102 LEDs (SPI0)
# Free (future cliff / collision sensors): 16, 22, 23, 24, 25, 26, 27 (+ 14, 15).

# ---------------------------------------------------------------------------
# I2C / SPI
# ---------------------------------------------------------------------------
I2C_BUS = 1
FUEL_GAUGE_ADDR = 0x36        # MAX17040G on the UPS-Lite
OLED_ADDR = 0x3C              # SH1106 OLED; try 0x3D if the screen stays black
LED_SPI = (0, 0)              # bus, device
LED_COUNT = 3
LED_BRIGHTNESS = 10           # 0..31

# ---------------------------------------------------------------------------
# Motors
# ---------------------------------------------------------------------------
# Motors are rated 3.3V but VM is 5V: never exceed this duty cycle.
# Enforced inside hw/motors.py, callers use speeds from -1.0 to 1.0.
MAX_DUTY = 0.65
PWM_FREQUENCY = 100           # Hz, software PWM
RAMP_TIME = 0.25              # s from stop to full speed (brownout protection)
MOTOR_TICK = 0.02             # s between ramp steps

# ---------------------------------------------------------------------------
# Roaming (speeds are fractions of MAX_DUTY)
# ---------------------------------------------------------------------------
ROAM_ON_START = True              # start roaming as soon as the program starts
ROAM_SPEED = 0.8
TURN_SPEED = 0.7
ROAM_FORWARD_TIME = (1.5, 4.0)    # s, random within range
ROAM_PAUSE_TIME = (0.3, 1.2)
ROAM_TURN_TIME = (0.3, 1.0)
ROAM_REVERSE_CHANCE = 0.15
ROAM_REVERSE_TIME = (0.4, 0.8)
SPIN_TIME = 1.6                   # s for the "spin" command (about a full turn, tune it)

# ---------------------------------------------------------------------------
# Battery
# ---------------------------------------------------------------------------
BATTERY_CHECK_EVERY = 10      # s
BATTERY_LOW_PERCENT = 15      # stop roaming below this
BATTERY_SHUTDOWN_PERCENT = 5  # clean shutdown below this (or below the voltage)
BATTERY_SHUTDOWN_VOLTS = 3.4
BATTERY_LOW_READINGS = 3      # consecutive low readings before acting

# ---------------------------------------------------------------------------
# Voice
# ---------------------------------------------------------------------------
TAP_TIME = 0.4                # s: shorter press = toggle roaming, longer = talk
MAX_RECORD_TIME = 6           # s
RECORD_TAIL = 0.6             # s, keep recording after the button is released
AUDIO_RATE = 16000
AUDIO_DEVICE = ""             # "" = find the ReSpeaker automatically

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
STATE_EVERY = 5               # s between state messages on MQTT


# ---------------------------------------------------------------------------
# Per-robot settings from robot.conf
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
CONF_FILE = ROOT / "robot.conf"

_conf = configparser.ConfigParser()
_conf.read_dict({
    "robot": {"name": "mikubot"},
    "mqtt": {"host": "localhost", "port": "1883", "tls": "false",
             "user": "", "password": "", "ca_file": ""},
    "voice": {"language": "en-US"},
    "devices": {},
})
_conf.read(CONF_FILE)

ROBOT_NAME = _conf["robot"]["name"]
MQTT_HOST = _conf["mqtt"]["host"]
MQTT_PORT = _conf["mqtt"].getint("port")
MQTT_TLS = _conf["mqtt"].getboolean("tls")
MQTT_USER = _conf["mqtt"]["user"]
MQTT_PASSWORD = _conf["mqtt"]["password"]
MQTT_CA_FILE = _conf["mqtt"]["ca_file"]
SPEECH_LANGUAGE = _conf["voice"]["language"]

# Spoken name -> MQTT topic prefix. "<prefix>/set" gets ON / OFF / TOGGLE.
DEVICES = dict(_conf["devices"]) or {"light": "home/robot/light"}

# This robot's own topics.
TOPIC = f"robot/{ROBOT_NAME}"
