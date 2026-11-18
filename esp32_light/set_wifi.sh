#!/bin/bash
# Asks for the Wi-Fi name and password and writes them into config.h (next to this script).
cd "$(dirname "$0")"
[ -f config.h ] || cp config.example.h config.h

read -r -p "Wi-Fi name: " SSID
read -r -s -p "Wi-Fi password (hidden while typing): " PASS
echo

SSID="$SSID" PASS="$PASS" python3 - <<'EOF'
import os, re
path = "config.h"
esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
text = open(path).read()
text = re.sub(r'(#define WIFI_SSID\s+)".*"', lambda m: m.group(1) + '"' + esc(os.environ["SSID"]) + '"', text)
text = re.sub(r'(#define WIFI_PASSWORD\s+)".*"', lambda m: m.group(1) + '"' + esc(os.environ["PASS"]) + '"', text)
open(path, "w").write(text)
EOF

echo "Saved to esp32_light/config.h (Wi-Fi: $SSID)"
