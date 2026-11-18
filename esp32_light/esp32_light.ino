// ESP32 robot light: connects to Wi-Fi and the MQTT broker, switches the LED
// when the Pi sends a voice command.
//
//   home/robot/light/set    <- ON | OFF | TOGGLE   (sent by pi_voice_mqtt.py)
//   home/robot/light/state  -> ON | OFF            (reported back, retained)
//   home/robot/status       -> online | offline    (offline = ESP32 lost power/Wi-Fi)
//
// Wi-Fi name/password and the broker IP are in config.h.
// Needs the PubSubClient library (Library Manager -> "PubSubClient").

#include <WiFi.h>
#include <PubSubClient.h>
#include "config.h"

const char* SET_TOPIC    = "home/robot/light/set";
const char* STATE_TOPIC  = "home/robot/light/state";
const char* STATUS_TOPIC = "home/robot/status";

WiFiClient wifi;
PubSubClient mqtt(wifi);
bool isOn = false;
unsigned long lastAttempt = 0;

void publishState() {
  mqtt.publish(STATE_TOPIC, isOn ? "ON" : "OFF", true);
}

void setLight(bool on) {
  isOn = on;
  digitalWrite(LED_PIN, on ? HIGH : LOW);
  Serial.printf("LIGHT %s\n", on ? "ON" : "OFF");
  publishState();
}

void onMessage(char* topic, byte* payload, unsigned int length) {
  String cmd;
  for (unsigned int i = 0; i < length; i++) cmd += (char)payload[i];
  cmd.trim();
  cmd.toUpperCase();
  Serial.printf("Got %s = %s\n", topic, cmd.c_str());

  if (cmd == "ON") setLight(true);
  else if (cmd == "OFF") setLight(false);
  else if (cmd == "TOGGLE") setLight(!isOn);
  else Serial.println("Unknown command");
}

void connectWifi() {
  // Try a few times, starting fresh each time; if it still fails, reboot.
  // (Calling begin() again on a half-dropped connection can hang forever.)
  for (int attempt = 1; attempt <= 3; attempt++) {
    Serial.printf("Connecting to Wi-Fi %s (attempt %d)", WIFI_SSID, attempt);
    WiFi.disconnect(true);
    delay(200);
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);  // power saving makes the ESP32 miss MQTT pings
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
      delay(500);
      Serial.print(".");
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("\nWi-Fi connected, ESP32 IP: %s, signal %d dBm\n",
                    WiFi.localIP().toString().c_str(), WiFi.RSSI());
      return;
    }
    Serial.printf("\nWi-Fi failed (status %d)\n", WiFi.status());
  }
  Serial.println("Wi-Fi still down, restarting the ESP32");
  ESP.restart();
}

bool connectMqtt() {
  Serial.printf("Connecting to broker %s:%d... ", MQTT_HOST, MQTT_PORT);
  // Last will: the broker publishes "offline" if the ESP32 disappears.
  if (!mqtt.connect("esp32-robot-light", STATUS_TOPIC, 1, true, "offline")) {
    Serial.printf("failed (state %d), retrying\n", mqtt.state());
    return false;
  }
  Serial.println("connected");
  mqtt.publish(STATUS_TOPIC, "online", true);
  mqtt.subscribe(SET_TOPIC, 1);
  publishState();
  return true;
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  connectWifi();
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi lost");
    connectWifi();
  }
  if (!mqtt.connected()) {
    // Retry every 3 s without blocking.
    if (millis() - lastAttempt > 3000) {
      lastAttempt = millis();
      connectMqtt();
    }
    return;
  }
  mqtt.loop();
}
