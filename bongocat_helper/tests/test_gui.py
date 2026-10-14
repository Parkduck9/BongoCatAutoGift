import tkinter as tk
import pytest
import numpy as np
import gui
import config
from vision import Observation
from detect import Box

@pytest.fixture
def app(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'BASE_DIR',tmp_path)
    monkeypatch.setattr(config,'load',lambda: {'monitor':1,'dry_run':True})
    monkeypatch.setattr(config,'save',lambda cfg: None)
    class Cap:
        def monitors(self):return [{}, {'left':0,'top':0}, {'left':1920,'top':0}]
        def close(self):pass
    monkeypatch.setattr(gui.capture,'Capturer',Cap)
    root=tk.Tk();root.withdraw()
    live=gui.App(root)
    live.runner.session.scanner=lambda frame:[Observation(Box(100,100,80,24),(140,80),{},None,False)]
    live.runner.session.name_reader=lambda frame,ob:('',0)
    live.runner.session.observe(np.zeros((200,400,3),np.uint8))
    live.show_rows(live.runner.session.snapshot())
    yield live
    live.runner.stop()
    if live.runner._thread:live.runner._thread.join(5)
    live.db.close();root.destroy()

def select(app):
    app.table.selection_set('1');app.select()

def test_unknown_cat_has_row_unchecked_and_can_be_corrected(app):
    select(app)
    app.name.set('리네');app.checked.set(True);app.save_cat()
    row=app.runner.session.snapshot()[0]
    assert row['name']=='리네' and row['enabled']

def test_refresh_does_not_overwrite_name_being_typed(app):
    select(app);app.root.update()
    app.name.set('수정 중')
    app.show_rows(app.runner.session.snapshot());app.root.update()
    assert app.name.get()=='수정 중'

def test_touch_button_enqueues_one_selected_cat_even_unchecked(app,monkeypatch):
    calls=[]
    monkeypatch.setattr(app.runner,'start',lambda *args:calls.append(args))
    select(app);app.touch()
    assert calls==[('touch',1)]

def test_chat_tab_shows_estimated_and_failed(app):
    app.db.add_chat(100,'리네','야용',status='estimated',score=.6)
    app.db.add_chat(101,'리네','채팅 로그 기록에 실패했습니다.',status='failed')
    app.refresh_chat()
    values=[app.chat.item(item,'values') for item in app.chat.get_children()]
    assert [row[2] for row in values]==['추정','실패']

def test_monitor_change_clears_permissions_and_cat_positions(app):
    select(app);app.checked.set(True);app.save_cat()
    app.monitor.set('2');app.change_monitor()
    assert not app.runner.session.cats and not app.table.get_children()

def test_start_has_no_calibration_gate_and_defaults_to_practice(app,monkeypatch):
    calls=[]
    monkeypatch.setattr(app.runner,'start',lambda *args:calls.append(args))
    app.start('scan')
    assert calls==[('scan',)] and app.cfg['dry_run']
