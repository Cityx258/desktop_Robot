# Desktop robot: setup guide

A small robot on a Pi Zero that roams around and takes voice commands. Say
"turn on the light" and a red LED on an ESP32 turns on, through an MQTT broker.

```
voice -> ReSpeaker HAT -> Pi Zero robot (pi/robot/) -> MQTT broker (laptop) -> ESP32 -> LED
```

The broker runs on a laptop on the local network instead of online, because school
Wi-Fi blocks MQTT. Going online later only means changing `[mqtt]` in `robot.conf`.

All devices (broker laptop, Pi, ESP32) must be on the **same Wi-Fi**, and it must be
**2.4 GHz** (neither the ESP32 nor the Pi Zero W can use 5 GHz). On a Pixel hotspot,
turn on "Extend compatibility". If the school Wi-Fi blocks devices from talking to
each other, use the hotspot.

## What's in this folder

| Folder | Runs on | What's in it |
|---|---|---|
| `pi/` | Pi | Everything the robot needs. Copied as-is to `~/desktop_Robot` on the Pi |
| `pi/robot/` | Pi | The robot program: roaming, voice commands, battery, screen |
| `pi/setup_pi.sh`, `pi/requirements.txt` | Pi | One-time install for the robot |
| `pi/robot.conf.example` | Pi | Per-robot settings (name, broker). Copied to `robot.conf` (not committed) |
| `broker/` | Laptop | `broker.sh` starts/stops the MQTT broker, with `mosquitto-demo.conf` |
| `esp32_light/` | ESP32 | Arduino sketch for the lamp. `set_wifi.sh` writes the Wi-Fi into `config.h` |
| `docs/` | | `RobotProjectInfo.md` (hardware, pin map), `BOM.ods`, `wiring.svg` (LED), `cahierDesCharges.pdf` (old plan, outdated) |
| `old/` | | Earlier approaches, no longer used: SD card prep + USB networking, the first voice script |

Do the parts in order: each one tests itself before the next.

---

## Part 1: Broker on the Linux computer

```bash
sudo apt install mosquitto mosquitto-clients
sudo systemctl disable --now mosquitto     # stop the built-in one; we run our own config
cd desktop_Robot
broker/broker.sh start
```

It prints `Use MQTT_HOST=<IP>`. **Write that IP down**, the ESP32 and the Pi need it.

If the firewall is on (`sudo ufw status` says active), open the port:

```bash
sudo ufw allow 1883/tcp
```

Other commands: `broker/broker.sh status`, `broker/broker.sh log` (watch messages live), `broker/broker.sh stop`.

---

## Part 2: ESP32 + red LED

### Wiring (USB unplugged)

See `docs/wiring.svg`.

```
GPIO 23 -> 220 Ω resistor -> LED long leg (+)
GND     -> LED short leg (-)        (short leg = flat side of the LED rim)
```

The pin may be labelled `D23`, `IO23` or `23`. Find it by its label; pin order
differs between boards. Any GND pin works. Never connect the LED without the resistor.

### Arduino IDE (one time)

1. **ESP32 support:** Tools → Board → Boards Manager → search "esp32" → install **esp32 by Espressif**.
2. **MQTT library:** Tools → Manage Libraries → search "PubSubClient" → install **PubSubClient by Nick O'Leary**.
3. **USB permission on Linux:** run this, then log out and back in:
   ```bash
   sudo usermod -aG dialout $USER
   ```

### Configure and upload

1. Fill in the Wi-Fi (asks for name and password; the password stays hidden):
   ```bash
   esp32_light/set_wifi.sh
   ```
2. It creates `esp32_light/config.h` from `config.example.h` (`config.h` holds your Wi-Fi
   password and isn't committed).
   Open `esp32_light/esp32_light.ino` in the Arduino IDE. In the **config.h** tab,
   set `MQTT_HOST` to the broker IP from Part 1. Save.
3. Tools → Board → esp32 → **ESP32 Dev Module**. Tools → Port → `/dev/ttyUSB0` (or `/dev/ttyACM0`).
4. Click Upload.
   - Fails with "Unable to verify flash chip connection": Tools → **Upload Speed → 115200**, upload again.
   - Stuck on `Connecting......`: hold the **BOOT** button until the upload starts.

### Test

Open Tools → Serial Monitor at **115200 baud** and press the board's **EN/RST** button. You should see:

```
Connecting to Wi-Fi <name> (attempt 1)...
Wi-Fi connected, ESP32 IP: ..., signal -55 dBm
Connecting to broker <IP>:1883... connected
```

Then, on the Linux computer:

```bash
mosquitto_pub -h localhost -t home/robot/light/set -m ON
mosquitto_pub -h localhost -t home/robot/light/set -m OFF
```

The LED turns on and off. If it never lights, the LED is backwards: flip it.

**Close the Serial Monitor** when you're done, or the next upload can't use the USB port.

---

## Part 3: The robot (Pi Zero)

Hardware and pins: see `docs/RobotProjectInfo.md`. All pins and limits are in `pi/robot/config.py`.
The robot runs on a **Pi Zero 2 W** (the first Pi Zero W's I2C pins are damaged).

### SD card and network

Flash **Raspberry Pi OS Lite (32-bit)** with Raspberry Pi Imager. In the customisation:
hostname `mikuBot`, user `mikubot`, a password, SSH on, and the Wi-Fi.

The Pi needs two Wi-Fi networks: the **home Wi-Fi** (same network as the PC, so the PC can
ssh to it) and the **phone hotspot** (for demos away from home). NetworkManager picks
whichever is in range; give the home one a higher priority on the Pi:

```bash
sudo nmcli connection modify <home-wifi> connection.autoconnect-priority 10
```

A hotspot hides the Pi from the PC (the phone's NAT), and so can a second router that makes
its own sub-network: from the PC, ssh only works when the Pi is on the PC's own network.

Find the Pi's IP from the PC: `nmap -sn 192.168.2.0/24 | grep -i -A2 miku`.

### Install (on the Pi, over ssh)

```bash
ssh mikubot@<pi-ip>
sudo apt install -y git
git clone https://github.com/Cityx258/desktop_Robot.git ~/desktop_Robot
cd ~/desktop_Robot/pi
./setup_pi.sh                    # 10-20 min on a Pi Zero; reboot + run again if it says so
nano robot.conf                  # [mqtt] host = the broker's IP
sudo systemctl enable --now robot   # start now and at every boot
```

**Updates:** at every boot, `robot-update.service` runs `git pull` before the robot starts,
so pushing to GitHub is enough: reboot the Pi (or `sudo systemctl start robot-update &&
sudo systemctl restart robot`). Without internet it keeps the code it has. New apt or pip
packages still need `./setup_pi.sh` again.

### Test each part

```bash
sudo i2cdetect -y 1                          # expect 1a (codec), 36 (battery), 3c (OLED)
.venv/bin/python -m robot.hw.battery         # voltage and %
.venv/bin/python -m robot.hw.display         # the face, every expression
.venv/bin/python -m robot.hw.leds            # LEDs cycle colours
.venv/bin/python -m robot.hw.motors          # each motor both ways
arecord -D plughw:CARD=wm8960soundcard,DEV=0 -f S16_LE -r 16000 -d 3 t.wav && aplay t.wav
```

A motor going the wrong way, or left/right swapped: fix `SWAP_LEFT_RIGHT` / `INVERT_*`
in `pi/robot/config.py`.

### Run

```bash
.venv/bin/python -m robot.main               # by hand (Ctrl+C stops, motors off)
sudo systemctl enable --now robot            # or: start at every boot
journalctl -fu robot                         # logs of the service
```

It starts **roaming** right away (`ROAM_ON_START` in `pi/robot/config.py`). Then:

| Do | Result |
|---|---|
| Tap the ReSpeaker button | Start / stop roaming (LEDs dim green while roaming) |
| Hold the button, talk, release | Voice command. Blue = listening, amber = thinking, green = done, red = not understood |
| "turn on the light" / "turn the light off" | Sent to the ESP32 lamp |
| "start roaming" / "stop" / "spin" | Robot commands |
| `mosquitto_pub -h localhost -t robot/mikubot/cmd -m roam` | Same commands from the laptop (`stop`, `spin`) |
| `mosquitto_sub -h localhost -t 'robot/#' -v` | Watch the robot's state, status and what it heard |

The motors stop while you hold the button, so their noise doesn't end up in the recording.
Speech recognition uses Google's service, so **the Pi needs internet** (the hotspot has it).
The OLED shows the robot's face: it blinks, looks toward its turns while roaming, opens
its eyes wide while listening, looks up while thinking, smiles when a command worked, looks
confused when it didn't, and gets sleepy on low battery. Preview on a computer:
`cd pi && python -m robot.face` (writes `face_preview.png`).

Purple LEDs = no broker: the robot keeps roaming and obeying "roam/stop/spin" anyway.

Motor speed-ups ramp over 0.25 s so the single battery doesn't brown out the Pi.
Below 15 % battery the robot stops roaming; below 5 % (or 3.4 V) it shuts the Pi down
cleanly (the UPS switch is a hard cut). Thresholds are in `pi/robot/config.py`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| ESP32 prints `failed (state -2)` | Broker not reachable: check `broker/broker.sh status`, the IP in `config.h`, the firewall (Part 1) |
| ESP32 stuck on Wi-Fi dots | Wrong Wi-Fi name/password, or a 5 GHz network. It restarts itself after 3 tries |
| `broker/broker.sh start` says port 1883 is taken | `sudo systemctl disable --now mosquitto` |
| Upload can't open the port | Close the Serial Monitor; check the `dialout` group (Part 2) |
| Robot: red LEDs after talking | Not understood: it logs what it heard (`journalctl -fu robot`) |
| The IP changed (new network) | Update `MQTT_HOST` in `config.h`, re-upload; update `host` in `robot.conf` on the Pi |
| Robot: `ReSpeaker not found` | Check `dtoverlay=wm8960-soundcard` in `/boot/firmware/config.txt`, reboot, `arecord -l` |
| Robot: recording is silent | Run `./setup_pi.sh` again on the Pi (sets the mic levels), or `alsamixer -c wm8960soundcard` |
| Robot: Pi reboots when motors start | Brownout: lower `ROAM_SPEED` or raise `RAMP_TIME` in `pi/robot/config.py` |
| Robot: screen says `no broker` | Wrong `host` in `robot.conf`, broker stopped, or not on the same Wi-Fi |

## MQTT topics

| Topic | Who sends | Values |
|---|---|---|
| `home/robot/light/set` | Robot (voice) | `ON`, `OFF`, `TOGGLE` |
| `home/robot/light/state` | ESP32 | `ON`, `OFF` |
| `home/robot/status` | ESP32 | `online`, `offline` (offline = ESP32 lost power or Wi-Fi) |
| `robot/mikubot/cmd` | Anyone | `roam`, `stop`, `spin` |
| `robot/mikubot/state` | Robot, every 5 s | JSON: mode, battery, rssi, last phrase heard... |
| `robot/mikubot/status` | Robot | `online`, `offline` (Last Will) |
| `robot/mikubot/heard` | Robot | Every phrase it recognised, as text |

`mikubot` is the `name` in `robot.conf`. More voice-controlled devices: add a line under
`[devices]` in `robot.conf` (spoken name = topic prefix).
