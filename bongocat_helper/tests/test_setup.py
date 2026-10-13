import pytest

import calib
import scene

LAYOUT = [(150, 390, "리네"), (450, 220, "철수"), (750, 320, "민지")]


def loose(rect, pad=4):
    """What a user's drag looks like: a little bigger than the object."""
    x, y, w, h = rect
    return [x - pad, y - pad, w + 2 * pad, h + 2 * pad]


def icon_rect(center):
    cx, cy = center
    return [cx - scene.ICON // 2, cy - scene.ICON // 2, scene.ICON, scene.ICON]


def user_rects(truth, i=0):
    t = truth[i]
    return {
        "zone": [0, 0, 900, 420],
        "left": icon_rect(t["icons"]["left"]),        # tight drag on the icon picture
        "right": icon_rect(t["icons"]["right"]),
        "tag": loose(t["tag"]),
    }


def test_compute_offsets_and_tag_size_from_one_cat():
    img, truth = scene.scene(LAYOUT)
    res = calib.compute(img, user_rects(truth, 1))
    assert res.region == [0, 0, 900, 420]
    assert res.offsets["left"] == pytest.approx(scene.OFF_LEFT, abs=2)
    assert res.offsets["right"] == pytest.approx(scene.OFF_RIGHT, abs=2)
    assert res.tag["height"] == pytest.approx(scene.TAG_H + 1, abs=4)
    assert res.templates["gift_left"].shape[:2] == (scene.ICON, scene.ICON)


def test_offsets_are_relative_to_zone_free_coords():
    # zone offset must not leak into offsets (they are tag-relative)
    img, truth = scene.scene(LAYOUT)
    rects = user_rects(truth, 0)
    rects["zone"] = [50, 100, 800, 320]
    res = calib.compute(img, rects)
    assert res.offsets["left"] == pytest.approx(scene.OFF_LEFT, abs=2)
    assert res.region == [50, 100, 800, 320]


def test_optional_bubble_offset():
    img, truth = scene.scene(LAYOUT)
    rects = user_rects(truth, 0)
    tx, ty = truth[0]["tag"][0] + truth[0]["tag"][2] // 2, truth[0]["tag"][1] + truth[0]["tag"][3] // 2
    rects["bubble"] = [tx - 120, ty - 150, 80, 30]
    res = calib.compute(img, rects)
    assert res.offsets["bubble"] == pytest.approx((-80, -135), abs=3)
    assert res.offsets["number"] is None


@pytest.mark.parametrize("bad, msg", [
    ({"left": [0, 0, 0, 0]}, "left"),
    ({"tag": [880, 400, 60, 30]}, "zone"),
    ({"zone": [0, 0, 5, 5]}, "zone"),
])
def test_validation_errors(bad, msg):
    img, truth = scene.scene(LAYOUT)
    rects = user_rects(truth, 0)
    rects.update(bad)
    with pytest.raises(calib.SetupError, match=msg):
        calib.compute(img, rects)


def test_verify_finds_all_cats_and_owners_with_new_settings():
    img, truth = scene.scene(LAYOUT)
    res = calib.compute(img, user_rects(truth, 0))
    report = calib.verify(img, res, read=lambda crop, box: ("x", 0.99))
    assert report.tags == 3
    assert report.icons == 6
    assert report.owned == 6


def test_select_rects_maps_display_coords_back_including_zone_zoom(monkeypatch):
    img, truth = scene.scene(LAYOUT)
    wanted = user_rects(truth, 0)
    wanted["zone"] = [100, 60, 700, 360]
    wanted["bubble"] = None
    wanted["number"] = None
    order = [k for k, _, _ in calib.STEPS]
    calls = iter(order)
    state = {"view_origin": (0, 0), "view": img}

    def fake_select(win, canvas, **kw):
        key = next(calls)
        view = state["view"]
        _, scale = calib._fit(view, 1600, 900)
        r = wanted[key]
        if r is None:
            return (0, 0, 0, 0)
        ox, oy = state["view_origin"]
        return (round((r[0] - ox) * scale), round((r[1] - oy) * scale) + 64,
                round(r[2] * scale), round(r[3] * scale))

    orig_fit = calib._fit

    # after the zone step the UI shows only the zone: mirror that in the fake
    def fit_spy(view, max_w, max_h):
        if view.shape != img.shape:
            state["view"], state["view_origin"] = view, (wanted["zone"][0], wanted["zone"][1])
        return orig_fit(view, max_w, max_h)

    monkeypatch.setattr(calib.cv2, "selectROI", fake_select)
    monkeypatch.setattr(calib.cv2, "destroyWindow", lambda *a: None)
    monkeypatch.setattr(calib, "_fit", fit_spy)
    got = calib.select_rects(img)
    for key in order:
        if wanted[key] is None:
            assert got[key] is None
        else:
            assert got[key] == pytest.approx(wanted[key], abs=1), key


def test_flat_icon_selection_is_rejected():
    img, truth = scene.scene(LAYOUT)
    rects = user_rects(truth, 0)
    rects["left"] = [5, 5, 20, 20]  # plain background, not an icon
    with pytest.raises(calib.SetupError, match="left"):
        calib.compute(img, rects)


def test_bubble_offset_relative_to_tag_center():
    layout = [(260, 390, "리네", True, "야옹 야옹")]
    img, truth = scene.scene(layout)
    rects = {"bubble": list(truth[0]["bubble"]), "tag": loose(truth[0]["tag"])}
    off = calib.compute_bubble_offset(img, rects)
    assert off == pytest.approx(list(scene.OFF_BUBBLE), abs=3)
