import json

import config


def test_load_missing_file_returns_defaults(tmp_path):
    cfg = config.load(tmp_path / "config.json")
    assert cfg == config.DEFAULTS
    assert cfg is not config.DEFAULTS  # must be a copy


def test_load_merges_nested_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"targets": ["리네"], "offsets": {"left": [-40, -90]}}), encoding="utf-8")
    cfg = config.load(path)
    assert cfg["targets"] == ["리네"]
    assert cfg["offsets"]["left"] == [-40, -90]
    assert cfg["offsets"]["right"] == config.DEFAULTS["offsets"]["right"]
    assert cfg["dry_run"] is True


def test_save_then_load_roundtrip_keeps_korean(tmp_path):
    path = tmp_path / "config.json"
    cfg = config.load(path)
    cfg["targets"] = ["리네", "민지"]
    cfg["region"] = [10, 20, 300, 400]
    config.save(cfg, path)
    assert "리네" in path.read_text(encoding="utf-8")
    assert config.load(path) == cfg


def test_save_does_not_leave_temp_file(tmp_path):
    path = tmp_path / "config.json"
    config.save(config.load(path), path)
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]
