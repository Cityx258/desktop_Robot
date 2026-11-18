// Template: copy to config.h (set_wifi.sh does it) and edit that. config.h is not committed.

// Same Wi-Fi network as the broker computer and the Pi. Must be 2.4 GHz.
#define WIFI_SSID     "your-wifi-name"
#define WIFI_PASSWORD "your-wifi-password"

// The broker computer's IP, as printed by ./broker.sh start
#define MQTT_HOST     "192.168.1.50"
#define MQTT_PORT     1883

// External red LED on GPIO 23 (via a 220 Ω resistor to the long leg, short leg to GND).
// GPIO 23 has no special role at boot, so the LED can't interfere with uploading.
#define LED_PIN       23
