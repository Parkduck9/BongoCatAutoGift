"""Korean OCR: RapidOCR (PaddleOCR korean PP-OCRv5 mobile, onnxruntime), recognition only.

Callers pass already-cropped boxes (name tag, chat bubble), so the slow text-detection
model is skipped: ~30 ms per line. Multi-line crops are split by ink-row projection.
Windows built-in OCR was measured at <=70% on 2-3 syllable names, RapidOCR rec at 30/30.
"""
import re
import threading
import unicodedata
from dataclasses import dataclass

import cv2
import numpy as np

from config import BASE_DIR, RESOURCE_DIR

MODEL_FILE = "korean_PP-OCRv5_rec_mobile.onnx"  # ~12 MB; bundled in the .exe, else downloaded on first use
MODEL_DIR = RESOURCE_DIR / "models" if (RESOURCE_DIR / "models" / MODEL_FILE).exists() else BASE_DIR / "models"
MIN_SCORE = 0.5
MARGIN = 0.25       # margin around trimmed ink, x text height (measured best: 0/50 errors, 12-36px)
WORD_GAP = 0.4      # word gap must exceed this x line height (and 2x the median gap); tuned: 71/72

_NOT_WORD = re.compile(r"[^0-9A-Za-z가-힣ㄱ-ㆎ]")
_engine = None
_lock = threading.Lock()  # onnx session is shared; serialize calls


@dataclass
class Line:
    text: str
    x: int
    y: int
    w: int
    h: int
    score: float = 1.0

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2


def is_numeric(s):
    """Counter/timer text like '156 758', '03:29', or OCR junk around digits ('155580|')."""
    core = _NOT_WORD.sub("", s)
    return core.isdigit()


def normalize(s):
    return "".join(unicodedata.normalize("NFC", s).split())


def ink_mask(img_bgr):
    """Boolean mask of text pixels; works for dark-on-light and light-on-dark."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if binary.mean() > 0.5:  # most pixels "ink" -> background is the dark side
        binary = 1 - binary
    if gray.max() - gray.min() < 30:  # flat image, no text
        binary[:] = 0
    return binary.astype(bool)


def split_lines(img_bgr, min_gap=2):
    """Text line boxes [(x, y, w, h)] from row/column ink projection, top to bottom."""
    mask = ink_mask(img_bgr)
    rows = mask.any(axis=1)
    boxes, y = [], 0
    while y < len(rows):
        if not rows[y]:
            y += 1
            continue
        start = y
        gap = 0
        while y < len(rows) and gap < min_gap:
            gap = 0 if rows[y] else gap + 1
            y += 1
        end = y - gap
        cols = np.flatnonzero(mask[start:end].any(axis=0))
        boxes.append((int(cols[0]), start, int(cols[-1] - cols[0] + 1), end - start))
    return boxes


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr import RapidOCR
        from rapidocr.utils.typings import LangRec, ModelType, OCRVersion

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        _engine = RapidOCR(params={
            "Global.use_det": False, "Global.use_cls": False,
            "Global.log_level": "error", "Global.model_root_dir": str(MODEL_DIR),
            "Rec.lang_type": LangRec.KOREAN, "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.model_type": ModelType.MOBILE,
            # default (all cores) leaves worker threads spin-waiting: measured 8.6 s CPU in the
            # 3 s after one call. One thread: 35 ms per call, 0 idle CPU.
            "EngineConfig.onnxruntime.intra_op_num_threads": 1,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        })
    return _engine


def ensure_ready():
    """Load (and on first run download) the model up front."""
    _get_engine()


def _normalized(img_bgr, mask):
    """Trim to ink, then add a margin proportional to text height in the background color.
    The model is sensitive to margins; this makes tight and loose crops look the same."""
    ys, xs = np.flatnonzero(mask.any(axis=1)), np.flatnonzero(mask.any(axis=0))
    tight = img_bgr[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1]
    bg = np.median(img_bgr[~mask], axis=0) if (~mask).any() else (255, 255, 255)
    m = max(1, int(MARGIN * tight.shape[0]))
    return cv2.copyMakeBorder(tight, m, m, m, m, cv2.BORDER_CONSTANT, value=[int(v) for v in bg])


def recognize(img_bgr):
    """Single-line crop -> (text, score). No spaces are inferred."""
    mask = ink_mask(img_bgr)
    if not mask.any():
        return "", 0.0
    with _lock:
        out = _get_engine()(_normalized(img_bgr, mask))
    text = "".join(out.txts or ()).strip()
    score = float(min(out.scores)) if out.scores else 0.0
    return text, score


def word_gaps(line_mask, height):
    """Centers (x) of gaps between words: blank column runs that are clearly wider than
    the usual gap between syllables."""
    cols = line_mask.any(axis=0)
    ink = np.flatnonzero(cols)
    if ink.size == 0:
        return []
    gaps, start = [], None
    for x in range(ink[0], ink[-1] + 1):
        if not cols[x] and start is None:
            start = x
        elif cols[x] and start is not None:
            gaps.append((start, x))
            start = None
    if not gaps:
        return []
    widths = np.array([b - a for a, b in gaps])
    limit = max(WORD_GAP * height, 2 * np.median(widths))
    return [(a + b) / 2 for (a, b), w in zip(gaps, widths) if w > limit]


def insert_spaces(text, gap_xs, x0, x1):
    """Put a space at each gap, mapped onto the text by relative position
    (Korean syllables are roughly equal width)."""
    if not text or x1 <= x0:
        return text
    chars = list(text.replace(" ", ""))
    cuts = sorted({min(len(chars) - 1, max(1, round((g - x0) / (x1 - x0) * len(chars)))) for g in gap_xs})
    for i in reversed(cuts):
        chars.insert(i, " ")
    return "".join(chars)


def read_lines(img_bgr, offset=(0, 0)):
    """Crop (possibly multi-line) -> [Line] in crop coords + offset. Numeric/low-score dropped."""
    mask = ink_mask(img_bgr)
    out = []
    for x, y, w, h in split_lines(img_bgr):
        text, score = recognize(img_bgr[y:y + h, x:x + w])
        if not text or score < MIN_SCORE or is_numeric(text):
            continue
        if " " not in text:  # the model sometimes emits spaces itself; trust those
            text = insert_spaces(text, word_gaps(mask[y:y + h, x:x + w], h), 0, w)
        out.append(Line(text, x + offset[0], y + offset[1], w, h, score))
    return out
