"""Calibration save dialog without native windows, screen capture, or input clicks."""
from types import SimpleNamespace

import pytest
from tkinter import messagebox

import bongo
import calib
import config
import scene
from test_setup import user_rects


@pytest.mark.parametrize("confirm", [True, False])
def test_setup_popup_saves_or_cancels_explicitly(tmp_path, monkeypatch, confirm):
    img, truth = scene.scene([(200, 390, "리네"), (500, 250, "철수")])
    selected = user_rects(truth, 0)
    path = tmp_path / "config.json"
    load, save = config.load, config.save
    initial = load(path)
    latest = load(path)
    latest["targets"] = ["민지"]  # edited while setup was open
    save(latest, path)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "load", lambda: load(path))
    monkeypatch.setattr(config, "save", lambda cfg: save(cfg, path))
    monkeypatch.setattr(bongo, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(bongo, "_imread", lambda path: img)
    monkeypatch.setattr(calib, "select_rects", lambda *args, **kwargs: selected)
    monkeypatch.setattr(calib, "verify", lambda *args, **kwargs: calib.Report(2, 4, 4, ["리네", "철수"], img))
    monkeypatch.setattr(calib, "show", lambda *args: None)
    monkeypatch.setattr(messagebox, "askyesno", lambda *args: confirm)
    result = bongo.cmd_setup(SimpleNamespace(bubble=False, image="fake.png", monitor=2), initial)
    stored = load(path)
    assert stored["targets"] == ["민지"]
    if confirm:
        assert result is None
        assert stored["monitor"] == 2 and stored["region"][2] > 0
        assert (tmp_path / "templates" / "gift_left.png").exists()
    else:
        assert result == 1
        assert stored["region"] == [0, 0, 0, 0]
