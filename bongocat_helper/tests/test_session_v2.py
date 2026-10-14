"""Production TDD for the cat-list design; all mouse input is replaced with a fake."""
from dataclasses import replace
import numpy as np
import pytest

import session
from detect import Box
from store import Store
from vision import Observation


FRAME = np.zeros((200, 400, 3), np.uint8)


class Clock:
    value = 100
    def __call__(self):
        return self.value


class Mouse:
    def __init__(self):
        self.clicks = []
    def click(self, x, y, abort=lambda: False):
        if abort():
            from clicker import ClickAborted
            raise ClickAborted()
        self.clicks.append((x, y))


@pytest.fixture
def world(tmp_path):
    a = Observation(Box(100, 120, 80, 24), (140, 96), {"left": Box(75, 85, 24, 24)}, None, False)
    b = Observation(Box(240, 120, 80, 24), (280, 96), {}, None, False)
    state = {"observations": [a, b], "names": {100: ("Alucard", .99), 240: ("", 0)}, "reads": []}
    clock = Clock()
    db = Store(tmp_path / "data.db")
    def read(frame, observation):
        state["reads"].append(observation.box.x)
        return state["names"].get(observation.box.x, ("", 0))
    live = session.Session(db, scanner=lambda frame: state["observations"], name_reader=read,
                           chat_reader=lambda frame, box: ("야옹 야옹", .99), clock=clock)
    mouse = Mouse()
    yield live, state, clock, db, mouse, a, b
    db.close()


def test_all_cats_are_kept_with_fixed_ids_and_unknown_names(world):
    live, *_ = world
    live.observe(FRAME)
    assert isinstance(live.cats, dict) and len(live.cats) == 2
    assert [row["name"] for row in live.snapshot()] == ["Alucard", "이름 미확인"]
    assert not any(row["enabled"] for row in live.snapshot())


def test_static_positions_are_not_ocr_read_again(world):
    live, state, *_ = world
    live.observe(FRAME)
    live.observe(FRAME)
    assert state["reads"] == [100, 240]


def test_manual_name_and_check_are_preserved(world):
    live, *_ = world
    live.observe(FRAME)
    cat_id = live.snapshot()[1]["id"]
    live.edit(cat_id, "리네", True)
    live.observe(FRAME)
    row = next(row for row in live.snapshot() if row["id"] == cat_id)
    assert row["name"] == "리네" and row["enabled"]


def test_unchecked_cat_never_clicks(world):
    live, state, clock, db, mouse, *_ = world
    live.observe(FRAME)
    live.send_gift(1, "left", FRAME, mouse, {"left": -1920, "top": 0})
    assert mouse.clicks == []


def test_checked_cat_gift_uses_fresh_coordinates_and_monitor_origin(world):
    live, state, clock, db, mouse, *_ = world
    live.observe(FRAME)
    live.edit(1, "Alucard", True)
    live.send_gift(1, "left", FRAME, mouse, {"left": -1920, "top": 100})
    assert mouse.clicks == [(-1833, 197)]


def test_wrong_fresh_name_blocks_and_clears_permission(world):
    live, state, clock, db, mouse, *_ = world
    live.observe(FRAME)
    live.edit(1, "Alucard", True)
    state["names"][100] = ("다른고양이", .99)
    live.send_gift(1, "left", FRAME, mouse, {"left": 0, "top": 0})
    assert not mouse.clicks
    assert not any(row["enabled"] for row in live.snapshot())


def test_stale_position_blocks_touch(world):
    live, state, clock, db, mouse, a, b = world
    live.observe(FRAME)
    state["observations"] = [replace(a, box=Box(110, 120, 80, 24)), b]
    live.touch(1, FRAME, mouse, {"left": 0, "top": 0})
    assert mouse.clicks == []


def test_touch_button_clicks_body_once_even_if_gift_unchecked(world):
    live, state, clock, db, mouse, *_ = world
    live.observe(FRAME)
    live.touch(1, FRAME, mouse, {"left": 10, "top": 20})
    assert mouse.clicks == [(150, 116)]


def test_stop_request_blocks_touch_and_gift(world):
    live, state, clock, db, mouse, *_ = world
    live.observe(FRAME)
    live.edit(1, "Alucard", True)
    live.touch(1, FRAME, mouse, {"left": 0, "top": 0}, should_stop=lambda: True)
    live.send_gift(1, "left", FRAME, mouse, {"left": 0, "top": 0}, should_stop=lambda: True)
    assert not mouse.clicks


def test_one_ocr_per_bubble_and_three_second_block(world):
    live, state, clock, db, mouse, a, b = world
    bubble = Box(35, 45, 110, 26)
    state["observations"] = [replace(a, bubble=bubble), b]
    reads = []
    live.chat_reader = lambda frame, box: reads.append(True) or ("Hello 야옹", .99)
    live.observe(FRAME)
    for t in (101, 102, 103, 104):
        clock.value = t
        live.observe(FRAME)
    assert len(reads) == 1 and len(db.query_chat()) == 1
    state["observations"] = [a, b]
    clock.value = 105
    live.observe(FRAME)
    state["observations"] = [replace(a, bubble=bubble), b]
    live.observe(FRAME)
    assert len(reads) == 2


def test_new_bubble_before_three_seconds_waits(world):
    live, state, clock, db, mouse, a, b = world
    state["observations"] = [replace(a, bubble=Box(35, 45, 110, 26)), b]
    live.observe(FRAME)
    state["observations"] = [a, b]
    clock.value = 101
    live.observe(FRAME)
    state["observations"] = [replace(a, bubble=Box(15, 45, 130, 26)), b]
    clock.value = 102.99
    live.observe(FRAME)
    assert len(db.query_chat()) == 1
    clock.value = 103
    live.observe(FRAME)
    assert len(db.query_chat()) == 2


def test_low_confidence_is_saved_as_estimated_once(world):
    live, state, clock, db, mouse, a, b = world
    state["observations"] = [replace(a, bubble=Box(35, 45, 110, 26)), b]
    live.chat_reader = lambda frame, box: ("야용 야용", .62)
    live.observe(FRAME)
    rows = db.query_chat_records()
    assert rows[0]["text"] == "야용 야용" and rows[0]["status"] == "estimated"
    assert rows[0]["cat_id"] == 1 and rows[0]["score"] == .62


@pytest.mark.parametrize("result", [("こんにちは", .99), ("你好", .99), ("Привет", .99)])
def test_other_decoded_scripts_are_skipped(world, result):
    live, state, clock, db, mouse, a, b = world
    state["observations"] = [replace(a, bubble=Box(35, 45, 110, 26)), b]
    live.chat_reader = lambda frame, box: result
    live.observe(FRAME)
    assert db.query_chat() == []


def test_failed_ocr_is_logged_once_without_three_retries(world):
    live, state, clock, db, mouse, a, b = world
    state["observations"] = [replace(a, bubble=Box(35, 45, 110, 26)), b]
    attempts = []
    def fail(frame, box):
        attempts.append(True)
        raise RuntimeError("failed")
    live.chat_reader = fail
    for t in range(100, 110):
        clock.value = t
        live.observe(FRAME)
    assert len(attempts) == 1 and db.query_chat_records()[0]["status"] == "failed"


def test_unique_movement_retains_id_but_room_exit_removes_it(world):
    live, state, clock, db, mouse, a, b = world
    live.observe(FRAME)
    live.edit(1, "Alucard", True)
    state["observations"] = [replace(a, box=Box(110, 120, 80, 24)), b]
    state["names"][110] = ("Alucard", .99)
    live.observe(FRAME)
    assert live.snapshot()[0]["id"] == 1 and live.snapshot()[0]["enabled"]
    state["observations"] = []
    live.observe(FRAME)
    assert not live.cats


def test_same_visible_gift_is_not_clicked_twice(world):
    live, state, clock, db, mouse, *_ = world
    live.observe(FRAME)
    live.edit(1, "Alucard", True)
    for _ in range(2):
        live.send_gift(1, "left", FRAME, mouse, {"left": 0, "top": 0})
    assert len(mouse.clicks) == 1

def test_duplicate_names_do_not_transfer_permission_to_moved_cat(world):
    live,state,clock,db,mouse,a,b=world
    state['names'][240]=('Alucard',.99)
    live.observe(FRAME);live.edit(1,'Alucard',True)
    state['observations']=[replace(a,box=Box(110,120,80,24)),b]
    state['names'][110]=('Alucard',.99)
    live.observe(FRAME)
    rows=live.snapshot()
    assert not any(row['enabled'] for row in rows)
    assert {row['id'] for row in rows}=={2,3}


def test_completed_gift_is_confirmed_only_when_icon_disappears(world):
    live,state,clock,db,mouse,a,b=world
    live.observe(FRAME);live.edit(1,'Alucard',True)
    live.send_gift(1,'left',FRAME,mouse,{'left':0,'top':0})
    assert db.count_gifts(0)==0
    clock.value=102
    state['observations']=[replace(a,gifts={}),b]
    live.observe(FRAME)
    assert db.count_gifts(0)==1


def test_room_exit_after_click_is_unverified_not_success(world):
    live,state,clock,db,mouse,a,b=world
    live.observe(FRAME);live.edit(1,'Alucard',True)
    live.send_gift(1,'left',FRAME,mouse,{'left':0,'top':0})
    state['observations']=[];live.observe(FRAME)
    assert db.count_gifts(0)==0 and db.recent_gifts(0)[-1][3]=='unverified'

def test_saving_same_name_does_not_resend_visible_gift(world):
    live,state,clock,db,mouse,a,b=world
    live.observe(FRAME);live.edit(1,'Alucard',True)
    live.send_gift(1,'left',FRAME,mouse,{'left':0,'top':0})
    live.edit(1,'Alucard',True)
    live.send_gift(1,'left',FRAME,mouse,{'left':0,'top':0})
    assert len(mouse.clicks)==1


def test_corrected_low_confidence_name_can_use_matching_fresh_ocr(world):
    live,state,clock,db,mouse,a,b=world
    state['names'][100]=('리네?',.3)
    live.observe(FRAME);live.edit(1,'리네',True)
    live.send_gift(1,'left',FRAME,mouse,{'left':0,'top':0})
    assert len(mouse.clicks)==1


def test_stop_after_cursor_move_blocks_touch_and_gift(world):
    from clicker import ClickAborted
    live,state,clock,db,mouse,a,b=world
    live.observe(FRAME);live.edit(1,'Alucard',True)
    class LateStop:
        def click(self,x,y,*,abort):
            raise ClickAborted()
    late=LateStop()
    assert live.touch(1,FRAME,late,{'left':0,'top':0}) is False
    assert live.send_gift(1,'left',FRAME,late,{'left':0,'top':0}) is False
    assert not db.recent_gifts(0)
