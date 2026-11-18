"""The robot's face, drawn for the 128x64 OLED.

Pure Pillow, no hardware: render() returns an image, hw/display.py sends it.

Preview every expression on a computer:
    python -m robot.face            # writes face_preview.png
"""

from PIL import Image, ImageDraw

W, H = 128, 64
EYE_Y = 26
EYE_X = (40, 88)
EYE_W, EYE_H = 26, 30
LOOK_SHIFT = 10                    # pixels the eyes move when looking left/right

EXPRESSIONS = ("normal", "happy", "listening", "thinking", "confused", "sleepy")


def _eye(d, cx, cy, w, h):
    r = min(w, h) // 3
    d.rounded_rectangle((cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2), radius=r, fill=1)


def _smile(d, cx, cy, w, h, width=3):
    d.arc((cx - w // 2, cy - h, cx + w // 2, cy + h), start=20, end=160, fill=1, width=width)


def render(expression="normal", look=0, blink=False):
    """look: -1 left, 0 ahead, 1 right. blink: eyes closed for this frame."""
    img = Image.new("1", (W, H), 0)
    d = ImageDraw.Draw(img)
    dx = int(look * LOOK_SHIFT)

    if expression == "happy":                   # ^ ^ eyes, big smile
        for x in EYE_X:
            d.arc((x - 14 + dx, EYE_Y - 8, x + 14 + dx, EYE_Y + 16), start=200, end=340, fill=1, width=5)
        _smile(d, 64 + dx, 46, 36, 10, width=4)
        return img

    if blink:
        for x in EYE_X:
            d.rounded_rectangle((x - EYE_W // 2 + dx, EYE_Y - 2, x + EYE_W // 2 + dx, EYE_Y + 2), radius=2, fill=1)
        _smile(d, 64 + dx, 50, 20, 5)
        return img

    if expression == "listening":               # big round eyes, little "o" mouth
        for x in EYE_X:
            _eye(d, x, EYE_Y - 2, EYE_W + 6, EYE_H + 6)
        d.ellipse((59, 50, 69, 60), outline=1, width=2)
    elif expression == "thinking":              # eyes up and to the side, flat mouth
        for x in EYE_X:
            _eye(d, x + 8, EYE_Y - 6, EYE_W - 4, EYE_H - 8)
        d.line((54, 54, 74, 54), fill=1, width=3)
    elif expression == "confused":              # one squinting eye, crooked mouth
        _eye(d, EYE_X[0] + dx, EYE_Y, EYE_W, EYE_H)
        _eye(d, EYE_X[1] + dx, EYE_Y + 4, EYE_W, EYE_H // 3)
        d.line((54 + dx, 56, 64 + dx, 52, 74 + dx, 56), fill=1, width=3)
    elif expression == "sleepy":                # heavy eyelids: top half of each eye covered
        for x in EYE_X:
            _eye(d, x + dx, EYE_Y, EYE_W, EYE_H)
            d.rectangle((x - EYE_W // 2 + dx - 1, EYE_Y - EYE_H // 2 - 1, x + EYE_W // 2 + dx + 1, EYE_Y + 2), fill=0)
            d.line((x - EYE_W // 2 + dx, EYE_Y + 2, x + EYE_W // 2 + dx, EYE_Y + 2), fill=1, width=2)
        d.line((58 + dx, 54, 70 + dx, 54), fill=1, width=2)
    else:                                       # normal
        for x in EYE_X:
            _eye(d, x + dx, EYE_Y, EYE_W, EYE_H)
        _smile(d, 64 + dx, 48, 22, 6)
    return img


if __name__ == "__main__":
    frames = [(e, 0, False) for e in EXPRESSIONS] + [("normal", -1, False), ("normal", 1, False),
                                                     ("normal", 0, True)]
    sheet = Image.new("1", ((W + 4) * 3, (H + 4) * 3), 1)
    for i, (e, look, blink) in enumerate(frames):
        sheet.paste(render(e, look, blink), ((i % 3) * (W + 4) + 2, (i // 3) * (H + 4) + 2))
    sheet.save("face_preview.png")
    print("Wrote face_preview.png:", ", ".join(EXPRESSIONS), "+ look left/right + blink")
