import pytest
import datetime

import chatlog
import detect
import scene
import store

LAYOUT = [(200, 390, "리네", True, "야옹 야옹"), (520, 250, "철수", False, "선물 고마워요"), (800, 380, "민지", True)]


def test_dedup_records_first_sighting_and_again_after_gap():
    d = chatlog.ChatDedup(gap_sec=8)
    assert d.observe("리네", "야옹 야옹", now=0)
    assert not d.observe("리네", "야옹야옹", now=3)        # same text (spacing ignored), still showing
    assert not d.observe("리네", "야옹 야옹", now=10)      # seen 7 s ago -> same bubble
    assert d.observe("리네", "야옹 야옹", now=30)          # said again later
    assert d.observe("민지", "야옹 야옹", now=30)          # other speaker


def test_store_chat_query_filters_and_dates(tmp_path):
    db = store.Store(tmp_path / "bongo.db")
    t = datetime.datetime(2026, 10, 12, 14, 2, 12).timestamp()
    db.add_chat(t, "리네", "야옹 야옹")
    db.add_chat(t + 3, "민지", "안녕하세요")
    db.add_chat(t + 86400, "리네", "또 왔어요")
    assert db.chat_dates() == ["2026-10-12", "2026-10-13"]
    assert [r[2] for r in db.query_chat(date="2026-10-12")] == ["야옹 야옹", "안녕하세요"]
    assert [r[2] for r in db.query_chat(speaker="리네")] == ["야옹 야옹", "또 왔어요"]
    assert [r[2] for r in db.query_chat(keyword="안녕")] == ["안녕하세요"]
    assert db.chat_speakers("2026-10-12") == ["리네", "민지"]


def test_export_md_groups_by_date(tmp_path):
    t = datetime.datetime(2026, 10, 12, 14, 2, 12).timestamp()
    rows = [(t, "리네", "야옹 야옹"), (t + 3, "민지", "안녕하세요"), (t + 86400, "리네", "또 왔어요")]
    path = chatlog.export_md(rows, tmp_path, title_hint="리네")
    text = path.read_text(encoding="utf-8")
    assert path.name == "chat_2026-10-12_2026-10-13_리네.md"
    assert "## 2026-10-12" in text and "## 2026-10-13" in text
    assert "- **14:02:12** 리네: 야옹 야옹" in text


def test_find_bubble_boxes_finds_bubbles_not_tags_or_bodies():
    img, truth = scene.scene(LAYOUT, w=1000)
    tags = detect.find_tag_boxes(img, scene.TAG_H)
    bubbles = detect.find_bubble_boxes(img, scene.TAG_H, exclude=tags)
    expected = sorted(t["bubble"][:2] for t in truth if "bubble" in t)
    got = sorted((b.x, b.y) for b in bubbles)
    assert len(got) == 2
    for (gx, gy), (ex, ey) in zip(got, expected):
        assert abs(gx - ex) <= 4 and abs(gy - ey) <= 4


def test_bubble_reader_reads_text_once_and_names_speaker(tmp_path):
    img, truth = scene.scene(LAYOUT, w=1000)
    import cats
    from test_cats import FakeOcr, settle

    reg = cats.CatRegistry(FakeOcr(truth))
    settle(reg, detect.find_tag_boxes(img, scene.TAG_H), img)
    reads = []

    def read(crop):
        import ocr
        lines = ocr.read_lines(crop)
        reads.append(lines)
        return lines

    br = chatlog.BubbleReader(read=read, settle_sec=0.5)
    said = []
    for t in (0, 1, 2, 3):
        boxes = detect.find_bubble_boxes(img, scene.TAG_H, exclude=detect.find_tag_boxes(img, scene.TAG_H))
        said += br.update(boxes, img, t, reg, scene.OFF_BUBBLE, max_dist=80)
    assert sorted(said) == [("리네", "야옹 야옹"), ("철수", "선물 고마워요")]
    assert len(reads) == 2                                  # each bubble read once


REAL = scene.Path(__file__).parent / "fixtures" / "real_zone_rine.png"


@pytest.mark.skipif(not REAL.exists(), reason="real-game capture is kept out of the public repo")
def test_no_false_bubbles_on_real_crop():
    import cv2

    img = cv2.imread(str(REAL))
    tags = detect.find_tag_boxes(img, 20)
    assert detect.find_bubble_boxes(img, 20, exclude=tags) == []


def test_round_button_is_not_a_bubble():
    """A round '?' help button (like the one on the real 2560x1440 desktop that used to
    pass) must not count as a bubble."""
    import cv2

    square = scene.background(200, 200)
    cv2.circle(square, (100, 100), 30, (250, 250, 250), -1)
    cv2.putText(square, "?", (88, 112), cv2.FONT_HERSHEY_SIMPLEX, 1, (40, 40, 40), 2)
    assert detect.find_bubble_boxes(square, 20) == []
