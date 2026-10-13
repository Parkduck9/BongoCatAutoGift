import calib
import config
import engine
import scene
import store
from test_cats import FakeOcr

CATS = [(150, 390, "리네"), (450, 220, "철수"), (750, 320, "민지")]
ZONE_H = 470   # leaves room below the lowest cat: icons whose owner could be cut off are refused
MON = {"left": 100, "top": 50}


def frame(gifts=("리네", "철수", "민지")):
    return scene.scene([(x, y, n, n in gifts) for x, y, n in CATS], h=ZONE_H)


class Frames:
    def __init__(self, *frames):
        self.frames = list(frames)

    def __call__(self):
        return self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]


class FakeClicker:
    def __init__(self):
        self.clicks = []

    def click(self, x, y, abort=lambda: False):
        self.clicks.append((x, y))


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def make(tmp_path, frames, targets=("리네", "민지"), dry_run=True):
    img, truth = frame()
    rects = {"zone": [0, 0, 900, ZONE_H],
             "left": [truth[0]["icons"]["left"][0] - 20, truth[0]["icons"]["left"][1] - 20, 40, 40],
             "right": [truth[0]["icons"]["right"][0] - 20, truth[0]["icons"]["right"][1] - 20, 40, 40],
             "tag": [truth[0]["tag"][0] - 3, truth[0]["tag"][1] - 3, truth[0]["tag"][2] + 6, truth[0]["tag"][3] + 6]}
    res = calib.compute(img, rects)
    cfg = config.load(tmp_path / "none.json")
    cfg.update(region=res.region, offsets=res.offsets, tag=res.tag, targets=list(targets), dry_run=dry_run)
    clock, clicker = Clock(), FakeClicker()
    db = store.Store(tmp_path / "bongo.db")
    eng = engine.Engine(cfg, Frames(*frames), clicker, db,
                        [res.templates["gift_left"], res.templates["gift_right"]],
                        read=FakeOcr(truth), clock=clock, monitor=MON)
    return eng, clock, clicker, db, truth


def run(eng, clock, n, step=1.0):
    events = []
    for _ in range(n):
        events += eng.tick()
        clock.t += step
    return events


def kinds(events, result):
    return sorted((e.name, e.side) for e in events if e.result == result)


def test_dry_run_reports_only_targets_and_starts_timers(tmp_path):
    img, _ = frame()
    eng, clock, clicker, db, _ = make(tmp_path, [img])
    events = run(eng, clock, 4)
    assert kinds(events, "dry_run") == [("리네", "left"), ("리네", "right"), ("민지", "left"), ("민지", "right")]
    assert ("철수", "left") in kinds(events, "skipped")
    assert clicker.clicks == []
    assert eng.timers.remaining("리네", "left", clock()) > 1790


def test_dry_run_does_not_repeat_while_cooling(tmp_path):
    img, _ = frame()
    eng, clock, clicker, db, _ = make(tmp_path, [img])
    events = run(eng, clock, 20)
    assert len(kinds(events, "dry_run")) == 4


def test_real_click_at_screen_coords_then_verified_ok(tmp_path):
    with_gifts, truth = frame()
    after, _ = frame(gifts=("철수", "민지"))          # 리네's icons disappeared after the clicks
    eng, clock, clicker, db, truth = make(tmp_path, [with_gifts], targets=("리네",), dry_run=False)
    eng.grab = lambda: after if len(clicker.clicks) >= 2 else with_gifts
    events = run(eng, clock, 6)                           # one click per tick, then both verified
    lx, ly = truth[0]["icons"]["left"]
    assert any(abs(x - (MON["left"] + lx)) <= 2 and abs(y - (MON["top"] + ly)) <= 2 for x, y in clicker.clicks)
    assert len(clicker.clicks) == 2
    assert kinds(events, "clicked_ok") == [("리네", "left"), ("리네", "right")]
    assert eng.timers.cooling("리네", "left", clock())
    assert db.count_gifts(since=0) == 2


def test_click_without_effect_starts_no_timer_and_retries_later(tmp_path):
    img, _ = frame()
    eng, clock, clicker, db, _ = make(tmp_path, [img], targets=("리네",), dry_run=False)
    events = run(eng, clock, 6)
    assert kinds(events, "clicked_no_change") == [("리네", "left"), ("리네", "right")]
    assert not eng.timers.cooling("리네", "left", clock())
    n = len(clicker.clicks)
    run(eng, clock, 10)                                   # past click_cooldown_sec (5)
    assert len(clicker.clicks) > n


def test_pending_cat_gets_nothing(tmp_path):
    img, _ = frame()
    eng, clock, clicker, db, _ = make(tmp_path, [img])
    events = eng.tick()                                   # first frame: names not confirmed yet
    assert not kinds(events, "dry_run")


def test_skips_icon_search_while_every_target_is_cooling(tmp_path, monkeypatch):
    img, _ = frame()
    eng, clock, clicker, db, _ = make(tmp_path, [img])
    run(eng, clock, 4)
    calls = []
    real = engine.detect.find_templates
    monkeypatch.setattr(engine.detect, "find_templates", lambda *a, **k: calls.append(1) or real(*a, **k))
    run(eng, clock, 10)
    assert calls == []
    clock.t += 1800                                       # timers done -> searching again
    run(eng, clock, 2)
    assert calls


def test_timers_restored_after_restart(tmp_path):
    img, _ = frame()
    eng, clock, clicker, db, _ = make(tmp_path, [img])
    run(eng, clock, 4)
    db.close()
    eng2, clock2, *_ = make(tmp_path, [img])
    clock2.t = clock.t + 60
    eng2.restore_timers()
    assert 1700 < eng2.timers.remaining("리네", "left", clock2()) < 1800


def test_action_log_lines(tmp_path):
    img, _ = frame()
    eng, clock, clicker, db, _ = make(tmp_path, [img])
    lines = [engine.format_event(e) for e in run(eng, clock, 4)]
    assert any(" | L1000 | " in l and l.endswith("| 리네 | dry_run") for l in lines)


def test_late_warning_when_icon_does_not_come_back(tmp_path):
    with_gifts, _ = frame()
    without, _ = frame(gifts=("철수",))
    eng, clock, clicker, db, _ = make(tmp_path, [with_gifts] * 4 + [without])
    run(eng, clock, 4)                                    # dry_run starts 30 min timers
    clock.t += 1800 + 61
    events = run(eng, clock, 3)
    assert kinds(events, "late") == [("리네", "left"), ("리네", "right"), ("민지", "left"), ("민지", "right")]
    assert not kinds(run(eng, clock, 3), "late")          # reported once


def test_chat_recorded_once_with_speaker(tmp_path):
    # 리네 moved right so the bubble (left of the cat) is fully on screen
    layout = [(260, 390, "리네", True, "야옹 야옹"), (450, 220, "철수"), (750, 320, "민지")]
    chatty, truth = scene.scene(layout, h=ZONE_H)
    eng, clock, clicker, db, _ = make(tmp_path, [chatty])
    eng.registry.read = FakeOcr(truth)
    eng.cfg["offsets"]["bubble"] = list(scene.OFF_BUBBLE)
    events = run(eng, clock, 6)
    chats = [(e.name, e.text) for e in events if e.result == "chat"]
    assert chats == [("리네", "야옹 야옹")]
    assert [r[1:] for r in db.query_chat()] == [("리네", "야옹 야옹")]
    assert engine.format_event(next(e for e in events if e.result == "chat")).endswith("| 채팅 | 리네: 야옹 야옹")


def test_no_unmatched_noise_while_names_are_being_read(tmp_path):
    img, _ = frame()
    eng, clock, clicker, db, _ = make(tmp_path, [img])
    first = eng.tick()                                    # names pending after one read
    assert [e for e in first if e.result == "unmatched"] == []
