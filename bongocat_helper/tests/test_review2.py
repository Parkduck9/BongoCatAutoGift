"""Regression tests for the second Codex review (docs/md/codex_review_2.md), items B1-B8."""
import pytest

import cats
import chatlog
import clicker as clicker_mod
import detect
import engine
import scene
from test_cats import FakeOcr
from test_engine import CATS, ZONE_H, frame, kinds, make, run


def counted_read(names):
    """OCR stand-in: answers from `names` in call order, the last one repeats."""
    calls = []

    def read(crop, box):
        calls.append(box)
        return names[min(len(calls), len(names)) - 1], 0.99

    read.calls = calls
    return read


def only_rine_reads(eng, names):
    """리네's tag reads `names` in order; every other tag reads its true name."""
    truth_read = eng.registry.read
    rine_read = counted_read(names)
    rine_box = {}

    def read(crop, box):
        name, score = truth_read(crop, box)
        if name == "리네" or box == rine_box.get("box"):
            rine_box["box"] = box
            return rine_read(crop, box)
        return name, score

    eng.registry.read = read
    return rine_read


# B1: the name is re-read on the FRESH capture taken right before the click
def test_b1_fresh_capture_with_another_player_is_not_clicked(tmp_path):
    img, _ = frame()
    swapped, _ = scene.scene([(150, 390, "철수"), (450, 220, "민지"), (750, 320, "민지")], h=ZONE_H)
    eng, clock, clicker, *_ = make(tmp_path, [img], targets=("리네",), dry_run=False)
    eng.registry.read = cats.read_tag                       # real OCR: the frame content decides
    grabs = []
    eng.grab = lambda: grabs.append(1) or (img if len(grabs) <= 2 else swapped)
    run(eng, clock, 2)
    assert clicker.clicks == []


# B2: an icon whose possible owner tag could lie outside the zone is not acted on
def test_b2_icon_near_zone_edge_is_refused(tmp_path):
    near_bottom, truth = scene.scene([(150, 300, "철수"), (450, ZONE_H - 25, "리네"), (750, 320, "민지")], h=ZONE_H)
    eng, clock, clicker, *_ = make(tmp_path, [near_bottom], targets=("리네",))
    eng.registry.read = FakeOcr(truth)
    events = run(eng, clock, 4)
    assert not [e for e in events if e.result == "dry_run" and e.name == "리네"]
    assert any(e.result == "edge_unsafe" for e in events)


# B3: a target removed while the tick runs is not clicked
def test_b3_target_removed_mid_tick_is_not_clicked(tmp_path):
    img, _ = frame()
    eng, clock, clicker, *_ = make(tmp_path, [img], targets=("리네",), dry_run=False)
    rine = only_rine_reads(eng, ["리네"])
    inner = eng.registry.read

    def read(crop, box):
        out = inner(crop, box)
        if len(rine.calls) == 3 and "리네" in eng.cfg["targets"]:   # 3rd read = right before the click
            eng.cfg["targets"].remove("리네")                       # user removes 리네 at that moment
        return out

    eng.registry.read = read
    run(eng, clock, 2)
    assert clicker.clicks == []


# B4: the CLI remembers an F12 press even after the key is released
def test_b4_stop_latch_stays_set():
    import bongo

    presses = iter([False, True, False, False])
    stop = bongo.stop_latch(lambda: next(presses))
    assert stop() is False
    assert stop() is True
    assert stop() is True and stop() is True


def test_b4_stop_checked_right_before_click(tmp_path):
    img, _ = frame()
    eng, clock, clicker, *_ = make(tmp_path, [img], targets=("리네",), dry_run=False)
    checks = []
    eng.should_stop = lambda: checks.append(1) or len(checks) > 1   # stop arrives after the first check
    run(eng, clock, 2)
    assert clicker.clicks == []


# B5: success is only recorded if the tag still reads the same name
def test_b5_replaced_cat_makes_click_unverified(tmp_path):
    img, _ = frame()
    after, _ = frame(gifts=("철수", "민지"))
    eng, clock, clicker, *_ = make(tmp_path, [img], targets=("리네",), dry_run=False)
    only_rine_reads(eng, ["리네", "리네", "리네", "하늘"])   # confirm x2, fresh re-read, then someone else
    eng.grab = lambda: after if clicker.clicks else img
    events = run(eng, clock, 4)
    assert len(clicker.clicks) == 1
    assert ("리네", "left") in kinds(events, "clicked_unverified")
    assert not eng.timers.cooling("리네", "left", clock())


def test_b5_chat_speaker_is_reread_before_recording():
    img, truth = scene.scene([(260, 390, "리네", True, "야옹 야옹")], h=ZONE_H)
    reg = cats.CatRegistry(counted_read(["리네", "리네", "하늘", "하늘"]))
    tags = detect.find_tag_boxes(img, scene.TAG_H)
    reg.update(tags, img, 0)
    reg.update(tags, img, 1)
    br = chatlog.BubbleReader(read=lambda crop: [type("L", (), {"text": "야옹 야옹", "score": 0.99})()])
    bubbles = detect.find_bubble_boxes(img, scene.TAG_H, exclude=tags)
    said = br.update(bubbles, img, 2, reg, scene.OFF_BUBBLE, 80)
    said += br.update(bubbles, img, 3, reg, scene.OFF_BUBBLE, 80)   # past the 0.5 s settle time
    assert ("리네", "야옹 야옹") not in said


# B6: the DB is not closed under a worker that is still running
def test_b6_close_keeps_db_open_while_worker_alive(monkeypatch):
    import gui

    closed = []
    app = gui.App.__new__(gui.App)
    app.runner = type("R", (), {"stop": lambda s: None, "join": lambda s, timeout=None: None,
                                "running": property(lambda s: True)})()
    app.db = type("D", (), {"close": lambda s: closed.append(1)})()
    app.root = type("T", (), {"destroy": lambda s: None})()
    app.close()
    assert closed == []


# B7: a tag cut by the edge of the scanned area is not marked missing
def test_b7_tag_crossing_scan_edge_is_not_missing():
    reg = cats.CatRegistry(lambda crop, box: ("리네", 0.99))
    box = detect.Box(100, 300, 60, 26)
    img = scene.background(900, ZONE_H)
    reg.update([box], img, 0)
    reg.update([box], img, 1)
    reg.update([], img, 2, scanned=[(0, 0, 135, 420)])     # covers the tag center, not the whole tag
    assert [c.name for c in reg.cats()] == ["리네"]


# B8: the cursor is checked again right before the button goes down
def test_b8_cursor_moved_by_user_aborts_click(monkeypatch):
    sent = []
    positions = iter([(5, 5), (10, 10), (300, 300)])      # before, after move, just before DOWN

    def get_pos(ptr):
        x, y = next(positions)
        ptr._obj.x, ptr._obj.y = x, y
        return 1

    monkeypatch.setattr(clicker_mod.ctypes.windll.user32, "GetCursorPos", get_pos, raising=False)
    monkeypatch.setattr(clicker_mod.ctypes.windll.user32, "SetCursorPos", lambda x, y: 1, raising=False)
    monkeypatch.setattr(clicker_mod, "_send", lambda flags: sent.append(flags))
    with pytest.raises(clicker_mod.ClickAborted):
        clicker_mod.Clicker().click(10, 10)
    assert sent == []


def test_b8_engine_reports_aborted_click_and_keeps_running(tmp_path):
    img, _ = frame()
    eng, clock, clicker, *_ = make(tmp_path, [img], targets=("리네",), dry_run=False)

    def abort(x, y, abort=None):
        raise clicker_mod.ClickAborted("moved")

    eng.clicker.click = abort
    events = run(eng, clock, 2)
    assert kinds(events, "click_aborted")
    assert eng._verify == []
