#!/bin/sh
# Brings up the Pi's USB network link to the PC: 10.55.0.2 (PC = 10.55.0.1).
# Run as root at every boot by cloud-init (bootcmd, added by prepare_sd.sh). Kept on the
# boot partition so it can be edited from any computer.
# Logs to /boot/firmware/usb-link.log so a failure can be read from the SD card.
MAC=02:52:4f:42:00:02          # the Pi's end, fixed by g_ether.dev_addr in cmdline.txt
LOG=/boot/firmware/usb-link.log
exec >>"$LOG" 2>&1
echo "== $(date '+%F %T') boot"

# NetworkManager must not manage the USB link, or it may take it down again.
mkdir -p /etc/NetworkManager/conf.d
printf '[keyfile]\nunmanaged-devices=mac:%s\n' "$MAC" > /etc/NetworkManager/conf.d/90-robot-usb.conf
nmcli general reload conf 2>/dev/null || true

# Find the interface by MAC (its name may not be usb0). g_ether is loaded at boot.
IF=
i=0
while [ -z "$IF" ] && [ $i -lt 90 ]; do
  for d in /sys/class/net/*; do
    [ "$(cat "$d/address" 2>/dev/null)" = "$MAC" ] && IF=$(basename "$d")
  done
  [ -n "$IF" ] || { sleep 1; i=$((i + 1)); }
done
echo "interfaces: $(ls /sys/class/net | tr '\n' ' ')"
if [ -z "$IF" ]; then
  echo "no interface with MAC $MAC"
  exit 0
fi
nmcli device set "$IF" managed no 2>/dev/null || true
ip link set "$IF" up
ip addr replace 10.55.0.2/24 dev "$IF"
ip -br addr show "$IF"
