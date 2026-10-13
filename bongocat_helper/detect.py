"""Image-level detection: gift icons, name-tag boxes, changed screen tiles, icon ownership.

No OCR here; everything is cheap enough to run every loop on the changed area only.
"""
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Box:
    x: int
    y: int
    w: int
    h: int

    @property
    def c(self):
        return (self.x + self.w // 2, self.y + self.h // 2)


@dataclass
class Hit(Box):
    score: float = 0.0


@dataclass
class Owner:
    index: int      # which anchor (cat) in the list passed in
    side: str       # "left" | "right"
    dist: float


def iou(a, b):
    ix = max(0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    iy = max(0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    inter = ix * iy
    return inter / (a.w * a.h + b.w * b.h - inter) if inter else 0.0


def nms(boxes, thresh=0.3):
    kept = []
    for b in sorted(boxes, key=lambda b: -b.score):
        if all(iou(b, k) <= thresh for k in kept):
            kept.append(b)
    return kept


def _gray(img):
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


MIN_TEMPLATE_PX = 20  # never shrink a template below this; a 22x24 button stops matching at 0.5x


def find_templates(img, templates, threshold, scale=None, offset=(0, 0)):
    """All matches of any template (grayscale, downscaled for speed), merged by NMS.
    scale=None picks per template: as small as possible while the template stays
    >= MIN_TEMPLATE_PX (40px icons -> 0.5x, small real-game icons -> 1x).
    Returned boxes are in full-resolution coords + offset."""
    g = _gray(img)
    hits = []
    for tmpl in templates:
        t = _gray(tmpl)
        s = scale or min(1.0, max(0.25, MIN_TEMPLATE_PX / min(t.shape)))
        small = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s != 1 else g
        ts = cv2.resize(t, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s != 1 else t
        if ts.shape[0] > small.shape[0] or ts.shape[1] > small.shape[1]:
            continue
        res = cv2.matchTemplate(small, ts, cv2.TM_CCOEFF_NORMED)
        for y, x in zip(*np.where(res >= threshold)):
            hits.append(Hit(round(x / s) + offset[0], round(y / s) + offset[1],
                            t.shape[1], t.shape[0], float(res[y, x])))
    return nms(hits, 0.3)


def _blob(mask, cnt):
    """Filled outline of one bright blob, cropped to its bounding box."""
    x, y, w, h = cv2.boundingRect(cnt)
    filled = np.zeros((h, w), np.uint8)
    cv2.drawContours(filled, [cnt - [x, y]], -1, 1, thickness=cv2.FILLED)
    return filled.astype(bool)


def _rounded(filled):
    """Speech bubbles have rounded corners; name tags are sharp rectangles.
    True when at least 3 of the 4 bounding-box corner pixels lie outside the blob."""
    h, w = filled.shape
    return sum(not filled[y, x] for y, x in ((0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1))) >= 3


def _ink_inside(gray, filled, x, y, bright):
    """Share of dark (text) pixels inside the blob outline."""
    region = gray[y:y + filled.shape[0], x:x + filled.shape[1]]
    return float((region[filled] < bright).mean())


def find_tag_boxes(img, tag_h, tol=0.25, min_aspect=1.2, max_aspect=10.0,
                   min_fill=0.85, bright=200, offset=(0, 0)):
    """Name-tag candidates: bright, nearly rectangular blobs about `tag_h` tall.
    The white cat body is rejected by rectangularity (fill ratio), the square menu button
    by aspect. Real game tags are light gray-blue (~223 gray), hence bright=200."""
    g = _gray(img)
    _, mask = cv2.threshold(g, bright, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = g.shape
    out = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if x <= 0 or y <= 0 or x + w >= W or y + h >= H:
            continue  # cut by the image edge -> truncated tag (would be read as a new cat)
        if not (1 - tol) * tag_h <= h <= (1 + tol) * tag_h:
            continue
        if not min_aspect <= w / h <= max_aspect:
            continue
        if cv2.contourArea(cnt) / (w * h) < min_fill or _rounded(_blob(mask, cnt)):
            continue
        # the dark border sits just outside the bright interior; grow to include it
        out.append(Box(x - 2 + offset[0], y - 2 + offset[1], w + 4, h + 4))
    return out


def find_bubble_boxes(img, tag_h, exclude=(), bright=200, min_fill=0.6, ink_range=(0.04, 0.5),
                      offset=(0, 0)):
    """Chat-bubble candidates: bright, rounded blobs at least tag-high and wider than tall that
    hold text-like ink inside their outline and are not name tags (`exclude`, offset coords).
    Cat bodies are rejected by the ink check (a face is ~1% ink, text 4-50%)."""
    g = _gray(img)
    _, mask = cv2.threshold(g, bright, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = g.shape
    out = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if x <= 0 or y <= 0 or x + w >= W or y + h >= H:
            continue
        if not 0.9 * tag_h <= h <= 6 * tag_h or w < 1.5 * tag_h or w < 1.3 * h:
            continue  # round/square UI buttons (taskbar, help) are not wider than tall
        filled = _blob(mask, cnt)
        if cv2.contourArea(cnt) / (w * h) < min_fill or not _rounded(filled):
            continue
        box = Box(x + offset[0], y + offset[1], w, h)
        cx, cy = box.c
        if any(e.x <= cx < e.x + e.w and e.y <= cy < e.y + e.h for e in exclude):
            continue
        if not ink_range[0] <= _ink_inside(g, filled, x, y, bright) <= ink_range[1]:
            continue
        out.append(box)
    return out


def assign_owner(point, anchors, offsets, max_dist, ambiguity_px):
    """Which anchor (name-tag center) does an icon at `point` belong to?
    Each anchor has an expected spot per side (anchor + offset). Pick the closest spot;
    reject if too far, or if a *different* anchor is almost as close."""
    best = {}  # anchor index -> (dist, side)
    for i, (ax, ay) in enumerate(anchors):
        for side, off in offsets.items():
            if off is None:
                continue
            d = float(np.hypot(point[0] - (ax + off[0]), point[1] - (ay + off[1])))
            if i not in best or d < best[i][0]:
                best[i] = (d, side)
    if not best:
        return None
    ranked = sorted(best.items(), key=lambda kv: kv[1][0])
    i, (d, side) = ranked[0]
    if d > max_dist:
        return None
    if len(ranked) > 1 and ranked[1][1][0] - d < ambiguity_px:
        return None
    return Owner(i, side, d)


class ChangeDetector:
    """Which parts of the screen changed since last frame (downscaled grayscale, per tile)."""

    def __init__(self, tile=64, factor=4, threshold=8):
        self.tile, self.factor, self.threshold = tile, factor, threshold
        self.prev = None

    def feed(self, img):
        small = cv2.resize(_gray(img), None, fx=1 / self.factor, fy=1 / self.factor,
                           interpolation=cv2.INTER_AREA).astype(np.int16)
        h, w = img.shape[:2]
        if self.prev is None or self.prev.shape != small.shape:
            self.prev = small
            return [(0, 0, w, h)]
        diff = np.abs(small - self.prev)
        self.prev = small
        st = max(1, self.tile // self.factor)
        rects = []
        for ty in range(0, small.shape[0], st):
            for tx in range(0, small.shape[1], st):
                if diff[ty:ty + st, tx:tx + st].mean() > self.threshold:
                    x, y = tx * self.factor, ty * self.factor
                    rects.append((x, y, min(self.tile, w - x), min(self.tile, h - y)))
        return rects


def merge_rects(rects):
    x0 = min(r[0] for r in rects)
    y0 = min(r[1] for r in rects)
    x1 = max(r[0] + r[2] for r in rects)
    y1 = max(r[1] + r[3] for r in rects)
    return (x0, y0, x1 - x0, y1 - y0)


def pad_rect(rect, pad, size):
    """Grow rect by `pad` on every side, clamped to (width, height)."""
    x, y, w, h = rect
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(size[0], x + w + pad), min(size[1], y + h + pad)
    return (x0, y0, x1 - x0, y1 - y0)
