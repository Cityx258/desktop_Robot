"""Push-to-talk voice: record with arecord, transcribe, turn the text into a command.

Recording uses the arecord command (alsa-utils), so PyAudio isn't needed.
Speech-to-text uses Google's free web service through the SpeechRecognition package:
the Pi needs internet, and the Pi Zero is far too slow to transcribe on its own.
To move transcription to a computer later, publish the WAV instead and let the
broker side do it: everything after transcribe() stays the same.

Test on a computer, no hardware needed:
    python -m robot.voice "turn on the light"
"""

import logging
import re
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from robot import config

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------
def find_audio_device():
    """Return an ALSA device string for the ReSpeaker, e.g. 'plughw:CARD=respeaker,DEV=0'."""
    if config.AUDIO_DEVICE:
        return config.AUDIO_DEVICE
    out = subprocess.run(["arecord", "-l"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        m = re.match(r"card \d+: (\S+) \[(.*?)\]", line)
        if m and re.search(r"wm8960|respeaker|seeed", line, re.I):
            return f"plughw:CARD={m.group(1)},DEV=0"
    raise RuntimeError("ReSpeaker not found in `arecord -l`. Is dtoverlay=wm8960-soundcard "
                       f"in /boot/firmware/config.txt? arecord says:\n{out}")


class Recorder:
    def __init__(self):
        self.device = find_audio_device()
        self._proc = None
        self.path = Path(tempfile.gettempdir()) / f"{config.ROBOT_NAME}-voice.wav"

    def start(self):
        self.stop()
        self._proc = subprocess.Popen(
            ["arecord", "-q", "-D", self.device, "-f", "S16_LE", "-c", "1",
             "-r", str(config.AUDIO_RATE), "-d", str(config.MAX_RECORD_TIME), str(self.path)],
            stderr=subprocess.PIPE)

    def stop(self):
        """Stop recording and return the WAV path (None if nothing was recording)."""
        if self._proc is None:
            return None
        proc, self._proc = self._proc, None
        if proc.poll() is None:
            # Keep recording a moment: people release the button while still saying
            # the last word, and arecord drops what's still in its buffer.
            time.sleep(config.RECORD_TAIL)
            proc.send_signal(signal.SIGINT)  # arecord finishes the WAV header on SIGINT
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        err = proc.stderr.read().decode(errors="replace").strip()
        if err:
            log.warning("arecord: %s", err)
        return self.path


# ---------------------------------------------------------------------------
# Speech to text
# ---------------------------------------------------------------------------
_sr = None


def preload():
    """Import SpeechRecognition ahead of time (takes a few seconds on a Pi Zero)."""
    global _sr
    if _sr is None:
        import speech_recognition
        _sr = speech_recognition


def transcribe(wav_path):
    """Return the recognised text, or None if nothing was understood.

    Raises ConnectionError if the speech service can't be reached.
    """
    preload()
    recognizer = _sr.Recognizer()
    recognizer.operation_timeout = 10
    with _sr.AudioFile(str(wav_path)) as source:
        audio = recognizer.record(source)
    try:
        return recognizer.recognize_google(audio, language=config.SPEECH_LANGUAGE)
    except _sr.UnknownValueError:
        return None
    except _sr.RequestError as e:
        raise ConnectionError(f"Speech service unreachable: {e}") from e


# ---------------------------------------------------------------------------
# Text -> command
# ---------------------------------------------------------------------------
# Robot commands. Checked after device commands, so "turn off the light" isn't "stop".
# Stop first, so "stop roaming" is a stop.
ROBOT_COMMANDS = [
    (r"\b(stop|halt|freeze|stay|sit|wait|be still)\b", "stop"),
    (r"\b(spin\w*|turn around|do a twirl)\b", "spin"),
    (r"\b(roam\w*|wander\w*|explor\w*|go around|move around|start moving|let'?s go)\b", "roam"),
]

# Device actions -> payload on <device>/set. "...on"/"...off" at the end covers
# "turn the light on".
DEVICE_ACTIONS = [
    (r"\b(turn on|switch on|open|light up)\b|\bon$", "ON"),
    (r"\b(turn off|switch off|close|shut)\b|\boff$", "OFF"),
    (r"\b(toggle|switch)\b", "TOGGLE"),
]


def parse(text):
    """Turn a phrase into ("robot", action) or ("device", topic_prefix, payload), or None."""
    text = text.lower().strip().rstrip(".!?")

    # Longest device name first, so "kitchen light" beats "light".
    for name in sorted(config.DEVICES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", text):
            for pattern, payload in DEVICE_ACTIONS:
                if re.search(pattern, text):
                    return ("device", config.DEVICES[name], payload)
            return None  # named a device but no action: don't guess

    for pattern, action in ROBOT_COMMANDS:
        if re.search(pattern, text):
            return ("robot", action)
    return None


if __name__ == "__main__":
    import sys

    for phrase in sys.argv[1:] or ["turn on the light", "turn the light off", "start roaming",
                                   "stop", "spin around", "hello there"]:
        print(f"{phrase!r:30} -> {parse(phrase)}")
