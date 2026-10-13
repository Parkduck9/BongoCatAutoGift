"""config.json load/save. Missing keys fall back to DEFAULTS (deep merge)."""
import copy
import json
import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
# user data (config, templates, logs, chat db) lives next to the .exe when frozen
BASE_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
# read-only files bundled into the .exe (OCR model) are unpacked here
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULTS = {
    "monitor": 1,
    "region": [0, 0, 0, 0],          # detection zone [x, y, w, h], monitor-local; set by setup
    "interval_sec": 1.0,
    "targets": [],
    "dry_run": True,
    "match_threshold": 0.85,
    "max_dist": 30,                  # px between a hit and its expected spot (kept small: a cat
                                     # whose tag is cut off by the zone edge cannot compete)
    "ambiguity_px": 20,              # 1st vs 2nd candidate gap below this -> unmatched
    "click_cooldown_sec": 5,
    "chat_gap_sec": 8,
    "cat_ttl_sec": 10,
    "gift_cooldown_sec": 1800,
    "wake_before_sec": 15,
    "late_grace_sec": 60,
    "offsets": {                     # [dx, dy] from name-tag center; set by setup
        "left": None,
        "right": None,
        "bubble": None,
        "number": None,
    },
    "tag": {"height": None, "aspect": None},
    "templates": {
        "gift_left": "templates/gift_left.png",
        "gift_right": "templates/gift_right.png",
    },
}


def _merge(base, override):
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path=CONFIG_PATH):
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(DEFAULTS)
    return _merge(DEFAULTS, json.loads(path.read_text(encoding="utf-8")))


def save(cfg, path=CONFIG_PATH):
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)  # atomic: never leaves a half-written config
