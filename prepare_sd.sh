#!/bin/bash
# Prepares a freshly flashed SD card for the robot. Runs on the PC, before the card
# ever goes in the Pi.
#
# 1. Flash with Raspberry Pi Imager: Raspberry Pi OS Lite (32-bit). In the customisation
#    set the hostname, user, password, Wi-Fi (the hotspot) and turn SSH on.
# 2. Plug the card back in the PC (the "bootfs" partition gets mounted), then:
#       ./prepare_sd.sh                       # broker = this PC's IP
#       ./prepare_sd.sh 192.168.2.202         # or give the broker address
#       BOOT=/path/to/bootfs ./prepare_sd.sh  # if bootfs is mounted somewhere else
# 3. Put the card in the Pi, connect the Pi's USB *data* port (not PWR) to the PC, and:
#       ssh mikubot@10.55.0.2                 # 2-5 min after power-on the first time
#    (PC side, once: sudo cp pc/10-robot-usb.network /etc/systemd/network/ && sudo networkctl reload)
# 4. On the Pi:
#       cp -r /boot/firmware/desktop_Robot ~/ && cd ~/desktop_Robot && ./setup_pi.sh
#
# What it changes on the card:
#   config.txt     I2C (400 kHz), SPI, ReSpeaker audio, USB gadget, motor pins low from power-on
#   cmdline.txt    load the USB network gadget, with fixed MAC addresses
#   user-data      runs usb-link.sh at every boot: the Pi's USB link gets 10.55.0.2
#                  (cmdline.txt gets a new cloud-init instance id so it's applied)
#   desktop_Robot/ the project, with robot.conf pointing to the broker
set -e
cd "$(dirname "$0")"

BOOT=${BOOT:-/run/media/$USER/bootfs}
BROKER=${1:-$(ip -4 route get 1.1.1.1 2>/dev/null | sed -nE 's/.* src ([0-9.]+).*/\1/p')}
PI_USB_IP=10.55.0.2
HOST_MAC=02:52:4f:42:00:01      # this PC's end of the cable (matched by pc/10-robot-usb.network)
DEV_MAC=02:52:4f:42:00:02       # the Pi's end

if [ ! -f "$BOOT/config.txt" ]; then
  echo "No SD card boot partition at $BOOT (plug the card in, or set BOOT=...)"; exit 1
fi
[ -n "$BROKER" ] || { echo "Couldn't find this PC's IP, pass the broker address: ./prepare_sd.sh <ip>"; exit 1; }

echo "== config.txt"
CONFIG_LINES="dtparam=i2c_arm=on dtparam=i2c_arm_baudrate=400000 dtparam=spi=on dtoverlay=wm8960-soundcard dtoverlay=dwc2,dr_mode=peripheral gpio=5,6,12,13=op,dl"
grep -q "^# Desktop robot" "$BOOT/config.txt" || printf '\n# Desktop robot\n' >> "$BOOT/config.txt"
for line in $CONFIG_LINES; do
  grep -qx "$line" "$BOOT/config.txt" || echo "$line" >> "$BOOT/config.txt"
done

echo "== cmdline.txt: USB network gadget"
if ! grep -q "g_ether" "$BOOT/cmdline.txt"; then
  sed -i "1s/\$/ modules-load=dwc2,g_ether g_ether.host_addr=$HOST_MAC g_ether.dev_addr=$DEV_MAC/" "$BOOT/cmdline.txt"
fi
[ "$(wc -l < "$BOOT/cmdline.txt")" -le 1 ] || { echo "cmdline.txt must stay one line"; exit 1; }

echo "== USB link: usb0 = $PI_USB_IP, set up by our own boot step"
# Raspberry Pi OS didn't bring usb0 up from network-config, so usb0 is configured by
# usb-link.sh (run by cloud-init's bootcmd at every boot) and NetworkManager leaves it alone.
if [ -f "$BOOT/network-config" ] && grep -q "^    usb0:" "$BOOT/network-config"; then
  sed -i '/^    usb0:$/,+2d' "$BOOT/network-config"     # remove the old usb0 entry (3 lines)
fi
if ! grep -q "Desktop robot usb link" "$BOOT/user-data"; then
  cat >> "$BOOT/user-data" <<'EOF'
bootcmd:
  # Desktop robot usb link
  - [ sh, /boot/firmware/desktop_Robot/usb-link.sh ]
EOF
fi
# cloud-init only reads user-data for a new instance, and Imager puts the instance id in
# cmdline.txt (ds=nocloud;i=...): give it a new one so an already-booted card applies this too.
sed -i -E "s/(ds=nocloud;i=[^ ]*)-robot[0-9]+/\1/; s/(ds=nocloud;i=[^ ]*)/\1-robot$(date +%s)/" "$BOOT/cmdline.txt"
python3 - "$BOOT/user-data" "$BOOT/network-config" <<'EOF'
import sys
try:
    import yaml
except ImportError:
    sys.exit(0)
ud = yaml.safe_load(open(sys.argv[1]))
assert any("usb-link.sh" in str(c) for c in ud.get("bootcmd", [])), "bootcmd not added"
net = yaml.safe_load(open(sys.argv[2]))["network"]
assert "usb0" not in net.get("ethernets", {}), "usb0 still in network-config"
print("   user-data OK, Wi-Fi:", ", ".join(net.get("wifis", {}).get("wlan0", {}).get("access-points", {})) or "none")
EOF
echo "   $(grep -oE 'ds=nocloud;i=[^ ]*' "$BOOT/cmdline.txt")"

echo "== Project files -> $BOOT/desktop_Robot"
rm -rf "$BOOT/desktop_Robot"
mkdir -p "$BOOT/desktop_Robot"
cp -r robot setup_pi.sh usb-link.sh requirements.txt robot.conf.example README.md RobotProjectInfo.md "$BOOT/desktop_Robot/"
find "$BOOT/desktop_Robot" -name __pycache__ -prune -exec rm -rf {} +
if [ -f robot.conf ]; then
  cp robot.conf "$BOOT/desktop_Robot/robot.conf"
else
  sed "s/^host = .*/host = $BROKER/" robot.conf.example > "$BOOT/desktop_Robot/robot.conf"
fi
echo "   broker: $(grep '^host' "$BOOT/desktop_Robot/robot.conf")"

sync
echo
echo "Card ready. Put it in the Pi, plug the Pi's USB data port into this PC, then:"
echo "  ssh mikubot@$PI_USB_IP"
