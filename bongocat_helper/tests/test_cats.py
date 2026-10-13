import pytest

import cats
import detect
import scene
from test_detect import CLOSE_AND_STAGGERED, DIFF_HEIGHT, SAME_HEIGHT


class FakeOcr:
    """Returns names by tag position from the scene truth; counts calls."""

    def __init__(self, truth):
        self.truth = truth
        self.calls = 0

    def __call__(self, crop, box):
        self.calls += 1
        for t in self.truth:
            x, y, w, h = t["tag"]
            if abs(box.x - x) <= 4 and abs(box.y - y) <= 4:
                return t["name"], 0.99
        return "156 758", 0.99


def boxes_of(img):
    return detect.find_tag_boxes(img, tag_h=scene.TAG_H)


def settle(reg, boxes, img, start=0):
    """Two frames: enough for 2 agreeing reads."""
    reg.update(boxes, img, now=start)
    reg.update(boxes, img, now=start + 1)


def test_registry_confirms_after_two_reads_then_stops_reading():
    img, truth = scene.scene(SAME_HEIGHT)
    ocr = FakeOcr(truth)
    reg = cats.CatRegistry(ocr, move_tol=8, ttl=10)
    reg.update(boxes_of(img), img, now=0)
    assert reg.cats() == []                       # one read is not enough
    for t in (1, 2, 3, 4):
        reg.update(boxes_of(img), img, now=t)
    assert sorted(c.name for c in reg.cats()) == ["리네", "민지", "철수"]
    assert ocr.calls == 6


def test_registry_follows_small_moves_without_ocr():
    img, truth = scene.scene(SAME_HEIGHT)
    ocr = FakeOcr(truth)
    reg = cats.CatRegistry(ocr, move_tol=8, ttl=10)
    settle(reg, boxes_of(img), img)
    moved = [detect.Box(b.x + 5, b.y - 3, b.w, b.h) for b in boxes_of(img)]
    reg.update(moved, img, now=2)
    assert ocr.calls == 6
    assert sorted(c.box.x for c in reg.cats()) == sorted(b.x for b in moved)


def test_registry_numeric_box_is_ignored_and_not_reread():
    img, truth = scene.scene(SAME_HEIGHT)
    ocr = FakeOcr(truth)
    reg = cats.CatRegistry(ocr, move_tol=8, ttl=10)
    stray = detect.Box(10, 10, 60, 26)
    settle(reg, boxes_of(img) + [stray], img)
    reg.update(boxes_of(img) + [stray], img, now=2)
    assert len(reg.cats()) == 3
    assert len(reg.ignored()) == 1
    assert ocr.calls == 8


class Sequence:
    def __init__(self, results):
        self.results = list(results)

    def __call__(self, crop, box):
        return self.results.pop(0)


def test_animation_misreads_never_confirm_and_clean_reads_win():
    box = detect.Box(100, 100, 80, 26)
    img = scene.background()
    reg = cats.CatRegistry(Sequence([("우리네", 0.93), ("리네오", 0.81), ("리네", 0.999),
                                     ("우리네", 0.93), ("리네", 0.999)]), retry_sec=0)
    for t in range(4):
        reg.update([box], img, now=t)
        assert reg.cats() == []
    reg.update([box], img, now=4)
    assert [c.name for c in reg.cats()] == ["리네"]


def test_pending_neighbor_blocks_misattribution():
    # A is named, B (right next to it) is still pending: B's icon must not go to A
    a_box, b_box = detect.Box(100, 300, 60, 26), detect.Box(200, 300, 60, 26)
    img = scene.background()
    reg = cats.CatRegistry(lambda crop, box: ("리네", 0.99) if box.x == 100 else ("", 0.0))
    settle(reg, [a_box, b_box], img)
    assert [c.name for c in reg.cats()] == ["리네"] and len(reg.pending()) == 1
    b_left_spot = (b_box.c[0] + scene.OFF_LEFT[0], b_box.c[1] + scene.OFF_LEFT[1])
    offsets = {"left": scene.OFF_LEFT, "right": scene.OFF_RIGHT}
    owner = reg.owner_of(b_left_spot, offsets, 30, 10)
    assert owner.cat.state == cats.PENDING and not owner.cat.is_named


def test_registry_expires_only_cats_inside_scanned_area():
    img, truth = scene.scene(SAME_HEIGHT)
    reg = cats.CatRegistry(FakeOcr(truth), move_tol=8, ttl=5)
    settle(reg, boxes_of(img), img)
    left_half = (0, 0, 300, 420)
    reg.update([], img, now=10, scanned=[left_half])  # 리네 scanned and missing
    assert sorted(c.name for c in reg.cats()) == ["민지", "철수"]


@pytest.mark.parametrize("layout", [SAME_HEIGHT, DIFF_HEIGHT, CLOSE_AND_STAGGERED])
def test_end_to_end_icons_to_names(layout):
    img, truth = scene.scene(layout)
    reg = cats.CatRegistry(FakeOcr(truth), move_tol=8, ttl=10)
    settle(reg, boxes_of(img), img)
    icon = scene.gift_icon()
    found = set()
    for hit in detect.find_templates(img, [icon, icon], 0.85, 0.5):
        owner = reg.owner_of(hit.c, {"left": scene.OFF_LEFT, "right": scene.OFF_RIGHT}, 30, 10)
        found.add((owner.cat.name, owner.side))
    assert found == {(t["name"], s) for t in truth for s in ("left", "right")}


@pytest.mark.skipif(not scene.FONT.exists(), reason="font missing")
@pytest.mark.parametrize("layout", [SAME_HEIGHT, DIFF_HEIGHT, CLOSE_AND_STAGGERED])
def test_real_ocr_reads_tag_crops(layout):
    img, truth = scene.scene(layout)
    reg = cats.CatRegistry(move_tol=8, ttl=10)  # default reader = RapidOCR
    settle(reg, boxes_of(img), img)
    assert sorted(c.name for c in reg.cats()) == sorted(t["name"] for t in truth)


REAL = scene.Path(__file__).parent / "fixtures" / "real_zone_rine.png"


@pytest.mark.skipif(not REAL.exists(), reason="fixture missing")
def test_real_game_crop_reads_name_and_ignores_number_box():
    """Real screenshot (2026-10-12): own bat cat with '157 444' number box + menu button,
    other player's purple cat with light gray-blue tag '리네'."""
    import cv2

    img = cv2.imread(str(REAL))
    boxes = detect.find_tag_boxes(img, tag_h=20)
    assert len(boxes) == 2                      # name tag + number box; menu button rejected
    reg = cats.CatRegistry()
    settle(reg, boxes, img)
    named = reg.cats()
    assert len(reg.ignored()) == 1              # '157 444' read as numeric
    assert [c.name for c in named] == ["리네"]
    assert named[0].score > 0.95


def test_pending_tag_is_reread_when_screen_goes_static():
    box = detect.Box(100, 100, 80, 26)
    img = scene.background()
    reg = cats.CatRegistry(Sequence([("우리네", 0.93), ("리네", 0.999), ("리네", 0.999)]), retry_sec=0)
    reg.update([box], img, now=0)                  # changed area: read (spoiled)
    reg.update([], img, now=1, scanned=[])         # nothing changed, still re-read
    reg.update([], img, now=2, scanned=[])
    assert [c.name for c in reg.cats()] == ["리네"]


def test_partial_box_inside_known_tag_is_not_a_new_cat():
    img, truth = scene.scene(SAME_HEIGHT)
    ocr = FakeOcr(truth)
    reg = cats.CatRegistry(ocr)
    settle(reg, boxes_of(img), img)
    full, *others = boxes_of(img)
    half = detect.Box(full.x + full.w // 3, full.y, full.w // 2, full.h)
    reg.update([half, *others], img, now=2)
    assert len(reg.cats()) == 3 and ocr.calls == 6
    assert any(c.box == full for c in reg.cats())   # kept the full box
