"""Two DC motors on the DRV8833.

- Speeds are -1.0..1.0 and get scaled by config.MAX_DUTY here, so calling code
  can never over-drive the 3.3V motors.
- Speed-ups are ramped over config.RAMP_TIME so motor inrush can't brown out the Pi.
  Slowing down and stopping happen immediately.

Test on its own:
    python -m robot.hw.motors          # each motor forward then backward, slowly
"""

import threading
import time

from robot import config


def _clamp(v):
    return max(-1.0, min(1.0, float(v)))


class Drive:
    def __init__(self):
        from gpiozero import Motor

        left_pins, right_pins = config.LEFT_MOTOR_PINS, config.RIGHT_MOTOR_PINS
        if config.SWAP_LEFT_RIGHT:
            left_pins, right_pins = right_pins, left_pins
        self._motors = (Motor(*left_pins, pwm=True), Motor(*right_pins, pwm=True))
        for m in self._motors:
            m.forward_device.frequency = config.PWM_FREQUENCY
            m.backward_device.frequency = config.PWM_FREQUENCY
        self._signs = (-1 if config.INVERT_LEFT else 1, -1 if config.INVERT_RIGHT else 1)

        self._lock = threading.Lock()
        self._target = [0.0, 0.0]
        self._current = [0.0, 0.0]
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="motors", daemon=True)
        self._thread.start()

    def set(self, left, right):
        """Ask for wheel speeds (-1..1). Speed-ups are ramped."""
        with self._lock:
            self._target = [_clamp(left), _clamp(right)]

    def stop(self):
        """Stop both motors now (no ramp)."""
        with self._lock:
            self._target = [0.0, 0.0]
            self._current = [0.0, 0.0]
            self._apply()

    @property
    def moving(self):
        return any(abs(v) > 0.01 for v in self._current)

    def close(self):
        self._running = False
        self._thread.join(timeout=1)
        self.stop()
        for m in self._motors:
            m.close()

    def _loop(self):
        step = config.MOTOR_TICK / config.RAMP_TIME
        while self._running:
            time.sleep(config.MOTOR_TICK)
            with self._lock:
                changed = False
                for i in (0, 1):
                    cur, tgt = self._current[i], self._target[i]
                    if cur == tgt:
                        continue
                    if cur * tgt < 0:
                        cur = 0.0                       # reversing: drop to zero first
                    if abs(tgt) <= abs(cur):
                        cur = tgt                       # slowing down: immediate
                    else:
                        cur += step if tgt > cur else -step
                        if abs(cur) > abs(tgt):
                            cur = tgt
                    self._current[i] = cur
                    changed = True
                if changed:
                    self._apply()

    def _apply(self):
        for motor, sign, speed in zip(self._motors, self._signs, self._current):
            motor.value = sign * speed * config.MAX_DUTY


if __name__ == "__main__":
    print(f"Duty cap {config.MAX_DUTY}.")
    drive = Drive()
    try:
        for name, (l, r) in [("left forward", (0.6, 0)), ("left backward", (-0.6, 0)),
                             ("right forward", (0, 0.6)), ("right backward", (0, -0.6)),
                             ("both forward", (0.6, 0.6))]:
            print(name)
            drive.set(l, r)
            time.sleep(1.0)
            drive.stop()
            time.sleep(0.5)
        print("Done. Wrong direction or side? Fix SWAP_LEFT_RIGHT / INVERT_* in config.py.")
    finally:
        drive.close()
