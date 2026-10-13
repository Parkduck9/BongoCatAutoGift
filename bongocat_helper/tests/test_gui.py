import datetime
import gc
import time
import tkinter as tk

import pytest

import calib
import config
import engine
import gui
import scene
from test_cats import FakeOcr
from test_engine import CATS, Clock, FakeClicker, Frames, frame


@pytest.fixture
def app(tmp_path, monkeypatch):
    for name in ("showwarning", "showinfo"):
        monkeypatch.setattr(gui.messagebox, name, lambda *a, **k: None)
    root = tk.Tk()
    root.withdraw()
    made = {}

    def make_engine(cap):
        img, truth = frame()
        t = truth[0]
        icon = lambda c: [c[0] - 20, c[1] - 20, 40, 40]
        res = calib.compute(img, {"zone": [0, 0, 900, 420], "left": icon(t["icons"]["left"]),
                                  "right": icon(t["icons"]["right"]),
                                  "tag": [t["tag"][0] - 3, t["tag"][1] - 3, t["tag"][2] + 6, t["tag"][3] + 6]})
        made["clicker"] = FakeClicker()
        a = holder["app"]
        a.cfg.update(offsets=res.offsets)
        return engine.Engine(a.cfg, Frames(img), made["clicker"], a.db,
                             [res.templates["gift_left"], res.templates["gift_right"]], read=FakeOcr(truth))

    holder = {}
    cfg_path = tmp_path / "config.json"
    a = gui.App(root, cfg_path=cfg_path, base_dir=tmp_path, make_engine=make_engine)
    holder["app"] = a
    a.made = made
    yield a
    a.runner.stop()
    if a.runner._thread:
        a.runner._thread.join(timeout=5)
    a.db.close()
    root.destroy()
    del a, holder["app"], root
    gc.collect()  # free Tk variables here, on the main thread; a worker-thread GC breaks Tcl


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.root.update()
        time.sleep(0.05)


def calibrated(app):
    import cv2

    app.cfg.update(region=[0, 0, 900, 420], tag={"height": 23, "aspect": 2.0}, interval_sec=0.2)
    config.save(app.cfg, app.cfg_path)
    (app.base_dir / "templates").mkdir(exist_ok=True)
    for name in ("gift_left", "gift_right"):   # what setup writes
        cv2.imwrite(str(app.base_dir / "templates" / f"{name}.png"), scene.gift_icon())


def test_start_refused_without_templates(app):
    app.cfg.update(region=[0, 0, 900, 420], tag={"height": 23, "aspect": 2.0})
    config.save(app.cfg, app.cfg_path)
    app.add_target("리네")
    app.start()
    assert not app.runner.running


def test_targets_add_remove_persist(app):
    app.add_target("리네")
    app.add_target("민지")
    app.add_target("리네")
    assert config.load(app.cfg_path)["targets"] == ["리네", "민지"]
    app.remove_target("리네")
    assert config.load(app.cfg_path)["targets"] == ["민지"]
    assert app.lst_targets.get(0, "end") == ("민지",)


def test_start_refused_without_setup(app):
    app.add_target("리네")
    app.start()
    assert not app.runner.running


def test_live_mode_needs_confirmation(app):
    calibrated(app)
    app.add_target("리네")
    app.var_dry.set(False)
    app.start(confirm=lambda *a: False)
    assert not app.runner.running


def test_practice_run_logs_countdown_and_stops(app):
    calibrated(app)
    app.add_target("리네")
    app.add_target("민지")
    app.start()
    assert app.runner.running
    assert "연습 모드" in app.lbl_state["text"]
    pump(app, 4)
    log = app.txt_log.get("1.0", "end")
    assert log.count("dry_run") == 4 and "리네" in log and "민지" in log
    assert app.made["clicker"].clicks == []
    rows = app.countdown_rows()
    assert sorted((n, s) for n, s, _ in rows) == [("리네", "left"), ("리네", "right"), ("민지", "left"), ("민지", "right")]
    assert all(1700 < left <= 1800 for _, _, left in rows)
    assert len(app.next_rows) == 4
    assert app.lbl_gifts["text"] == "선물 4 (연습)"
    app.stop()
    pump(app, 1)
    assert not app.runner.running and app.lbl_state["text"] == "멈춤"


def test_chat_tab_filters_and_exports(app, tmp_path):
    t = datetime.datetime.now().replace(microsecond=0).timestamp()
    app.db.add_chat(t, "리네", "야옹 야옹")
    app.db.add_chat(t + 1, "민지", "안녕하세요")
    app.refresh_chat()
    assert len(app.tree.get_children()) == 2
    app.cmb_speaker.set("리네")
    app.refresh_chat(keep_date=True)
    assert [app.tree.item(i)["values"][2] for i in app.tree.get_children()] == ["야옹 야옹"]
    path = app.export_chat(notify=lambda *a: None)
    assert path.parent == tmp_path / "exports" and "리네: 야옹 야옹" in path.read_text(encoding="utf-8")
    assert "안녕하세요" not in path.read_text(encoding="utf-8")
