"""Design prototype only. No screen capture, OS mouse calls, or production imports."""
from collections import Counter
from dataclasses import dataclass
import unicodedata


def supported_text(text):
    for char in text:
        if not unicodedata.category(char).startswith("L"):
            continue
        if "LATIN" in unicodedata.name(char, "") or "HANGUL" in unicodedata.name(char, ""):
            continue
        return False
    return bool(text.strip())


@dataclass(frozen=True)
class Position:
    monitor: int
    anchor: tuple
    touch: tuple
    gifts: dict


@dataclass
class CatRecord:
    id: int
    position: Position
    ocr_name: str
    score: float
    manual_name: str = ""
    allow_gift: bool = False

    @property
    def name(self):
        return self.manual_name or self.ocr_name or "이름 미확인"


class CatTable:
    def __init__(self):
        self.cats = {}
        self._next_id = 1

    def scan(self, positions, read_name):
        """Retain unchanged slots. OCR new positions once; only unique names carry IDs."""
        old = self.cats
        next_cats, used, new = {}, set(), []
        for position in positions:
            same = [cat for cat in old.values() if cat.id not in used
                    and cat.position.monitor == position.monitor
                    and cat.position.anchor == position.anchor]
            if len(same) == 1:
                cat = same[0]
                cat.position = position
                used.add(cat.id)
                next_cats[cat.id] = cat
            else:
                name, score = read_name(position)
                name = name.strip()
                if not supported_text(name) or name.replace(" ", "").isdigit():
                    name = ""
                new.append((position, name, score))
        counts = Counter(name for _, name, _ in new if name)
        for position, name, score in new:
            matching = [cat for cat in old.values() if cat.id not in used and name
                        and cat.ocr_name == name and cat.position.monitor == position.monitor]
            if len(matching) == 1 and counts[name] == 1:
                cat = matching[0]
                cat.position, cat.ocr_name, cat.score = position, name, score
            else:
                cat = CatRecord(self._next_id, position, name, score)
                self._next_id += 1
            used.add(cat.id)
            next_cats[cat.id] = cat
        self.cats = next_cats

    def edit(self, cat_id, name, allow_gift):
        cat = self.cats[cat_id]
        if not supported_text(name):
            raise ValueError("이름은 영어·한국어로 입력해 주세요")
        cat.manual_name, cat.allow_gift = name.strip(), allow_gift

    def gift_action(self, cat_id, side, fresh_position, fresh_name):
        cat = self.cats[cat_id]
        if not cat.allow_gift or cat.name == "이름 미확인":
            return None
        if fresh_position.monitor != cat.position.monitor or fresh_position.anchor != cat.position.anchor:
            return None
        if not fresh_name or fresh_name not in (cat.ocr_name, cat.manual_name):
            return None
        point = fresh_position.gifts.get(side)
        return ("gift", cat_id, point) if point is not None else None

    def touch_action(self, cat_id, fresh_position):
        cat = self.cats[cat_id]
        if fresh_position.monitor != cat.position.monitor or fresh_position.anchor != cat.position.anchor:
            return None
        return ("touch", cat_id, fresh_position.touch)


class ChatRecorder:
    """One OCR call per bubble appearance; a cat's position is blocked for three seconds."""
    def __init__(self):
        self._read_events = set()
        self._blocked_until = {}
        self.logs = []

    def disappeared(self, cat_id):
        self._read_events.discard(cat_id)

    def appeared(self, cat_id, now, read_once):
        if cat_id in self._read_events or now < self._blocked_until.get(cat_id, 0):
            return None
        self._read_events.add(cat_id)
        self._blocked_until[cat_id] = now + 3
        try:
            candidates = read_once()
        except Exception:
            candidates = []
        if not candidates:
            row = (cat_id, now, "인식 실패", "failed", 0)
        else:
            text, score = max(candidates, key=lambda candidate: candidate[1])
            if not supported_text(text):
                return None
            row = (cat_id, now, text, "recognized" if score >= 0.8 else "estimated", score)
        self.logs.append(row)
        return row
