#!/usr/bin/env python3
"""
Raspberry Pi -> online MQTT broker bridge for voice-controlled smart appliances.

Flow:
    microphone -> speech-to-text -> command parser -> MQTT publish
    MQTT state topics -> console (so the Pi knows what the devices report)

Topic layout (change BASE_TOPIC / DEVICES to match your house):
    home/<room>/<device>/set     <- we publish commands here ("ON", "OFF", "50", ...)
    home/<room>/<device>/state   <- devices publish their state here
    home/pi/status               <- "online"/"offline" (Last Will)

Run:
    python3 pi_voice_mqtt.py            # voice mode (needs a microphone)
    python3 pi_voice_mqtt.py --text     # type commands instead (handy for testing)
"""

import argparse
import logging
import os
import re
import ssl
import sys
import time

import paho.mqtt.client as mqtt

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration (read from environment / .env file)
# ---------------------------------------------------------------------------
BROKER_HOST = os.getenv("MQTT_HOST", "broker.hivemq.com")
BROKER_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")
USE_TLS = os.getenv("MQTT_TLS", "true").lower() == "true"
CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "pi-voice-controller")
BASE_TOPIC = os.getenv("MQTT_BASE_TOPIC", "home")
SPEECH_LANG = os.getenv("SPEECH_LANG", "en-US")  # "fr-CA" for French
# Part of the microphone's name, e.g. "seeed" or "wm8960" for the ReSpeaker HAT.
# Empty = system default mic. List names with: python3 pi_voice_mqtt.py --list-mics
MIC_NAME = os.getenv("MIC_NAME", "")

STATUS_TOPIC = f"{BASE_TOPIC}/pi/status"

# Spoken name(s) -> topic path under BASE_TOPIC.
# Add your appliances here.
DEVICES = {
    "living room light": "living_room/light",
    "kitchen light":     "kitchen/light",
    "bedroom light":     "bedroom/light",
    "fan":               "bedroom/fan",
    "coffee machine":    "kitchen/coffee_machine",
    "thermostat":        "living_room/thermostat",
    # Plain "light" = the robot's light for the demo ("open the light").
    "light":             "robot/light",
}

# Spoken action -> payload sent on the /set topic.
# "...on" / "...off" at the end covers "turn the light on".
ACTIONS = {
    r"\b(turn on|switch on|start|open)\b|\bon$":    "ON",
    r"\b(turn off|switch off|stop|close)\b|\boff$": "OFF",
    r"\btoggle\b":                           "TOGGLE",
}

log = logging.getLogger("pi-mqtt")


# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        log.error("Connection failed: %s", reason_code)
        return
    log.info("Connected to %s:%s", BROKER_HOST, BROKER_PORT)
    client.publish(STATUS_TOPIC, "online", qos=1, retain=True)
    # Listen to every device's state so we can confirm commands worked.
    client.subscribe(f"{BASE_TOPIC}/+/+/state", qos=1)


def on_disconnect(client, userdata, flags, reason_code, properties):
    log.warning("Disconnected (%s), paho will retry automatically", reason_code)


def on_connect_fail(client, userdata):
    log.warning("Can't reach %s:%s, retrying (is the port blocked on this network?)", BROKER_HOST, BROKER_PORT)


def on_message(client, userdata, msg):
    log.info("State update  %s = %s", msg.topic, msg.payload.decode(errors="replace"))


def build_client() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    if USE_TLS:
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    # If the Pi loses power/network, the broker tells everyone it's offline.
    client.will_set(STATUS_TOPIC, "offline", qos=1, retain=True)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_connect_fail = on_connect_fail
    client.on_message = on_message
    return client


def send_command(client: mqtt.Client, device_path: str, payload: str) -> None:
    topic = f"{BASE_TOPIC}/{device_path}/set"
    if not client.is_connected():
        log.warning("Not connected to broker, would have sent %s = %s", topic, payload)
        return
    result = client.publish(topic, payload, qos=1)
    try:
        result.wait_for_publish(timeout=5)
    except (RuntimeError, ValueError) as e:
        log.error("Publish failed for %s: %s", topic, e)
        return
    log.info("Sent          %s = %s", topic, payload)


# ---------------------------------------------------------------------------
# Command parsing
# ---------------------------------------------------------------------------
def parse_command(text: str):
    """Turn 'turn on the kitchen light' into ('kitchen/light', 'ON').

    Returns None if nothing matched.
    """
    text = text.lower().strip()

    # Longest name first so "living room light" beats "light".
    device = next((DEVICES[n] for n in sorted(DEVICES, key=len, reverse=True) if n in text), None)
    if device is None:
        return None

    # "set the thermostat to 21" -> numeric payload
    number = re.search(r"\bto (\d+(?:\.\d+)?)\b", text)
    if number:
        return device, number.group(1)

    for pattern, payload in ACTIONS.items():
        if re.search(pattern, text):
            return device, payload
    return None


# ---------------------------------------------------------------------------
# Input sources
# ---------------------------------------------------------------------------
def voice_phrases():
    """Yield recognised phrases from the microphone forever."""
    import speech_recognition as sr

    device_index = None
    if MIC_NAME:
        names = sr.Microphone.list_microphone_names()
        device_index = next((i for i, n in enumerate(names) if MIC_NAME.lower() in n.lower()), None)
        if device_index is None:
            sys.exit(f"No microphone matching {MIC_NAME!r}. Available: {names}")
        log.info("Using microphone %d: %s", device_index, names[device_index])

    recognizer = sr.Recognizer()
    with sr.Microphone(device_index=device_index) as source:
        log.info("Calibrating for ambient noise...")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        log.info("Listening. Say e.g. 'turn on the kitchen light'.")
        while True:
            try:
                audio = recognizer.listen(source, phrase_time_limit=5)
                # Google's free web API: needs internet. Swap for Vosk/Whisper to run offline.
                yield recognizer.recognize_google(audio, language=SPEECH_LANG)
            except sr.UnknownValueError:
                continue
            except sr.RequestError as e:
                log.error("Speech service error: %s", e)
                time.sleep(2)


def text_phrases():
    """Yield typed commands (for testing without a microphone)."""
    print("Type a command (Ctrl+C to quit):")
    for line in sys.stdin:
        if line.strip():
            yield line


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--text", action="store_true", help="type commands instead of speaking")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--list-mics", action="store_true", help="print microphone names and exit")
    args = parser.parse_args()

    if args.list_mics:
        import speech_recognition as sr
        for i, name in enumerate(sr.Microphone.list_microphone_names()):
            print(i, name)
        return

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    client = build_client()
    client.connect_async(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()  # network loop runs in a background thread

    # Give the broker a moment before listening, so the first command isn't lost.
    deadline = time.time() + 10
    while not client.is_connected() and time.time() < deadline:
        time.sleep(0.1)

    phrases = text_phrases() if args.text else voice_phrases()
    try:
        for phrase in phrases:
            log.info("Heard         %r", phrase.strip())
            command = parse_command(phrase)
            if command is None:
                log.info("Didn't understand that. Known devices: %s", ", ".join(DEVICES))
                continue
            send_command(client, *command)
    except KeyboardInterrupt:
        pass
    finally:
        if client.is_connected():
            client.publish(STATUS_TOPIC, "offline", qos=1, retain=True).wait_for_publish(timeout=2)
        client.loop_stop()
        client.disconnect()
        log.info("Bye")


if __name__ == "__main__":
    main()
