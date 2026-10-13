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


class BubbleReader:
    """Track bubble boxes; OCR each once after it settled (`settle_sec`, pop-in animation)."""

    def __init__(self, read=ocr.read_lines, settle_sec=0.5, ttl=2.0, min_score=0.8, max_tries=3,
                 move_tol=8):
        self.read, self.settle, self.ttl = read, settle_sec, ttl
        self.min_score, self.max_tries, self.move_tol = min_score, max_tries, move_tol
        self._bubbles: list[Bubble] = []

    def _match(self, box):
        for b in self._bubbles:
            if abs(box.c[0] - b.box.c[0]) <= self.move_tol and abs(box.c[1] - b.box.c[1]) <= self.move_tol \
                    and abs(box.w - b.box.w) <= max(4, 0.15 * b.box.w):
                return b
        return None

    def update(self, boxes, zone, now, registry, bubble_offset, max_dist, scanned=None):
        """-> [(speaker, text)] for bubbles read this call. Speaker = cat whose tag + bubble
        offset is closest (UNKNOWN when the offset was never calibrated or no cat fits)."""
        for box in boxes:
            b = self._match(box)
            if b:
                b.box, b.last_seen = box, now
            else:
                self._bubbles.append(Bubble(box, now, now))
        for b in self._bubbles:
            cx, cy = b.box.c
            if scanned is not None and not any(x <= cx < x + w and y <= cy < y + h for x, y, w, h in scanned):
                b.last_seen = now  # area unchanged -> still on screen
        self._bubbles = [b for b in self._bubbles if now - b.last_seen <= self.ttl]

        said = []
        for b in self._bubbles:
            if b.done or now - b.first_seen < self.settle or b.tries >= self.max_tries:
                continue
            owner = registry.owner_of(b.box.c, {"bubble": bubble_offset}, max_dist, 10) if bubble_offset else None
            if owner and not owner.cat.is_named:
                continue  # speaker's name still being read; read the bubble once it is known
            if owner and not registry.reverify(owner.cat, zone, now):
                continue  # the tag does not read that name right now: do not pin it on them
            b.tries += 1
            x, y, w, h = b.box.x + 3, b.box.y + 3, b.box.w - 6, b.box.h - 6
            lines = [l for l in self.read(zone[y:y + h, x:x + w]) if l.score >= self.min_score]
            if not lines:
                continue
            b.done = True
            said.append((owner.cat.name if owner else UNKNOWN, " ".join(l.text for l in lines)))
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
