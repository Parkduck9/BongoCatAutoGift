"""Setup (calibration): the user drags boxes on one cat; we derive everything else.

compute()/verify() are pure and tested; run_interactive() is the thin OpenCV UI on top.
Coordinates: `rects` are in frame coords (frame = whole monitor). Offsets are relative to
the name-tag center, so they hold for every cat at any height.
"""
from dataclasses import dataclass, field
import sys

import cv2
import numpy as np

import cats as cats_mod
import detect

STEPS = [  # key, required, Korean instruction
    ("zone", True, "1/6 감지 영역: 고양이가 나타날 수 있는 범위 전체 (가장 높은 말풍선 ~ 작업표시줄 위)"),
    ("left", True, "2/6 한 고양이의 왼쪽 1000 선물 아이콘 (그림만, 딱 맞게)"),
    ("right", True, "3/6 같은 고양이의 오른쪽 1000 선물 아이콘"),
    ("tag", True, "4/6 같은 고양이의 이름표 (흰 박스 전체)"),
    ("bubble", False, "5/6 (선택) 같은 고양이의 말풍선: 없으면 Esc"),
    ("number", False, "6/6 (선택) 같은 고양이의 숫자칸: 없으면 Esc"),
]
BUBBLE_STEPS = [
    ("bubble", True, "1/2 말풍선 하나 (흰 둥근 박스 전체)"),
    ("tag", True, "2/2 그 말풍선을 띄운 고양이의 이름표"),
]
MIN_ICON = 8


class SetupError(ValueError):
    pass


@dataclass
class SetupResult:
    region: list
    offsets: dict
    tag: dict
    templates: dict = field(default_factory=dict)   # name -> BGR image


@dataclass
class Report:
    tags: int
    icons: int
    owned: int
    names: list
    image: np.ndarray | None = None


def _center(r):
    return (r[0] + r[2] / 2, r[1] + r[3] / 2)


def _inside(inner, outer):
    return (inner[0] >= outer[0] and inner[1] >= outer[1]
            and inner[0] + inner[2] <= outer[0] + outer[2] and inner[1] + inner[3] <= outer[1] + outer[3])


def _tag_interior(frame, rect):
    """Bright interior of the name tag the user dragged around -> (x, y, w, h) in frame coords."""
    x, y, w, h = rect
    crop = cv2.cvtColor(frame[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise SetupError("tag: 이름표 안에서 흰 박스를 찾지 못했습니다")
    bx, by, bw, bh = cv2.boundingRect(max(contours, key=cv2.contourArea))
    return (x + bx, y + by, bw, bh)


def compute(frame, rects):
    for key, required, _ in STEPS:
        r = rects.get(key)
        if required and (not r or r[2] < MIN_ICON or r[3] < MIN_ICON):
            raise SetupError(f"{key}: 영역이 비었거나 너무 작습니다")
    zone = [int(v) for v in rects["zone"]]
    if zone[2] < 50 or zone[3] < 50:
        raise SetupError("zone: 감지 영역이 너무 작습니다")
    for key in ("left", "right", "tag", "bubble", "number"):
        r = rects.get(key)
        if r and r[2] > 0 and not _inside(r, zone):
            raise SetupError(f"{key}: 감지 영역(zone) 밖에 있습니다")

    tx, ty, tw, th = _tag_interior(frame, [int(v) for v in rects["tag"]])
    tag_c = (tx + tw / 2, ty + th / 2)

    def off(key):
        r = rects.get(key)
        if not r or r[2] <= 0 or r[3] <= 0:
            return None
        c = _center(r)
        return (round(c[0] - tag_c[0]), round(c[1] - tag_c[1]))

    def crop(key):
        x, y, w, h = (int(v) for v in rects[key])
        return frame[y:y + h, x:x + w].copy()

    for key in ("left", "right"):
        x, y, w, h = (int(v) for v in rects[key])
        gray = cv2.cvtColor(frame[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)
        if cv2.GaussianBlur(gray, (5, 5), 0).std() < 12:  # blur: noise fades, icon edges stay
            raise SetupError(f"{key}: 선택한 곳이 거의 단색입니다. 선물 아이콘 그림을 정확히 드래그해 주세요")

    return SetupResult(
        region=zone,
        offsets={k: off(k) for k in ("left", "right", "bubble", "number")},
        tag={"height": th, "aspect": round(tw / th, 2)},
        templates={"gift_left": crop("left"), "gift_right": crop("right")},
    )


def verify(frame, res, read=cats_mod.read_tag, threshold=0.85, max_dist=60, ambiguity_px=20):
    """Run detection on the zone with the new settings; draw what was found."""
    import debug

    x, y, w, h = res.region
    a = debug.analyze(frame[y:y + h, x:x + w], res.tag["height"],
                      [res.templates["gift_left"], res.templates["gift_right"]], res.offsets,
                      threshold, max_dist, ambiguity_px, read=read)
    return Report(len(a.cats), len(a.hits), a.owned, [c.name for c in a.cats], a.image)


def apply(cfg, res, monitor, templates_dir):
    """Write templates to disk and settings into cfg (caller saves cfg)."""
    templates_dir.mkdir(exist_ok=True)
    for name, img in res.templates.items():
        path = templates_dir / f"{name}.png"
        cv2.imwrite(str(path), img)
        cfg["templates"][name] = f"templates/{name}.png"
    cfg["monitor"] = monitor
    cfg["region"] = res.region
    cfg["offsets"] = res.offsets
    cfg["tag"] = res.tag
    return cfg


# ---------------------------------------------------------------- interactive UI

def _banner(img, text):
    """Korean instruction bar on top (cv2.putText cannot draw Hangul)."""
    from PIL import Image, ImageDraw, ImageFont

    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\malgun.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    draw.rectangle([0, 0, pil.width, 63], fill=(20, 20, 20))
    draw.text((12, 6), text, fill=(255, 220, 80), font=font)
    draw.text((12, 36), "드래그 후 Enter/Space = 확정 · c 또는 Esc = 건너뛰기(선택 항목)", fill=(220, 220, 220), font=font)
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def _fit(img, max_w, max_h):
    """Scale to fit the window; small zones are enlarged (up to 3x) so icons are easy to drag."""
    scale = min(3.0, max_w / img.shape[1], (max_h - 64) / img.shape[0])
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_NEAREST
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=interp), scale


def compute_bubble_offset(frame, rects):
    """Bubble center relative to its cat's tag center (same reference as the icon offsets)."""
    for key in ("bubble", "tag"):
        r = rects.get(key)
        if not r or r[2] < MIN_ICON or r[3] < MIN_ICON:
            raise SetupError(f"{key}: 영역이 비었거나 너무 작습니다")
    tx, ty, tw, th = _tag_interior(frame, [int(v) for v in rects["tag"]])
    bx, by = _center(rects["bubble"])
    return [round(bx - (tx + tw / 2)), round(by - (ty + th / 2))]


def select_rects(frame, max_w=1600, max_h=900, steps=STEPS, view_rect=None):
    """Ask the user for each step's box. Returns rects in frame coords.
    After the zone is chosen (or from the start, given `view_rect`), only that part of the
    screen is shown, enlarged."""
    win = "bongo setup"
    rects = {}
    view, origin = frame, (0, 0)
    if view_rect:
        x, y, w, h = view_rect
        view, origin = frame[y:y + h, x:x + w], (x, y)
    for key, required, text in steps:
        shown, scale = _fit(view, max_w, max_h)
        canvas = _banner(np.vstack([np.zeros((64, shown.shape[1], 3), np.uint8), shown]), text)
        while True:
            print(text)
            print(f"보정 단계 시작: {key}", file=sys.stderr, flush=True)
            r = cv2.selectROI(win, canvas, showCrosshair=True, fromCenter=False)
            print(f"보정 선택 결과: {key} {r}", file=sys.stderr, flush=True)
            if r[2] > 0 and r[3] > 0 and r[1] >= 64:
                rects[key] = [round(r[0] / scale) + origin[0], round((r[1] - 64) / scale) + origin[1],
                              round(r[2] / scale), round(r[3] / scale)]
                break
            if not required:
                rects[key] = None
                break
            print("  필수 항목입니다. 다시 드래그해 주세요.")
        if key == "zone":
            x, y, w, h = rects["zone"]
            view, origin = frame[y:y + h, x:x + w], (x, y)
    cv2.destroyWindow(win)
    return rects


def show(img, title="bongo setup check", max_w=1600, max_h=900):
    scale = min(1.0, max_w / img.shape[1], max_h / img.shape[0])
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    cv2.imshow(title, img)
    print("확인 창: 아무 키나 누르면 닫힙니다.")
    cv2.waitKey(0)
    cv2.destroyWindow(title)
