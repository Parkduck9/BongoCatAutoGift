"""Read-only review reproductions: synthetic frames and a fake mouse only."""
import json
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1] / 'bongocat_helper'
sys.path[:0] = [str(PROJECT), str(PROJECT / 'tests')]

import numpy as np
import cats
import chatlog
import detect
import ocr
import scene
from test_engine import Frames, frame, make, run


def changed_owner_before_click():
    old, _ = frame()
    fresh, _ = scene.scene([(150, 390, '철수'), (450, 220, '철수'), (750, 320, '민지')])
    with tempfile.TemporaryDirectory() as directory:
        eng, clock, mouse, db, _ = make(Path(directory), [old], targets=('리네',), dry_run=False)
        try:
            run(eng, clock, 1)
            original_read = eng.registry.read
            reads = []

            def read(crop, box):
                if box.c[0] < 200:
                    name = '리네' if np.array_equal(crop, cats.tag_interior(old, box)) else '철수'
                    reads.append(name)
                    return name, 0.99
                return original_read(crop, box)

            eng.registry.read = read
            eng.grab = Frames(old, fresh)
            eng.tick()
            return {'fresh_screen_owner': '철수', 'targets': ['리네'],
                    'name_reads': reads, 'fake_clicks': mouse.clicks,
                    'bug_reproduced': bool(mouse.clicks) and '철수' not in reads}
        finally:
            db.close()


def new_bubble_after_disappearance():
    zone = scene.background(300, 200)
    box = detect.Box(20, 20, 120, 30)
    reg = cats.CatRegistry()
    current = ['first message']
    reader = chatlog.BubbleReader(read=lambda crop: [ocr.Line(current[0], 0, 0, 100, 20, 0.99)])
    whole = [(0, 0, 300, 200)]
    reader.update([box], zone, 0, reg, None, 30, whole)
    first = reader.update([box], zone, 1, reg, None, 30, whole)
    reader.update([], zone, 2, reg, None, 30, whole)
    reader.update([], zone, 3, reg, None, 30, [])
    reader.update([], zone, 4, reg, None, 30, [])
    current[0] = 'second message'
    second = reader.update([box], zone, 5, reg, None, 30, whole)
    second += reader.update([box], zone, 6, reg, None, 30, whole)
    return {'first_recorded': first, 'second_recorded': second,
            'bug_reproduced': bool(first) and not second}


print(json.dumps({'changed_owner': changed_owner_before_click(),
                  'new_bubble': new_bubble_after_disappearance()}, ensure_ascii=True, indent=2))
