#!/bin/bash
# Run on the PC with the robot's SD card plugged in (needs root, the Pi's files are root's):
#     sudo pc/card_wifi.sh "<wifi name>" "<wifi password>"
#
# 1. Copies the Pi's logs from its last boot (Wi-Fi, NetworkManager, cloud-init) to
#    pc/card-logs.txt, readable without root.
# 2. Adds the home Wi-Fi as a normal NetworkManager connection on the Pi
#    (/etc/NetworkManager/system-connections/), the same file `nmcli` would create.
#    It is tried before any other Wi-Fi (priority 10). Doesn't depend on cloud-init.
set -e
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ] || { echo "Run with sudo: sudo $0"; exit 1; }

SSID=$1
PSK=$2
[ -n "$SSID" ] && [ -n "$PSK" ] || { echo "Usage: sudo $0 \"<wifi name>\" \"<wifi password>\""; exit 1; }
DEV=/dev/sdc2
OUT=card-logs.txt

ROOT=$(findmnt -n -o TARGET "$DEV" || true)
if [ -z "$ROOT" ]; then
  ROOT=/mnt/robot-card
  mkdir -p "$ROOT"
  mount "$DEV" "$ROOT"
fi
[ -f "$ROOT/etc/os-release" ] || { echo "$DEV doesn't look like the Pi's root partition"; exit 1; }
echo "Pi root partition: $ROOT"

{
  echo "===== boots"
  journalctl -D "$ROOT/var/log/journal" --list-boots --no-pager 2>&1 | tail -5
  echo "===== last boot: network, Wi-Fi, cloud-init, errors"
  journalctl -D "$ROOT/var/log/journal" -b 0 --no-pager -o short-monotonic 2>&1 \
    | grep -iE "NetworkManager|wpa_supplicant|wlan0|brcmf|cloud-init|netplan|usb0|g_ether|dwc2|gadget|failed|error" \
    | grep -v "$PSK" | tail -250
  echo "===== cloud-init-output.log (tail)"
  tail -60 "$ROOT/var/log/cloud-init-output.log" 2>&1
  echo "===== cloud-init.log: network lines"
  grep -iE "network|netplan|renderer|apply" "$ROOT/var/log/cloud-init.log" 2>&1 | tail -60
  echo "===== /etc/netplan"
  for f in "$ROOT"/etc/netplan/*.yaml; do echo "--- $f"; sed -E 's/(password|psk)(: *).*/\1\2<hidden>/' "$f"; done
  echo "===== /etc/NetworkManager/system-connections"
  ls -la "$ROOT/etc/NetworkManager/system-connections/"
} > "$OUT" 2>&1
chmod 644 "$OUT"
echo "Logs saved to pc/$OUT"

CONN="$ROOT/etc/NetworkManager/system-connections/home-wifi.nmconnection"
cat > "$CONN" <<EOF
[connection]
id=home-wifi
uuid=$(cat /proc/sys/kernel/random/uuid)
type=wifi
autoconnect=true
autoconnect-priority=10

[wifi]
mode=infrastructure
ssid=$SSID

[wifi-security]
key-mgmt=wpa-psk
psk=$PSK

[ipv4]
method=auto

[ipv6]
method=auto
EOF
chown root:root "$CONN"
chmod 600 "$CONN"
echo "Home Wi-Fi ($SSID) added: $CONN"
sync
echo "Done. Eject the card and put it back in the Pi."
