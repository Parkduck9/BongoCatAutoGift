"""Regression tests for the Codex review (docs/md/codex_review_1.md) findings that were confirmed."""
import threading

import pytest

import cats
import config
import debug
import detect
import engine
import gift_timer
import scene
import store
from test_cats import Sequence, settle
from test_engine import Clock, FakeClicker, Frames, frame, kinds, make, run


# 1: another cat in a departed target's spot must not inherit the target's name
def test_click_rechecks_name_and_resets_on_different_name(tmp_path):
    img, truth = frame()
    eng2, clock2, clicker2, *_ = make(tmp_path, [img], targets=("리네",), dry_run=False)
    run(eng2, clock2, 2)                                  # names confirmed, first click
    rine = next(c for c in eng2.registry.cats() if c.name == "리네")
    # the tag at 리네's spot now reads as a different player
    eng2.registry.read = lambda crop, box: ("철수", 0.99) if box == rine.box else ("x", 0.0)
    eng2.timers = gift_timer.GiftTimers(1800)
    clicks_before = len(clicker2.clicks)
    clock2.t += 10
    run(eng2, clock2, 2)
    assert len(clicker2.clicks) == clicks_before
    assert rine.name != "리네"                             # reset, re-read as the new player


# 2: a tag seen missing in a scan stays missing on later unchanged frames and expires
def test_missing_tag_is_not_kept_alive_by_static_frames():
    img, truth = scene.scene([(150, 390, "리네")])
    reg = cats.CatRegistry(lambda crop, box: ("리네", 0.99), ttl=5)
    boxes = detect.find_tag_boxes(img, scene.TAG_H)
    settle(reg, boxes, img)
    reg.update([], img, now=2, scanned=[(0, 0, 900, 420)])   # scanned: tag gone
    assert reg.cats() == []                                    # missing -> never an owner
    for t in range(3, 12):
        reg.update([], img, now=t, scanned=[])                 # nothing changes afterwards
    assert reg._cats == []                                     # expired, not immortal


def test_missing_cat_still_blocks_its_neighbors_icons():
    reg = cats.CatRegistry(lambda crop, box: ("리네", 0.99) if box.x == 100 else ("민지", 0.99))
    a, b = detect.Box(100, 300, 60, 26), detect.Box(200, 300, 60, 26)
    img = scene.background()
    settle(reg, [a, b], img)
    reg.update([a], img, now=2, scanned=[(0, 0, 900, 420)])    # 민지's tag hidden by animation
    b_left = (b.c[0] + scene.OFF_LEFT[0], b.c[1] + scene.OFF_LEFT[1])
    owner = reg.owner_of(b_left, {"left": scene.OFF_LEFT, "right": scene.OFF_RIGHT}, 30, 10)
    assert owner is not None and owner.cat.name == "민지" and not owner.cat.is_named


# 4: at most one real click per tick, and only if a fresh capture still shows the icon
def test_one_click_per_tick_and_fresh_recheck(tmp_path):
    img, _ = frame()
    gone, _ = frame(gifts=("철수", "민지"))
    eng, clock, clicker, db, _ = make(tmp_path, [img], targets=("리네",), dry_run=False)
    run(eng, clock, 1)                                       # first read
    events = eng.tick()                                      # confirmed now; would click
    assert len(clicker.clicks) == 1
    eng.grab = Frames(img, gone)                              # icon vanished before 2nd click
    clock.t += 6
    eng.tick()
    assert len(clicker.clicks) == 1


# 5: target edits while running take effect
def test_target_changes_apply_while_running(tmp_path):
    img, _ = frame()
    eng, clock, clicker, db, _ = make(tmp_path, [img], targets=("리네",))
    eng.cfg["targets"].append("민지")
    events = run(eng, clock, 3)
    assert ("민지", "left") in kinds(events, "dry_run")


# 6: a failed cursor move must not click at the old cursor position
def test_clicker_raises_when_cursor_cannot_move(monkeypatch):
    import clicker as clicker_mod

    sent = []
    monkeypatch.setattr(clicker_mod, "_send", lambda flags: sent.append(flags))
    monkeypatch.setattr(clicker_mod.ctypes.windll.user32, "SetCursorPos", lambda x, y: 0, raising=False)
    with pytest.raises(OSError):
        clicker_mod.Clicker().click(10, 10)
    assert sent == []


# 7: stop request is honoured before a click even mid-tick
def test_stop_request_blocks_click(tmp_path):
    img, _ = frame()
    eng, clock, clicker, db, _ = make(tmp_path, [img], targets=("리네",), dry_run=False)
    eng.should_stop = lambda: True
    run(eng, clock, 3)
    assert clicker.clicks == []


# 8: success needs the same cat still in place
def test_click_unverified_when_cat_left(tmp_path):
    img, _ = frame()
    empty = scene.background(900, 470)
    # tick1 read, tick2 confirm + fresh recheck + click, tick3 the cat is gone
    eng, clock, clicker, db, _ = make(tmp_path, [img, img, img, empty], targets=("리네",), dry_run=False)
    events = run(eng, clock, 5)
    assert kinds(events, "clicked_unverified")
    assert not eng.timers.cooling("리네", "left", clock())


# 9: practice records do not block real gifts
def test_live_mode_ignores_dry_run_records(tmp_path):
    img, _ = frame()
    eng, clock, clicker, db, _ = make(tmp_path, [img])
    run(eng, clock, 4)
    db.close()
    eng2, clock2, *_ = make(tmp_path, [img], dry_run=False)
    clock2.t = clock.t + 60
    eng2.restore_timers()
    assert not eng2.timers.cooling("리네", "left", clock2())


# 10: timers can be read while another thread adds keys
def test_upcoming_is_safe_while_worker_adds_timers():
    t = gift_timer.GiftTimers(1800)
    stop = threading.Event()

    def writer():
        for i in range(20000):  # bounded: upcoming() sorts every key
            t.start(f"n{i}", "left", now=0)
        stop.set()

    th = threading.Thread(target=writer)
    th.start()
    while not stop.is_set():
        t.upcoming(now=1)
    th.join()


# 12: missing or broken templates fail loudly
def test_load_templates_fails_fast(tmp_path):
    cfg = config.load(tmp_path / "none.json")
    with pytest.raises(FileNotFoundError):
        debug.load_templates(cfg, tmp_path)
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "gift_left.png").write_bytes(b"not a png")
    (tmp_path / "templates" / "gift_right.png").write_bytes(b"not a png")
    with pytest.raises(ValueError):
        debug.load_templates(cfg, tmp_path)


# 13: today's chat count is a COUNT query
def test_count_chat(tmp_path):
    import datetime

    db = store.Store(tmp_path / "b.db")
    t = datetime.datetime(2026, 10, 12, 10).timestamp()
    db.add_chat(t, "a", "x")
    db.add_chat(t + 1, "b", "y")
    db.add_chat(t + 86400, "a", "z")
    assert db.count_chat("2026-10-12") == 2


# 14: unused settings/paths are gone
def test_unused_config_removed():
    assert "idle_interval_sec" not in config.DEFAULTS
    assert "tag_edge" not in config.DEFAULTS["templates"]
