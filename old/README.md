# Old approaches (not used anymore)

Kept for reference; nothing here is needed to run the robot.

| File | What it was | Why it was dropped |
|---|---|---|
| `prepare_sd.sh` | Set up a freshly flashed SD card from the PC (config.txt, cloud-init, project files) | cloud-init changes were unreliable and invisible; setup is now done over ssh |
| `usb-link.sh`, `pc/10-robot-usb.network` | Networking over the Pi Zero's USB cable (Pi = 10.55.0.2) | Clashed with Raspberry Pi OS's own `rpi-usb-gadget`; the Pi now uses the home Wi-Fi |
| `pc/card_wifi.sh` | Added a Wi-Fi network to the SD card from the PC | One-off; use `nmcli` on the Pi instead |
| `pi_voice_mqtt.py` | First standalone voice-to-MQTT script | Replaced by `pi/robot/` (needs PyAudio, which no longer installs) |
