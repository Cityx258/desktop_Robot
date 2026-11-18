"""The robot program: roaming, push-to-talk voice commands, MQTT, battery, screen.

Run from the project folder:
    .venv/bin/python -m robot.main          # -v for debug logs

Controls:
    tap the ReSpeaker button         start / stop roaming
    hold the button and talk         voice command, released when done (LEDs blue = listening)
    MQTT robot/NAME/cmd              roam | stop | spin

Threads: the main loop below owns the motors and runs at 10 Hz. The button, the
speech worker and MQTT only put commands in a queue, which the main loop handles,
so nothing else ever touches the motors.
"""

import argparse
import logging
import queue
import signal
import subprocess
import threading
import time

from robot import config, voice
from robot.behaviors.roam import Roamer
from robot.hw.motors import Drive
from robot.net import Link

log = logging.getLogger("robot")

TICK = 0.1


def _optional(name, factory):
    """Start a piece of hardware, or log why not and carry on without it."""
    try:
        return factory()
    except Exception as e:
        log.warning("%s unavailable: %s", name, e)
        return None


def _wifi_rssi():
    try:
        with open("/proc/net/wireless") as f:
            for line in f.readlines()[2:]:
                return int(float(line.split()[3]))
    except (OSError, IndexError, ValueError):
        pass
    return None


class Robot:
    def __init__(self):
        from robot.hw.battery import Battery
        from robot.hw.display import Display
        from robot.hw.leds import Leds

        self.commands = queue.Queue()
        self.mode = "idle"            # idle | roam
        self.busy = None              # None | listening | thinking  (motors paused)
        self.heard = ""
        self.battery_low = False
        self._low_count = 0
        self._spin_until = 0.0
        self._flash = (None, 0.0)     # (led color, until)

        self.drive = Drive()          # required: no motors, no robot
        self.roamer = Roamer(self.drive)
        self.battery = _optional("Battery gauge", Battery)
        self.display = _optional("OLED", Display)
        self.leds = _optional("LEDs", Leds)
        self.recorder = _optional("Microphone", voice.Recorder)
        self.button = _optional("Button", self._setup_button)
        self.link = Link(on_command=lambda c: self.commands.put(("robot", c)))

        self._battery_reading = (None, None, None)
        if self.recorder:
            threading.Thread(target=self._preload_speech, daemon=True).start()

    # -- button / voice (gpiozero and worker threads) -----------------------
    def _setup_button(self):
        from gpiozero import Button

        b = Button(config.BUTTON_PIN, pull_up=True, bounce_time=0.05)
        b.when_pressed = self._pressed
        b.when_released = self._released
        return b

    def _pressed(self):
        if self.busy == "thinking":
            return
        self._press_time = time.monotonic()
        self.busy = "listening"
        if self.recorder:
            self.recorder.start()

    def _released(self):
        if self.busy != "listening":
            return
        held = time.monotonic() - self._press_time
        wav = self.recorder.stop() if self.recorder else None
        if held < config.TAP_TIME or wav is None:
            self.busy = None
            self.commands.put(("toggle",))
            return
        self.busy = "thinking"
        threading.Thread(target=self._understand, args=(wav,), daemon=True).start()

    def _understand(self, wav):
        try:
            text = voice.transcribe(wav)
            if not text:
                log.info("Heard nothing understandable")
                self.commands.put(("unknown", ""))
                return
            log.info("Heard         %r", text)
            self.heard = text
            self.link.publish(f"{config.TOPIC}/heard", text)
            self.commands.put(voice.parse(text) or ("unknown", text))
        except ConnectionError as e:
            log.error("%s", e)
            self.commands.put(("unknown", ""))
        except Exception:
            log.exception("Voice command failed")
            self.commands.put(("unknown", ""))
        finally:
            self.busy = None

    def _preload_speech(self):
        try:
            voice.preload()
            log.info("Speech recognition ready")
        except ImportError as e:
            log.error("SpeechRecognition isn't installed (%s): run ./setup_pi.sh", e)

    # -- main loop (main thread only) ----------------------------------------
    def run(self):
        self.link.start()
        log.info("Ready. Tap the button to roam, hold it to talk.")
        if config.ROAM_ON_START:
            self._check_battery()                  # don't start roaming on a low battery
            self.commands.put(("robot", "roam"))
        next_state = next_battery = 0.0
        while True:
            now = time.monotonic()
            self._handle_commands(now)

            if self.busy:                                  # listening: keep motors quiet
                self.drive.set(0, 0)
            elif now < self._spin_until:
                self.drive.set(config.TURN_SPEED, -config.TURN_SPEED)
            elif self.mode == "roam":
                self.roamer.tick()
            else:
                self.drive.set(0, 0)

            if now >= next_battery:
                next_battery = now + config.BATTERY_CHECK_EVERY
                self._check_battery()
            if now >= next_state:
                next_state = now + config.STATE_EVERY
                self.link.publish(f"{config.TOPIC}/state", self.state(), qos=0, retain=True)
            self._update_leds(now)
            self._update_face(now)

            time.sleep(TICK)

    def _handle_commands(self, now):
        while True:
            try:
                cmd = self.commands.get_nowait()
            except queue.Empty:
                return
            kind = cmd[0]
            if kind == "toggle":
                cmd = ("robot", "stop" if self.mode == "roam" else "roam")
                kind = "robot"

            if kind == "robot":
                action = cmd[1]
                if action == "roam":
                    if self.battery_low:
                        log.warning("Battery low: not roaming")
                        self._flash = ("error", now + 1)
                        continue
                    log.info("Roaming")
                    self.mode = "roam"
                    self.roamer.reset()
                elif action == "stop":
                    log.info("Stopping")
                    self.mode = "idle"
                    self._spin_until = 0
                    self.drive.stop()
                elif action == "spin":
                    log.info("Spinning")
                    self._spin_until = now + config.SPIN_TIME
                    self.roamer.reset()
                else:
                    log.warning("Unknown robot command %r", action)
                    self._flash = ("error", now + 1)
                    continue
                self._flash = ("ok", now + 0.6)
            elif kind == "device":
                _, prefix, payload = cmd
                sent = self.link.publish(f"{prefix}/set", payload)
                if sent:
                    log.info("Sent          %s/set = %s", prefix, payload)
                self._flash = ("ok" if sent else "offline", now + 1)
            elif kind == "unknown":
                if cmd[1]:
                    log.info("Didn't understand %r. Try: roam, stop, spin, turn on the %s",
                             cmd[1], next(iter(config.DEVICES)))
                self._flash = ("error", now + 1)

    def _check_battery(self):
        if not self.battery:
            return
        try:
            v, pct, chg = self.battery.volts, self.battery.percent, self.battery.charging
        except OSError as e:
            log.warning("Battery read failed: %s", e)
            return
        if v < 2.5:  # no cell reads this low: a bad I2C read, don't shut down over it
            log.warning("Ignoring implausible battery reading %.2f V", v)
            return
        self._battery_reading = (v, pct, chg)
        if chg:
            self._low_count = 0
            self.battery_low = False
            return

        if pct < config.BATTERY_SHUTDOWN_PERCENT or v < config.BATTERY_SHUTDOWN_VOLTS:
            self._low_count += 1
            if self._low_count >= config.BATTERY_LOW_READINGS:
                self._shutdown(v, pct)
        else:
            self._low_count = 0

        low = pct < config.BATTERY_LOW_PERCENT
        if low and not self.battery_low:
            log.warning("Battery low (%.0f%%): roaming off", pct)
            self.mode = "idle"
        self.battery_low = low

    def _shutdown(self, v, pct):
        log.critical("Battery empty (%.2f V, %.0f%%): shutting down", v, pct)
        self.drive.stop()
        if self.display:
            self.display.show_text(["BATTERY EMPTY", "Shutting down...", "", "Charge me, then", "switch on again"])
        self.link.stop()
        subprocess.run(["sudo", "-n", "/usr/sbin/shutdown", "-h", "now"])
        raise SystemExit(0)

    def state(self):
        v, pct, chg = self._battery_reading
        return {
            "mode": self.mode,
            "busy": self.busy,
            "moving": self.drive.moving,
            "battery_v": round(v, 2) if v else None,
            "battery_pct": round(pct) if pct is not None else None,
            "charging": chg,
            "rssi": _wifi_rssi(),
            "heard": self.heard,
        }

    def _update_leds(self, now):
        if not self.leds:
            return
        color, until = self._flash
        if self.busy:
            color = self.busy
        elif now >= until:
            color = "roam" if self.mode == "roam" else "idle" if self.link.connected else "offline"
        if color != getattr(self, "_led_color", None):
            self._led_color = color
            self.leds.color(color)

    def _update_face(self, now):
        if not self.display:
            return
        flash, until = self._flash
        look = 0
        if self.busy:
            expression = self.busy                       # listening / thinking
        elif now < until and flash in ("ok", "error", "offline"):
            expression = "happy" if flash == "ok" else "confused"
        elif now < self._spin_until:
            expression = "happy"
        elif self.battery_low:
            expression = "sleepy"
        else:
            expression = "normal"
            if self.mode == "roam":
                look = self.roamer.look                  # eyes follow the turns
        self.display.set_face(expression, look)

    # -- shutdown -----------------------------------------------------------
    def close(self):
        self.drive.close()
        for part in (self.recorder, self.button, self.leds, self.display, self.battery):
            if part is None:
                continue
            try:
                part.stop() if part is self.recorder else part.close()
            except Exception as e:
                log.debug("close %s: %s", part, e)
        self.link.stop()


def main():
    parser = argparse.ArgumentParser(description="Desktop robot")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")

    # SIGTERM (systemctl stop) unwinds like Ctrl+C, so the finally below stops the motors.
    def _terminate(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, _terminate)

    robot = Robot()
    try:
        robot.run()
    except KeyboardInterrupt:
        pass
    finally:
        robot.close()
        log.info("Stopped, motors off")


if __name__ == "__main__":
    main()
