"""One-shot analysis of the detection zone, drawn for humans (setup check, test-ocr)."""
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

import cats as cats_mod
import detect
import engine
import ocr

GREEN, RED, GRAY, ORANGE, BLUE = (0, 200, 0), (0, 0, 230), (150, 150, 150), (0, 165, 255), (230, 120, 0)
MAGENTA = (255, 0, 255)  # chat bubbles: must stand out on blue desktops too


@dataclass
class HitInfo:
    hit: detect.Hit
    name: str | None
    side: str | None
    dist: float | None
    edge: bool = False   # too close to the zone edge: the engine will not act on it


@dataclass
class Analysis:
    cats: list                       # named Cat objects
    ignored: list                    # boxes read as non-names (number box etc.)
    hits: list                       # HitInfo
    timings: dict = field(default_factory=dict)
    pending: list = field(default_factory=list)  # tags not read confidently (animation over it?)
    bubbles: list = field(default_factory=list)  # [(Box, speaker, text)]
    image: np.ndarray | None = None

    @property
    def owned(self):
        return sum(1 for h in self.hits if h.name)


def analyze(zone, tag_h, templates, offsets, threshold, max_dist, ambiguity_px,
            targets=(), read=cats_mod.read_tag, tag=None):
    t = {}
    t0 = time.perf_counter()
    boxes = detect.find_tag_boxes(zone, tag_h)
    t["tags_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    reg = cats_mod.CatRegistry(read, votes=1)  # one frame: re-reading it would add nothing
    reg.update(boxes, zone, now=0)
    t["ocr_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    raw = detect.find_templates(zone, templates, threshold) if templates else []
    t["icons_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    bubbles = []
    for b in detect.find_bubble_boxes(zone, tag_h, exclude=reg.boxes()):
        lines = [l for l in ocr.read_lines(zone[b.y + 3:b.y + b.h - 3, b.x + 3:b.x + b.w - 3]) if l.score >= 0.8]
        o = reg.owner_of(b.c, {"bubble": offsets.get("bubble")}, max_dist, 10) if offsets.get("bubble") else None
        bubbles.append((b, o.cat.name if o and o.cat.is_named else "?", " ".join(l.text for l in lines)))
    t["chat_ms"] = (time.perf_counter() - t0) * 1000

    side_offsets = {k: offsets.get(k) for k in ("left", "right")}
    hits = []
    for h in raw:
        o = reg.owner_of(h.c, side_offsets, max_dist, ambiguity_px)
        named = o and o.cat.is_named
        edge = bool(tag) and engine.owner_may_be_cut_off(h.c, side_offsets, tag, max_dist,
                                                         zone.shape[1], zone.shape[0])
        hits.append(HitInfo(h, o.cat.name if named else None, o.side if named else None,
                            o.dist if named else None, edge))
    named = reg.cats()
    a = Analysis(named, reg.ignored(), hits, t, pending=reg.pending(), bubbles=bubbles)
    a.image = draw(zone, a, side_offsets, set(ocr.normalize(x) for x in targets))
    return a


def _label(img, items):
    """Korean labels via PIL: items = [(x, y, text, bgr)]."""
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\malgun.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    for x, y, text, (b, g, r) in items:
        w = int(d.textlength(text, font=font))
        d.rectangle([x, y, x + w + 4, y + 16], fill=(0, 0, 0))
        d.text((x + 2, y), text, fill=(r, g, b), font=font)
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def draw(zone, a, offsets, targets):
    img = zone.copy()
    labels = []
    for c in a.ignored:
        b = c.box
        cv2.rectangle(img, (b.x, b.y), (b.x + b.w, b.y + b.h), GRAY, 1)
    for c in a.pending:
        b = c.box
        cv2.rectangle(img, (b.x, b.y), (b.x + b.w, b.y + b.h), BLUE, 1)
        labels.append((b.x, b.y + b.h + 2, "읽는 중(불확실)", BLUE))
    for c in a.cats:
        b = c.box
        color = GREEN if c.name in targets else RED
        cv2.rectangle(img, (b.x, b.y), (b.x + b.w, b.y + b.h), color, 2)
        labels.append((b.x, b.y + b.h + 2, f"{c.name} {c.score:.2f}", color))
        for off in offsets.values():
            if off:
                cv2.drawMarker(img, (int(b.c[0] + off[0]), int(b.c[1] + off[1])), ORANGE,
                               cv2.MARKER_CROSS, 10, 1)
    for b, speaker, text in a.bubbles:
        cv2.rectangle(img, (b.x, b.y), (b.x + b.w, b.y + b.h), MAGENTA, 2)
        owner = next((c for c in a.cats if c.name == speaker), None)
        if owner:
            cv2.line(img, b.c, owner.box.c, MAGENTA, 1)
        labels.append((b.x, max(0, b.y - 17), f"{speaker}: {text or '(못 읽음)'}", MAGENTA))
    for h in a.hits:
        x, y, w, hh = h.hit.x, h.hit.y, h.hit.w, h.hit.h
        color = (GREEN if h.name in targets else RED) if h.name else BLUE
        cv2.rectangle(img, (x, y), (x + w, y + hh), color, 2)
        owner = next((c for c in a.cats if c.name == h.name), None)
        if owner:
            cv2.line(img, h.hit.c, owner.box.c, color, 1)
        side = {"left": "L", "right": "R"}.get(h.side, "?")
        labels.append((x, max(0, y - 17), f"{side} {h.hit.score:.2f} {h.name or '주인 불명'}", color))
    return _label(img, labels)


def load_templates(cfg, base_dir):
    """Both gift icon templates, or an error naming the file (run setup again)."""
    out = []
    for key in ("gift_left", "gift_right"):
        path = base_dir / cfg["templates"][key]
        if not path.exists():
            raise FileNotFoundError(f"선물 아이콘 그림이 없습니다: {path} (보정을 다시 해 주세요)")
        img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"선물 아이콘 그림을 읽을 수 없습니다: {path} (보정을 다시 해 주세요)")
        out.append(img)
    return out


def watch(grab, cfg, templates, seconds, read=cats_mod.read_tag, on_tick=None):
    """Run the cheap loop (change detection -> tags/icons on changed area only) for `seconds`
    and measure it. grab() returns the zone image. Returns stats dict."""
    det = detect.ChangeDetector()
    reg = cats_mod.CatRegistry(read, ttl=cfg["cat_ttl_sec"])
    tag_h = cfg["tag"]["height"]
    loop_ms, ocr_calls, dirty_ticks = [], 0, 0
    counting_read = read

    def read_counted(crop, box):
        nonlocal ocr_calls
        ocr_calls += 1
        return counting_read(crop, box)

    reg.read = read_counted
    wall0, cpu0 = time.perf_counter(), time.process_time()
    end = wall0 + seconds
    while time.perf_counter() < end:
        t0 = time.perf_counter()
        zone = grab()
        rects = det.feed(zone)
        if rects:
            dirty_ticks += 1
            area = detect.pad_rect(detect.merge_rects(rects), 48, (zone.shape[1], zone.shape[0]))
            x, y, w, h = area
            sub = zone[y:y + h, x:x + w]
            boxes = detect.find_tag_boxes(sub, tag_h, offset=(x, y))
            reg.update(boxes, zone, time.perf_counter(), scanned=[area])
            if templates:
                detect.find_templates(sub, templates, cfg["match_threshold"], offset=(x, y))
        else:
            reg.update([], zone, time.perf_counter(), scanned=[])  # pending tags still re-read
        loop_ms.append((time.perf_counter() - t0) * 1000)
        if on_tick:
            on_tick(len(loop_ms), loop_ms[-1])
        time.sleep(max(0.0, cfg["interval_sec"] - (time.perf_counter() - t0)))
    wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
    return {
        "ticks": len(loop_ms), "dirty_ticks": dirty_ticks, "ocr_calls": ocr_calls,
        "avg_ms": float(np.mean(loop_ms)), "max_ms": float(np.max(loop_ms)),
        "cpu_pct": 100 * cpu / wall, "cats": [c.name for c in reg.cats()],
    }
