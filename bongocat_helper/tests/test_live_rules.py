"""User rules: cache positions, log failed chat reads, and preserve calibration."""
import pytest

import cats
import chatlog
import config
import detect
import engine
import gui
import ocr
import scene
from test_cats import FakeOcr, settle
from test_engine import frame, make, run


def test_departed_position_is_removed_immediately():
    img, truth = scene.scene([(200, 300, "리네")])
    reg = cats.CatRegistry(FakeOcr(truth))
    settle(reg, detect.find_tag_boxes(img, scene.TAG_H), img)
    departed = reg.cats()[0].id
    reg.update([], scene.background(), now=2)
    assert reg.get(departed) is None


def test_moved_position_is_new_and_requires_name_confirmation():
    old, truth = scene.scene([(200, 300, "리네")])
    reg = cats.CatRegistry(FakeOcr(truth))
    settle(reg, detect.find_tag_boxes(old, scene.TAG_H), old)
    original_id = reg.cats()[0].id
    moved, new_truth = scene.scene([(205, 297, "철수")])
    reg.read = FakeOcr(new_truth)
    boxes = detect.find_tag_boxes(moved, scene.TAG_H)
    reg.update(boxes, moved, now=2)
    assert reg.get(original_id) is None
    assert reg.cats() == []
    reg.update(boxes, moved, now=3)
    assert [cat.name for cat in reg.cats()] == ["철수"]


def test_scene_scan_only_reads_new_tags_and_clears_room_exit(tmp_path):
    img, _ = frame()
    eng, clock, mouse, *_ = make(tmp_path, [img])
    run(eng, clock, 4)
    calls = eng.registry.read.calls
    run(eng, clock, 5)
    assert eng.registry.read.calls == calls
    eng.grab = scene.background
    eng.tick()
    assert eng.registry._cats == []
    assert mouse.clicks == []


@pytest.mark.parametrize("raises", [False, True])
def test_failed_chat_logs_each_attempt_and_stops_after_three(tmp_path, raises):
    layout = [(260, 390, "리네", True, "야옹 야옹")]
    img, truth = scene.scene(layout)
    eng, clock, mouse, db, _ = make(tmp_path, [img], targets=("리네",))
    eng.registry.read = FakeOcr(truth)
    eng.cfg["offsets"]["bubble"] = list(scene.OFF_BUBBLE)
    calls = []

    def fail(crop):
        calls.append(True)
        if raises:
            raise RuntimeError("OCR failed")
        return []

    eng.bubbles.read = fail
    events = run(eng, clock, 10)
    assert len(calls) == 3
    failures = [e for e in events if e.result == "chat_ocr_failed"]
    assert len(failures) == 3
    assert [row[2] for row in db.query_chat()] == ["OCR 실패 (1/3)", "OCR 실패 (2/3)", "OCR 실패 (3/3)"]
    assert all(row[1] == "리네" for row in db.query_chat())
    assert mouse.clicks == []


def test_resized_bubble_keeps_four_second_block():
    zone = scene.background(500, 300)
    reg = cats.CatRegistry()
    original = detect.Box(100, 20, 120, 30)
    resized = detect.Box(80, 20, 140, 30)
    reader = chatlog.BubbleReader(read=lambda crop: [ocr.Line("안녕하세요", 0, 0, 100, 20, 0.99)])
    whole = [(0, 0, 500, 300)]
    reader.update([original], zone, 0, reg, None, 30, whole)
    assert reader.update([original], zone, 1, reg, None, 30, whole)
    for now in (2, 3, 4):
        assert reader.update([resized], zone, now, reg, None, 30, whole) == []
    assert reader.update([resized], zone, 5, reg, None, 30, whole)


def test_wider_bubble_keeps_speaker_and_tag_position_block():
    zone = scene.background(500, 400)
    reg = cats.CatRegistry(lambda crop, box: ("리네", 0.99))
    tag = detect.Box(270, 300, 60, 26)
    settle(reg, [tag], zone)
    original = detect.Box(100, 20, 120, 30)
    wider = detect.Box(10, 20, 210, 30)
    offset = (original.c[0] - tag.c[0], original.c[1] - tag.c[1])
    reader = chatlog.BubbleReader(read=lambda crop: [ocr.Line("안녕하세요", 0, 0, 100, 20, 0.99)])
    whole = [(0, 0, 500, 400)]
    reader.update([original], zone, 0, reg, offset, 30, whole)
    assert reader.update([original], zone, 1, reg, offset, 30, whole) == [("리네", "안녕하세요")]
    for now in (2, 3, 4):
        assert reader.update([wider], zone, now, reg, offset, 30, whole) == []
    assert reader.update([wider], zone, 5, reg, offset, 30, whole) == [("리네", "안녕하세요")]


def test_failed_bubble_stays_ignored_when_width_changes():
    zone = scene.background(500, 300)
    reg = cats.CatRegistry()
    original = detect.Box(100, 20, 120, 30)
    resized = detect.Box(80, 20, 140, 30)
    calls = []
    reader = chatlog.BubbleReader(read=lambda crop: calls.append(True) or [], settle_sec=0)
    whole = [(0, 0, 500, 300)]
    for now in range(3):
        reader.update([original], zone, now, reg, None, 30, whole)
    for now in range(3, 10):
        reader.update([resized], zone, now, reg, None, 30, whole)
    assert len(calls) == 3


def test_cat_edit_does_not_change_monitor_config(tmp_path):
    from session import Session
    from store import Store
    from vision import Observation
    from detect import Box
    path = tmp_path / "config.json"
    cfg = config.load(path)
    cfg["monitor"] = 2
    config.save(cfg, path)
    db = Store(tmp_path / "test.db")
    live = Session(db, scanner=lambda frame: [Observation(Box(10,10,50,24),(35,0),{},None,False)], name_reader=lambda *args: ("",0))
    live.observe(None)
    live.edit(1, "리네", True)
    assert config.load(path)["monitor"] == 2
    assert live.snapshot()[0]["enabled"]
    db.close()
