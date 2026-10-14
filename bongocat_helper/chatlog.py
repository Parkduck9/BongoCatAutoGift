"""Chat: read speech bubbles once, name the speaker, drop repeats, export to Markdown."""
import datetime
import re
from dataclasses import dataclass
from pathlib import Path

import detect
import ocr

UNKNOWN = "?"


class ChatDedup:
    """A bubble stays on screen for a while: record a (speaker, text) only when it was not
    seen during the last `gap_sec`."""

    def __init__(self, gap_sec=8):
        self.gap = gap_sec
        self._last = {}

    def observe(self, speaker, text, now):
        key = (speaker, ocr.normalize(text))
        fresh = now - self._last.get(key, -1e9) >= self.gap
        self._last[key] = now
        return fresh


@dataclass
class Bubble:
    box: detect.Box
    first_seen: float
    last_seen: float
    done: bool = False
    tries: int = 0
    anchor: tuple | None = None
    owner_id: int | None = None


class BubbleReader:
    """Read settled bubbles, then block that position for four seconds."""

    POSITION_BLOCK_SEC = 4

    def __init__(self, read=ocr.read_lines, settle_sec=0.5, ttl=2.0, min_score=0.8, max_tries=3,
                 move_tol=8, on_failure=lambda name, attempt, total: None):
        self.read, self.settle, self.ttl = read, settle_sec, ttl
        self.min_score, self.max_tries, self.move_tol = min_score, max_tries, move_tol
        self.on_failure = on_failure
        self._bubbles: list[Bubble] = []
        self._blocked = []  # [(name-tag anchor, until)]; survives bubble disappearance

    def _match(self, box):
        for b in self._bubbles:
            # The tail/right-bottom attachment stays put when the text width changes.
            if abs(box.x + box.w - b.box.x - b.box.w) <= self.move_tol \
                    and abs(box.y + box.h - b.box.y - b.box.h) <= self.move_tol:
                return b
        return None

    def update(self, boxes, zone, now, registry, bubble_offset, max_dist, scanned=None):
        """-> [(speaker, text)] for bubbles read this call. Speaker = cat whose tag + bubble
        offset is closest (UNKNOWN when the offset was never calibrated or no cat fits)."""
        found = set()
        for box in boxes:
            b = self._match(box)
            if b:
                b.box, b.last_seen = box, now
            else:
                b = Bubble(box, now, now)
                self._bubbles.append(b)
            found.add(id(b))
        # A scanned area without its bubble confirms disappearance immediately.
        # Do not let subsequent unchanged frames revive an already-read bubble.
        self._bubbles = [b for b in self._bubbles if id(b) in found or (
            scanned is not None and not any(x <= b.box.c[0] < x + w and y <= b.box.c[1] < y + h
                                           for x, y, w, h in scanned))]
        for b in self._bubbles:
            cx, cy = b.box.c
            if scanned is not None and not any(x <= cx < x + w and y <= cy < y + h for x, y, w, h in scanned):
                b.last_seen = now  # area unchanged -> still on screen
        self._bubbles = [b for b in self._bubbles if now - b.last_seen <= self.ttl]

        said = []
        self._blocked = [(point, until) for point, until in self._blocked if now < until]
        for b in self._bubbles:
            owner = registry.owner_of(b.box.c, {"bubble": bubble_offset}, max_dist, 10) if bubble_offset else None
            # Once assigned, the speaker is tied to its visible tag, not bubble width.
            cat = registry.get(b.owner_id) if b.owner_id is not None else None
            if cat is None and owner is not None:
                cat = owner.cat
            if cat is not None and not cat.is_named:
                continue
            speaker = cat.name if cat is not None else UNKNOWN
            if cat is not None:
                b.anchor, b.owner_id = cat.box.c, cat.id
            elif b.anchor is None:
                b.anchor = (b.box.x + b.box.w, b.box.y + b.box.h)
            cx, cy = b.anchor
            if any(abs(cx - point[0]) <= self.move_tol and abs(cy - point[1]) <= self.move_tol
                   for point, _ in self._blocked):
                continue
            if b.done:
                b.done, b.tries = False, 0  # the position's four-second block expired
            x, y, w, h = b.box.x + 3, b.box.y + 3, b.box.w - 6, b.box.h - 6
            crop = zone[y:y + h, x:x + w]
            if now - b.first_seen < self.settle or b.tries >= self.max_tries:
                continue
            if cat is not None and not registry.reverify(cat,zone,now):
                continue
            speaker = cat.name if cat is not None else UNKNOWN
            b.tries += 1
            try:
                lines = [l for l in self.read(crop) if l.score >= self.min_score]
            except Exception:  # a failed chat read must not stop gift detection
                lines = []
            if not lines:
                self.on_failure(speaker, b.tries, self.max_tries)
                continue
            b.done = True
            self._blocked.append((b.anchor, now + self.POSITION_BLOCK_SEC))
            said.append((speaker, " ".join(l.text for l in lines)))
        return said


def export_md(rows, out_dir, title_hint=""):
    """rows: [(ts, speaker, text)] -> exports/chat_<first>[_<last>][_<hint>].md, grouped by date."""
    if not rows:
        raise ValueError("내보낼 채팅이 없습니다")
    days = {}
    for ts, speaker, text in rows:
        d = datetime.datetime.fromtimestamp(ts)
        days.setdefault(d.date().isoformat(), []).append(f"- **{d:%H:%M:%S}** {speaker}: {text}")
    dates = list(days)
    span = dates[0] if len(dates) == 1 else f"{dates[0]}_{dates[-1]}"
    hint = re.sub(r'[\\/:*?"<>|\s]+', "_", title_hint).strip("_")
    path = Path(out_dir) / (f"chat_{span}" + (f"_{hint}" if hint else "") + ".md")
    body = [f"# 채팅 기록 {span.replace('_', ' ~ ')}" + (f" ({title_hint})" if title_hint else ""), ""]
    for date, lines in days.items():
        body += [f"## {date}", "", *lines, ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body), encoding="utf-8")
    return path
