#!/bin/bash
# One-time setup of the robot on the Pi Zero (Raspberry Pi OS Lite, trixie).
# Run it from the project folder on the Pi:   ./setup_pi.sh
# Safe to run again: every step checks before changing anything.
# (firstboot.sh runs it as root with ROBOT_USER set, on the Pi's first boot.)
set -e
cd "$(dirname "$0")"
DIR=$(pwd)
RUN_USER=${ROBOT_USER:-$USER}
CFG=/boot/firmware/config.txt

echo "== Packages (apt, so nothing has to compile on the Pi Zero)"
sudo apt-get update
sudo apt-get install -y python3-venv python3-gpiozero python3-lgpio python3-paho-mqtt \
  python3-smbus2 python3-spidev python3-pil alsa-utils flac i2c-tools

echo "== Python environment (.venv, sees the apt packages)"
[ -d .venv ] || python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt

echo "== Interfaces in $CFG"
NEED_REBOOT=0
for line in dtparam=i2c_arm=on dtparam=i2c_arm_baudrate=400000 dtparam=spi=on dtoverlay=wm8960-soundcard \
            gpio=5,6,12,13=op,dl; do   # last one: motor pins low from power-on
  if ! grep -qx "$line" "$CFG"; then
    echo "$line" | sudo tee -a "$CFG" >/dev/null
    echo "  added $line"; NEED_REBOOT=1
  fi
done

echo "== Robot settings"
if [ ! -f robot.conf ]; then
  cp robot.conf.example robot.conf
  echo "  created robot.conf: set the broker IP in it"
fi
chmod 600 robot.conf

echo "== Allow the robot to shut the Pi down on low battery"
RULE="$RUN_USER ALL=(root) NOPASSWD: /usr/sbin/shutdown"
echo "$RULE" | sudo tee /etc/sudoers.d/robot-shutdown >/dev/null
sudo chmod 440 /etc/sudoers.d/robot-shutdown
sudo visudo -cf /etc/sudoers.d/robot-shutdown >/dev/null

echo "== Microphone levels"
CARD=$(arecord -l 2>/dev/null | grep -i wm8960 | head -1 | sed -E 's/^card ([0-9]+).*/\1/')
if [ -n "$CARD" ]; then
  m() { amixer -q -c "$CARD" sset "$@" 2>/dev/null || echo "  (no mixer control '$1', skipped)"; }
  m 'Left Input Mixer Boost' on;  m 'Right Input Mixer Boost' on
  m 'Left Boost Mixer LINPUT1' on; m 'Right Boost Mixer RINPUT1' on
  m 'Left Input Boost Mixer LINPUT1' 2; m 'Right Input Boost Mixer RINPUT1' 2
  m 'Capture' 45 cap
  m 'ADC PCM' 195
  sudo alsactl store "$CARD" || true
  echo "  ReSpeaker is card $CARD"
else
  echo "  ReSpeaker not found yet (needs the reboot below), run ./setup_pi.sh again afterwards"
fi

echo "== Service (robot.service)"
sudo tee /etc/systemd/system/robot.service >/dev/null <<EOF
[Unit]
Description=Desktop robot
After=network-online.target sound.target
Wants=network-online.target

[Service]
User=$RUN_USER
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python -m robot.main
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload

echo
if [ "$NEED_REBOOT" = 1 ]; then
  echo "Done, but I2C/SPI/audio were just enabled: sudo reboot, then run ./setup_pi.sh again."
else
  echo "Done. Next:"
  echo "  sudo i2cdetect -y 1                       # expect 1a, 36, 3c"
  echo "  .venv/bin/python -m robot.hw.motors       # each motor both ways"
  echo "  .venv/bin/python -m robot.main            # run it by hand"
  echo "  sudo systemctl enable --now robot         # start at every boot (journalctl -fu robot for logs)"
fi
