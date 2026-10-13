import cv2
import numpy as np
import pytest

import detect
import scene

OFFSETS = {"left": scene.OFF_LEFT, "right": scene.OFF_RIGHT}

SAME_HEIGHT = [(150, 380, "리네"), (450, 380, "철수"), (750, 380, "민지")]
DIFF_HEIGHT = [(150, 390, "리네"), (450, 220, "철수"), (750, 320, "민지")]
CLOSE_AND_STAGGERED = [(200, 380, "리네"), (300, 300, "철수"), (600, 360, "민지")]


def test_nms_keeps_best_of_overlaps():
    boxes = [detect.Hit(0, 0, 10, 10, 0.9), detect.Hit(2, 1, 10, 10, 0.95), detect.Hit(50, 0, 10, 10, 0.8)]
    kept = detect.nms(boxes, 0.3)
    assert [(b.x, b.score) for b in kept] == [(2, 0.95), (50, 0.8)]


@pytest.mark.parametrize("layout", [SAME_HEIGHT, DIFF_HEIGHT, CLOSE_AND_STAGGERED])
def test_find_templates_finds_all_six_icons(layout):
    img, truth = scene.scene(layout)
    icon = scene.gift_icon()
    hits = detect.find_templates(img, [icon, icon], threshold=0.85, scale=0.5)
    expected = sorted(c for t in truth for c in t["icons"].values())
    got = sorted(h.c for h in hits)
    assert len(got) == 6
    for (gx, gy), (ex, ey) in zip(got, expected):
        assert abs(gx - ex) <= 2 and abs(gy - ey) <= 2


def test_find_templates_nothing_on_empty_desktop():
    assert detect.find_templates(scene.background(), [scene.gift_icon()], 0.85, 0.5) == []


@pytest.mark.parametrize("layout", [SAME_HEIGHT, DIFF_HEIGHT, CLOSE_AND_STAGGERED])
def test_find_tag_boxes(layout):
    img, truth = scene.scene(layout)
    boxes = detect.find_tag_boxes(img, tag_h=scene.TAG_H)
    got = sorted((b.x, b.y) for b in boxes)
    expected = sorted((t["tag"][0], t["tag"][1]) for t in truth)
    assert len(got) == len(expected)
    for (gx, gy), (ex, ey) in zip(got, expected):
        assert abs(gx - ex) <= 3 and abs(gy - ey) <= 3


def tag_centers(truth):
    return [(t["tag"][0] + t["tag"][2] // 2, t["tag"][1] + t["tag"][3] // 2) for t in truth]


@pytest.mark.parametrize("layout", [SAME_HEIGHT, DIFF_HEIGHT, CLOSE_AND_STAGGERED])
def test_assign_owner_every_icon_to_its_own_cat(layout):
    _, truth = scene.scene(layout)
    centers = tag_centers(truth)
    for i, t in enumerate(truth):
        for side, c in t["icons"].items():
            owner = detect.assign_owner(c, centers, OFFSETS, max_dist=30, ambiguity_px=10)
            assert owner is not None
            assert (owner.index, owner.side) == (i, side)


def test_assign_owner_rejects_far_hit():
    assert detect.assign_owner((10, 10), [(500, 300)], OFFSETS, max_dist=30, ambiguity_px=10) is None


def test_assign_owner_rejects_ambiguous_between_two_cats():
    # cat B's left spot is 4 px away from cat A's right spot; a hit in between is ambiguous
    a, b = (200, 300), (200 + 68 + 4, 300)
    hit = (200 + 34 + 2, 300 - 96)
    assert detect.assign_owner(hit, [a, b], OFFSETS, max_dist=30, ambiguity_px=10) is None


def test_change_detector_first_frame_all_dirty_then_only_changed_tile():
    det = detect.ChangeDetector(tile=64, factor=4, threshold=8)
    img = scene.background()
    full = det.feed(img)
    assert full == [(0, 0, img.shape[1], img.shape[0])]
    assert det.feed(img.copy()) == []
    changed = img.copy()
    cv2.rectangle(changed, (600, 100), (640, 140), (255, 255, 255), -1)
    rects = det.feed(changed)
    assert rects and all(r[0] <= 600 + 40 and r[0] + r[2] >= 600 for r in rects)
    assert sum(r[2] * r[3] for r in rects) < img.shape[0] * img.shape[1] / 4


def test_merge_rects_and_pad():
    assert detect.merge_rects([(0, 0, 10, 10), (5, 5, 10, 10)]) == (0, 0, 15, 15)
    assert detect.pad_rect((10, 10, 5, 5), 4, (100, 100)) == (6, 6, 13, 13)
    assert detect.pad_rect((0, 0, 5, 5), 4, (100, 100)) == (0, 0, 9, 9)


def test_find_tag_boxes_drops_tags_cut_by_image_edge():
    img, truth = scene.scene(SAME_HEIGHT)
    x, y, w, h = truth[0]["tag"]
    cut = img[:, x + w // 2:]                     # left half of the first tag is outside
    assert len(detect.find_tag_boxes(cut, scene.TAG_H)) == 2


REAL = scene.Path(__file__).parent / "fixtures" / "real_zone_rine.png"


@pytest.mark.skipif(not REAL.exists(), reason="real-game capture is kept out of the public repo")
def test_small_real_template_matches_with_auto_scale():
    """A 22x24 template from the real game (menu button) is missed at a fixed 0.5x."""
    img = cv2.imread(str(REAL))
    btn = img[127:151, 136:158]
    assert detect.find_templates(img, [btn], 0.85, scale=0.5) == []
    hits = detect.find_templates(img, [btn], 0.85)
    assert len(hits) == 1
    assert abs(hits[0].c[0] - 147) <= 1 and abs(hits[0].c[1] - 139) <= 1
