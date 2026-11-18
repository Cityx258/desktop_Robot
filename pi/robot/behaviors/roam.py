"""Roaming: a timed random walk.

Drive forward for a while, pause, pivot a random amount, sometimes reverse a bit, repeat.
There are no wheel encoders, so every move is timed.
"""

import logging
import random
import time

from robot import config

log = logging.getLogger(__name__)


def _rand(span):
    return random.uniform(*span)


class Roamer:
    def __init__(self, drive):
        self._drive = drive
        self._plan = []                # upcoming moves: (name, left, right, seconds)
        self._move = None              # (name, left, right, end_time)

    def reset(self):
        """Forget the current plan (call when roaming starts or resumes)."""
        self._plan.clear()
        self._move = None

    @property
    def look(self):
        """Where the eyes should look: -1 left, 0 ahead, 1 right (follows the current turn)."""
        if self._move is None:
            return 0
        _, left, right, _ = self._move
        return 1 if left > right else -1 if left < right else 0

    def tick(self):
        """Run one step. Call about 10 times a second while roaming."""
        now = time.monotonic()
        if self._move is None or now >= self._move[3]:
            if not self._plan:
                self._plan = self._next_plan()
            name, left, right, seconds = self._plan.pop(0)
            self._move = (name, left, right, now + seconds)
            log.debug("move %s %.2f/%.2f for %.1fs", name, left, right, seconds)

        _, left, right, _ = self._move
        self._drive.set(left, right)

    def _next_plan(self):
        s, t = config.ROAM_SPEED, config.TURN_SPEED
        plan = [("forward", s, s, _rand(config.ROAM_FORWARD_TIME)),
                ("pause", 0, 0, _rand(config.ROAM_PAUSE_TIME))]
        if random.random() < config.ROAM_REVERSE_CHANCE:
            plan.append(("reverse", -s, -s, _rand(config.ROAM_REVERSE_TIME)))
        turn = _rand(config.ROAM_TURN_TIME)
        plan.append(("turn", t, -t, turn) if random.random() < 0.5 else ("turn", -t, t, turn))
        plan.append(("pause", 0, 0, _rand(config.ROAM_PAUSE_TIME)))
        return plan
