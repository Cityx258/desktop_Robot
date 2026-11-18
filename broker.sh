#!/bin/bash
# Start/stop the local demo MQTT broker (Mosquitto). Works on a Mac or on the Pi.
#
#   ./broker.sh start    start in the background
#   ./broker.sh stop     turn it off
#   ./broker.sh status   is it running? which IP should the ESP32 use?
#   ./broker.sh log      watch messages live (Ctrl+C stops watching, not the broker)

cd "$(dirname "$0")"
MOSQUITTO=$(command -v mosquitto || ls /opt/homebrew/sbin/mosquitto /usr/local/sbin/mosquitto /usr/sbin/mosquitto 2>/dev/null | head -1)
CONF=mosquitto-demo.conf
LOG=broker.log

running() { pgrep -f "mosquitto -c $CONF" >/dev/null; }

my_ip() {
  if [ "$(uname)" = Darwin ]; then ipconfig getifaddr en0
  else hostname -I | awk '{print $1}'; fi
}

case "$1" in
  start)
    if [ -z "$MOSQUITTO" ]; then
      echo "Mosquitto isn't installed (Mac: brew install mosquitto, Pi: sudo apt install mosquitto)"; exit 1
    fi
    if running; then echo "Broker already running."; exit 0; fi
    nohup "$MOSQUITTO" -c "$CONF" -v >"$LOG" 2>&1 &
    sleep 1
    if running; then
      echo "Broker started. Use MQTT_HOST=$(my_ip) (ESP32 config.h, and the voice script if it runs on another machine)"
    else
      echo "Broker failed to start:"; tail -5 "$LOG"
      grep -q "Address already in use" "$LOG" && echo "Port 1883 is taken. On the Pi, stop the system broker first: sudo systemctl disable --now mosquitto"
      exit 1
    fi
    ;;
  stop)
    if running; then pkill -f "mosquitto -c $CONF"; echo "Broker stopped."
    else echo "Broker was not running."; fi
    ;;
  status)
    if running; then echo "Running. Use MQTT_HOST=$(my_ip)"
    else echo "Stopped."; fi
    ;;
  log)
    tail -f "$LOG"
    ;;
  *)
    echo "Usage: $0 {start|stop|status|log}"; exit 1
    ;;
esac
