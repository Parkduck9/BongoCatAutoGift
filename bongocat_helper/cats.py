"""Registry of cats on screen, keyed by name-tag position.

A tag's name is confirmed only after `votes` high-confidence reads agree. The cat's own
animation (paw motion lines) sometimes draws over the tag: on the real game such frames
read '우리네' (0.93) / '리네오' (0.81) while clean frames read '리네' (0.999).
Unconfirmed cats get re-read on later frames and never receive gifts.
"""
from collections import Counter
from dataclasses import dataclass, field

import detect
import ocr as ocr_mod

PENDING, NAMED, IGNORED = "pending", "named", "ignored"
NUMERIC = "<numeric>"


@dataclass
class Cat:
    box: detect.Box
    last_seen: float
    id: int = 0
    state: str = PENDING
    name: str | None = None
    score: float = 0.0
    reads: list = field(default_factory=list)   # [(normalized text or NUMERIC, score)]
    last_read: float = -1e9
    missing: bool = False   # its area was scanned and the tag was not there

    @property
    def is_named(self):
        return self.state == NAMED and not self.missing


@dataclass
class CatOwner:
    cat: Cat
    side: str
    dist: float


BORDER = 3  # tag boxes include their dark outline; it must not reach OCR


def tag_interior(frame, box):
    """Inside of the tag without its outline. Measured on the real game: with the outline
    Otsu picks border-vs-rest and confidence drops to 0.75; without it 0.999."""
    s = BORDER if min(box.w, box.h) > 2 * BORDER + 4 else 0
    return frame[max(0, box.y + s):box.y + box.h - s, max(0, box.x + s):box.x + box.w - s]


def read_tag(crop, box):
    """Default tag reader: RapidOCR on the box interior."""
    return ocr_mod.recognize(crop)


class CatRegistry:
    def __init__(self, read=read_tag, move_tol=8, ttl=10, confirm_score=0.97, votes=2,
                 retry_sec=0.5, max_reads=12, numeric_score=0.6):
        self.read, self.move_tol, self.ttl = read, move_tol, ttl
        self.confirm_score, self.votes, self.numeric_score = confirm_score, votes, numeric_score
        self.retry_sec, self.max_reads = retry_sec, max_reads
        self._cats: list[Cat] = []
        self._next_id = 1

    def cats(self):
        return [c for c in self._cats if c.is_named]

    def pending(self):
        return [c for c in self._cats if c.state == PENDING]

    def boxes(self):
        """Every known tag-like box (named, pending, ignored): never a chat bubble."""
        return [c.box for c in self._cats]

    def get(self, cat_id):
        return next((c for c in self._cats if c.id == cat_id), None)

    def reverify(self, cat, frame, now):
        """Read a named tag again right before acting on it. True only for a confident read of
        the same name. A confident different name means another player took this spot: the
        cat goes back to pending with that read as its first vote."""
        text, score = self.read(tag_interior(frame, cat.box), cat.box)
        name = ocr_mod.normalize(text)
        if score < self.confirm_score or not name or ocr_mod.is_numeric(text):
            return False
        if name == cat.name:
            return True
        cat.state, cat.name, cat.reads, cat.last_read = PENDING, None, [(name, score)], now
        return False

    def ignored(self):
        return [c for c in self._cats if c.state == IGNORED]

    def _match(self, box):
        bx, by = box.c
        for cat in self._cats:
            cx, cy = cat.box.c
            if abs(bx - cx) <= self.move_tol and abs(by - cy) <= self.move_tol \
                    and abs(box.w - cat.box.w) <= max(4, 0.15 * cat.box.w):
                return cat
        for cat in self._cats:  # overlapping an existing tag = same cat, never a duplicate
            b = cat.box
            if b.x <= bx < b.x + b.w and b.y <= by < b.y + b.h:
                return cat
        return None

    def _read(self, cat, frame, now):
        text, score = self.read(tag_interior(frame, cat.box), cat.box)
        cat.last_read = now
        numeric = ocr_mod.is_numeric(text)
        # counters are never gift targets, so a lower bar is safe (real box read at 0.93-0.97)
        need = self.numeric_score if numeric else self.confirm_score
        if score < need or not ocr_mod.normalize(text):
            cat.reads.append((None, score))
        else:
            cat.reads.append((NUMERIC if numeric else ocr_mod.normalize(text), score))
        votes = Counter(k for k, _ in cat.reads if k is not None)
        if votes:
            key, n = votes.most_common(1)[0]
            if n >= self.votes:
                cat.state = IGNORED if key == NUMERIC else NAMED
                cat.name = None if key == NUMERIC else key
                cat.score = max(s for k, s in cat.reads if k == key)
        cat.reads = cat.reads[-self.max_reads:]

    def update(self, boxes, frame, now, scanned=None):
        """boxes: tag boxes found in `scanned` rects of `frame` (None = whole frame scanned).
        Cats outside the scanned area are kept as-is (nothing changed there)."""
        found = set()
        for box in boxes:
            cat = self._match(box)
            if cat:
                if abs(box.w - cat.box.w) <= max(4, 0.15 * cat.box.w):
                    cat.box = box  # follow moves; keep the old box if this one looks partial
            else:
                cat = Cat(box, now, self._next_id)
                self._next_id += 1
                self._cats.append(cat)
            cat.last_seen, cat.missing = now, False
            found.add(cat.id)

        def inside_scan(cat):
            if scanned is None:
                return True
            cx, cy = cat.box.c
            return any(x <= cx < x + w and y <= cy < y + h for x, y, w, h in scanned)

        for cat in self._cats:
            if cat.id in found:
                continue
            if inside_scan(cat):
                cat.missing = True        # looked there, not found: not an owner any more
            elif not cat.missing:
                cat.last_seen = now       # area unchanged -> still there
        self._cats = [c for c in self._cats if now - c.last_seen <= self.ttl]
        # pending tags are re-read from the current frame even if their area did not change:
        # the animation that spoiled earlier reads may have stopped, leaving a clean, static tag
        for cat in self._cats:
            if cat.state == PENDING and not cat.missing and now - cat.last_read >= self.retry_sec:
                self._read(cat, frame, now)

    def owner_of(self, point, offsets, max_dist, ambiguity_px):
        """Owner among named, pending AND missing cats (a neighbor whose tag is unreadable or
        hidden for a moment must still count, or its icon could be pinned on a named cat next to
        it). None = nobody fits. Such an owner has `owner.cat.is_named` False: callers wait."""
        anchors = [c for c in self._cats if c.state != IGNORED]
        o = detect.assign_owner(point, [c.box.c for c in anchors], offsets, max_dist, ambiguity_px)
        return CatOwner(anchors[o.index], o.side, o.dist) if o else None
