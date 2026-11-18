"""MQTT link to the broker.

Topics (NAME = robot name from robot.conf):
    robot/NAME/status   -> online | offline        retained, offline is the Last Will
    robot/NAME/state    -> JSON every few seconds   retained (mode, battery, rssi...)
    robot/NAME/heard    -> every recognised phrase, as text (for the broker side to use)
    robot/NAME/cmd      <- roam | stop | spin       (same words as the voice commands)
    <device>/set        -> ON | OFF | TOGGLE        voice device commands (e.g. the lamp)
    <device>/state      <- logged, so you see the device confirm

Without a broker the robot still roams and obeys local voice commands:
paho keeps retrying in the background.
"""

import json
import logging
import ssl

import paho.mqtt.client as mqtt

from robot import config

log = logging.getLogger(__name__)


class Link:
    def __init__(self, on_command):
        """on_command(str) is called (from paho's thread) for every message on robot/NAME/cmd."""
        self._on_command = on_command
        self.status_topic = f"{config.TOPIC}/status"
        self.cmd_topic = f"{config.TOPIC}/cmd"

        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=config.ROBOT_NAME)
        if config.MQTT_USER:
            c.username_pw_set(config.MQTT_USER, config.MQTT_PASSWORD)
        if config.MQTT_TLS:
            c.tls_set(ca_certs=config.MQTT_CA_FILE or None, cert_reqs=ssl.CERT_REQUIRED)
        c.will_set(self.status_topic, "offline", qos=1, retain=True)
        c.reconnect_delay_set(min_delay=1, max_delay=30)
        c.on_connect = self._connected
        c.on_disconnect = self._disconnected
        c.on_message = self._message
        self._client = c

    @property
    def connected(self):
        return self._client.is_connected()

    def start(self):
        log.info("Broker %s:%s (tls=%s)", config.MQTT_HOST, config.MQTT_PORT, config.MQTT_TLS)
        self._client.connect_async(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
        self._client.loop_start()

    def stop(self):
        if self.connected:
            self._client.publish(self.status_topic, "offline", qos=1, retain=True).wait_for_publish(2)
            self._client.disconnect()
        self._client.loop_stop()

    def publish(self, topic, payload, qos=1, retain=False):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload)
        if not self.connected:
            log.warning("Not connected, dropped %s = %s", topic, payload)
            return False
        self._client.publish(topic, payload, qos=qos, retain=retain)
        return True

    # -- paho callbacks (run in paho's thread) --------------------------------
    def _connected(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("Broker refused the connection: %s", reason_code)
            return
        log.info("Connected to broker")
        client.publish(self.status_topic, "online", qos=1, retain=True)
        client.subscribe(self.cmd_topic, qos=1)
        for prefix in set(config.DEVICES.values()):
            client.subscribe(f"{prefix}/state", qos=1)

    def _disconnected(self, client, userdata, flags, reason_code, properties):
        log.warning("Lost the broker (%s), retrying", reason_code)

    def _message(self, client, userdata, msg):
        payload = msg.payload.decode(errors="replace").strip()
        if msg.topic == self.cmd_topic:
            log.info("Command from broker: %s", payload)
            try:
                self._on_command(payload.lower())
            except Exception:
                log.exception("Command %r failed", payload)
        else:
            log.info("Device state  %s = %s", msg.topic, payload)
