"""Regression tests for the Codex review (docs/md/codex_review_1.md) findings that were confirmed."""
import threading

import numpy as np
import pytest

import cats
import chatlog
import config
import debug
import detect
import engine
import gift_timer
import scene
import store
import ocr
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


def test_departed_cat_is_removed_and_its_icon_is_not_owned():
    reg = cats.CatRegistry(lambda crop, box: ("리네", 0.99) if box.x == 100 else ("민지", 0.99))
    a, b = detect.Box(100, 300, 60, 26), detect.Box(200, 300, 60, 26)
    img = scene.background()
    settle(reg, [a, b], img)
    reg.update([a], img, now=2, scanned=[(0, 0, 900, 420)])    # 민지's tag hidden by animation
    b_left = (b.c[0] + scene.OFF_LEFT[0], b.c[1] + scene.OFF_LEFT[1])
    owner = reg.owner_of(b_left, {"left": scene.OFF_LEFT, "right": scene.OFF_RIGHT}, 30, 10)
    assert owner is None
    assert [c.name for c in reg.cats()] == ["리네"]


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
    empty = scene.background()
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


def test_changed_owner_in_fresh_frame_never_gets_clicked(tmp_path):
    old, _ = frame()
    fresh, _ = scene.scene([(150, 390, "철수"), (450, 220, "철수"), (750, 320, "민지")], h=old.shape[0])
    eng, clock, mouse, db, _ = make(tmp_path, [old], targets=("리네",), dry_run=False)
    run(eng, clock, 1)
    original = eng.registry.read
    reads = []

    def read(crop, box):
        if box.c[0] < 200:
            name = "리네" if np.array_equal(crop, cats.tag_interior(old, box)) else "철수"
            reads.append(name)
            return name, 0.99
        return original(crop, box)

    eng.registry.read = read
    eng.grab = Frames(old, fresh)
    eng.tick()
    assert "철수" in reads
    assert mouse.clicks == []


def test_fresh_icon_without_visible_tag_never_gets_clicked(tmp_path):
    old, truth = frame()
    fresh = old.copy()
    x, y, w, h = truth[0]["tag"]
    fresh[y - 4:y + h + 4, x - 4:x + w + 4] = (200, 120, 40)
    eng, clock, mouse, *_ = make(tmp_path, [old], targets=("리네",), dry_run=False)
    run(eng, clock, 1)
    eng.grab = Frames(old, fresh)
    eng.tick()
    assert mouse.clicks == []


def test_uncertain_fresh_korean_ocr_never_gets_clicked(tmp_path):
    old, _ = frame()
    fresh = old.copy()
    fresh[380, 140] = (0, 0, 0)
    eng, clock, mouse, *_ = make(tmp_path, [old], targets=("리네",), dry_run=False)
    run(eng, clock, 1)
    original = eng.registry.read

    def read(crop, box):
        if box.c[0] < 200 and not np.array_equal(crop, cats.tag_interior(old, box)):
            return "리네", 0.5
        return original(crop, box)

    eng.registry.read = read
    eng.grab = Frames(old, fresh)
    eng.tick()
    assert mouse.clicks == []


def test_runner_captures_only_selected_full_monitor(tmp_path, monkeypatch):
    import queue
    import gui
    from store import Store
    calls = []
    class Capture:
        def monitor(self,index):
            assert index == 2
            return {"left":-1920,"top":100}
        def grab(self,index):
            calls.append(index)
            return None
        def close(self): pass
    monkeypatch.setattr(gui.capture,"Capturer",Capture)
    monkeypatch.setattr(gui.clicker,"stop_pressed",lambda:False)
    db=Store(tmp_path/"test.db")
    runner=gui.Runner({"monitor":2,"dry_run":True},db,queue.Queue())
    runner.session.scanner=lambda frame:[]
    runner._loop("scan",None)
    assert calls==[2]
    db.close()


def test_new_message_after_bubble_disappears_is_recorded():
    zone = scene.background(300, 200)
    box = detect.Box(20, 20, 120, 30)
    registry = cats.CatRegistry()
    current = ["안녕하세요"]
    reader = chatlog.BubbleReader(read=lambda crop: [ocr.Line(current[0], 0, 0, 100, 20, 0.99)])
    whole = [(0, 0, 300, 200)]
    reader.update([box], zone, 0, registry, None, 30, whole)
    assert reader.update([box], zone, 1, registry, None, 30, whole) == [("?", "안녕하세요")]
    reader.update([], zone, 2, registry, None, 30, whole)
    for now in (3, 4):
        reader.update([], zone, now, registry, None, 30, [])
    current[0] = "Hello"
    reader.update([box], zone, 5, registry, None, 30, whole)
    assert reader.update([box], zone, 6, registry, None, 30, []) == [("?", "Hello")]


def test_changed_text_in_same_bubble_is_saved_but_same_sentence_is_deduped():
    zone = scene.background(300, 200)
    box = detect.Box(20, 20, 120, 30)
    registry = cats.CatRegistry()
    current = ["안녕하세요"]
    reader = chatlog.BubbleReader(read=lambda crop: [ocr.Line(current[0], 0, 0, 100, 20, 0.99)])
    dedup = chatlog.ChatDedup()
    saved = []

    def tick(now):
        for who, text in reader.update([box], zone, now, registry, None, 30, [(0, 0, 300, 200)]):
            if dedup.observe(who, text, now):
                saved.append(text)

    tick(0)
    tick(1)
    # Tiny visual change, same OCR sentence: re-read but don't store a duplicate.
    zone[30, 30] = (1, 2, 3)
    tick(2)
    tick(3)
    current[0] = "Hello"
    zone[30, 30] = (4, 5, 6)
    tick(4)
    tick(5)
    tick(6)
    assert saved == ["안녕하세요", "Hello"]


def test_chat_position_is_blocked_for_four_seconds_even_after_disappearance():
    zone = scene.background(300, 200)
    box = detect.Box(20, 20, 120, 30)
    reg = cats.CatRegistry()
    text = ["첫 문장"]
    reads = []

    def read(crop):
        reads.append(text[0])
        return [ocr.Line(text[0], 0, 0, 100, 20, 0.99)]

    br = chatlog.BubbleReader(read=read, settle_sec=0)
    whole = [(0, 0, 300, 200)]
    assert br.update([box], zone, 0, reg, None, 30, whole) == [("?", "첫 문장")]
    br.update([], zone, 1, reg, None, 30, whole)
    text[0] = "다른 문장"
    for now in (2, 3, 3.99):
        assert br.update([box], zone, now, reg, None, 30, whole) == []
    assert reads == ["첫 문장"]
    assert br.update([box], zone, 4, reg, None, 30, whole) == [("?", "다른 문장")]


def test_pixel_changes_do_not_delay_first_chat_or_duplicate_same_sentence():
    zone = scene.background(300, 200)
    box = detect.Box(20, 20, 120, 30)
    reg, dedup = cats.CatRegistry(), chatlog.ChatDedup()
    reads, saved = [], []

    def read(crop):
        reads.append(True)
        return [ocr.Line("안녕하세요", 0, 0, 100, 20, 0.99)]

    br = chatlog.BubbleReader(read=read)
    for now in range(14):
        zone[30, 30] = (now, now, now)
        for speaker, text in br.update([box], zone, now, reg, None, 30, [(0, 0, 300, 200)]):
            if dedup.observe(speaker, text, now):
                saved.append(text)
    assert len(reads) == 4  # times 1, 5, 9, 13, regardless of tiny pixel changes
    assert saved == ["안녕하세요"]
