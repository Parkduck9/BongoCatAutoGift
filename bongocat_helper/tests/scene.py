"""Synthetic Bongo Cat screens for tests: cats at arbitrary (x, y), name tags, gift icons."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = Path(r"C:\Windows\Fonts\malgun.ttf")
TAG_H = 26
OFF_LEFT = (-34, -96)    # icon center relative to tag center
OFF_RIGHT = (34, -96)
ICON = 40
OFF_BUBBLE = (-120, -100)  # chat bubble center relative to tag center (left of the left icon)


def gift_icon():
    """Distinctive 40x40 gift icon with '1000' label (same picture on both sides)."""
    img = np.full((ICON, ICON, 3), (40, 170, 240), np.uint8)       # orange box
    cv2.rectangle(img, (0, 0), (ICON - 1, ICON - 1), (20, 60, 120), 2)
    cv2.rectangle(img, (17, 0), (22, ICON - 1), (40, 40, 220), -1)  # red ribbon
    cv2.rectangle(img, (0, 12), (ICON - 1, 16), (40, 40, 220), -1)
    cv2.putText(img, "1000", (2, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
    return img


def background(w=900, h=420, seed=0):
    rng = np.random.default_rng(seed)
    base = np.zeros((h, w, 3), np.uint8)
    base[:] = (200, 120, 40)  # blue desktop
    noise = rng.integers(-25, 25, (h, w, 1))
    return np.clip(base.astype(int) + noise, 0, 255).astype(np.uint8)


def draw_tag(img, cx, cy, name):
    font = ImageFont.truetype(str(FONT), 15)
    tw = int(font.getlength(name))
    w = tw + 20
    x0, y0 = cx - w // 2, cy - TAG_H // 2
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + TAG_H), (250, 250, 250), -1)
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + TAG_H), (60, 60, 60), 2)
    pil = Image.fromarray(img[:, :, ::-1])
    ImageDraw.Draw(pil).text((cx - tw // 2, y0 + 3), name, fill=(20, 20, 20), font=font)
    img[:] = np.array(pil)[:, :, ::-1]
    return (x0, y0, w + 1, TAG_H + 1)


def draw_bubble(img, cx, cy, text):
    """White rounded speech bubble with a tail toward the cat, centered at (cx, cy)."""
    font = ImageFont.truetype(str(FONT), 15)
    tw = int(font.getlength(text))
    w, h = tw + 24, 30
    x0, y0 = cx - w // 2, cy - h // 2
    pil = Image.fromarray(img[:, :, ::-1])
    d = ImageDraw.Draw(pil)
    d.polygon([(x0 + w - 18, y0 + h - 1), (x0 + w - 6, y0 + h - 1), (x0 + w + 4, y0 + h + 9)],
              fill=(250, 250, 250), outline=(60, 60, 60))
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=10, fill=(250, 250, 250), outline=(60, 60, 60), width=2)
    d.text((x0 + 12, y0 + 5), text, fill=(20, 20, 20), font=font)
    img[:] = np.array(pil)[:, :, ::-1]
    return (x0, y0, w + 1, h + 1)


def draw_cat(img, cx, cy, name, gifts=True, bubble=None):
    """Cat whose name tag is centered at (cx, cy). Returns ground truth dict."""
    cv2.ellipse(img, (cx, cy - 42), (46, 28), 0, 180, 360, (245, 245, 245), -1)  # white body
    tag = draw_tag(img, cx, cy, name)
    icons = {}
    if gifts:
        icon = gift_icon()
        for side, (dx, dy) in (("left", OFF_LEFT), ("right", OFF_RIGHT)):
            x, y = cx + dx - ICON // 2, cy + dy - ICON // 2
            img[y:y + ICON, x:x + ICON] = icon
            icons[side] = (cx + dx, cy + dy)
    truth = {"name": name, "tag": tag, "icons": icons}
    if bubble:
        truth["bubble"] = draw_bubble(img, cx + OFF_BUBBLE[0], cy + OFF_BUBBLE[1], bubble)
        truth["said"] = bubble
    return truth


def scene(cats, w=900, h=420, seed=0):
    """cats: [(cx, cy, name)] or [(cx, cy, name, gifts)] or [(cx, cy, name, gifts, bubble_text)]"""
    img = background(w, h, seed)
    truth = [draw_cat(img, c[0], c[1], c[2], c[3] if len(c) > 3 else True, c[4] if len(c) > 4 else None)
             for c in cats]
    return img, truth
