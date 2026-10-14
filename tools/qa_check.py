"""Additional QA; temporary config/DB only, no real mouse or game actions."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'bongocat_helper'), str(ROOT / 'bongocat_helper' / 'tests')]

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cats
import chatlog
import config
import detect
import gui
import ocr
import scene


def animated_bubble():
    zone = scene.background(300, 200)
    box = detect.Box(20, 20, 120, 30)
    reads = []

    def read(crop):
        reads.append(True)
        return [ocr.Line('hello', 0, 0, 60, 20, 0.99)]

    reader = chatlog.BubbleReader(read=read)
    reg = cats.CatRegistry()
    said = []
    for t in range(10):
        zone[30, 30] = (t, t, t)
        said += reader.update([box], zone, t, reg, None, 30, [(0, 0, 300, 200)])
    return {'frames': 10, 'ocr_calls': len(reads), 'saved': said,
            'issue_reproduced': len(reads) == 0}


def duplicate_same_visible_message():
    zone = scene.background(300, 200)
    box = detect.Box(20, 20, 120, 30)
    reader = chatlog.BubbleReader(read=lambda crop: [ocr.Line('hello', 0, 0, 60, 20, 0.99)])
    reg, dedup = cats.CatRegistry(), chatlog.ChatDedup()
    saved = []
    for t in range(13):
        if t == 10:
            zone[30, 30] = (0, 0, 0)
        for who, text in reader.update([box], zone, t, reg, None, 30, [(0, 0, 300, 200)]):
            if dedup.observe(who, text, t):
                saved.append((t, who, text))
    return {'saved': saved, 'issue_reproduced': len(saved) == 2}


def calibration_overwritten_by_target_edit():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'config.json'
        app = gui.App.__new__(gui.App)
        app.cfg_path, app.cfg = path, config.load(path)
        app._show_targets = lambda: None
        class Entry:
            def delete(self, *args):
                pass
        app.ent_target = Entry()
        calibrated = config.load(path)
        calibrated.update(monitor=2, region=[100, 100, 600, 400], tag={'height': 26, 'aspect': 2})
        config.save(calibrated, path)  # GUI setup runs in another process.
        app.add_target('리네')
        saved = config.load(path)
        return {'before_monitor': 2, 'after_monitor': saved['monitor'],
                'after_region': saved['region'], 'after_tag_height': saved['tag']['height'],
                'issue_reproduced': saved['monitor'] != 2 or not saved['region'][2]}


def real_language_ocr():
    font = ImageFont.truetype(r'C:\Windows\Fonts\malgun.ttf', 24)
    results = []
    missing = font.getmask('\U0010ffff')
    missing_signature = (missing.size, bytes(missing))
    for text in ('안녕하세요', '선물 고마워요', '야옹 야옹'):
        image = Image.new('RGB', (300, 60), 'white')
        ImageDraw.Draw(image).text((20, 10), text, fill='black', font=font)
        lines = ocr.read_lines(np.array(image)[:, :, ::-1].copy())
        actual = ' '.join(line.text for line in lines)
        results.append({'expected': text, 'actual': actual,
                        'font_missing_chars': [char for char in text if char != ' ' and
                                               (font.getmask(char).size, bytes(font.getmask(char))) == missing_signature],
                        'exact_match': ocr.normalize(actual) == ocr.normalize(text)})
    return results


def failed_ocr_then_new_text():
    zone = scene.background(300, 200)
    box = detect.Box(30, 20, 120, 30)
    reg = cats.CatRegistry()
    calls = []
    failures = []
    text = [None]

    def read(crop):
        calls.append(text[0])
        return [] if text[0] is None else [ocr.Line(text[0], 0, 0, 100, 20, 0.99)]

    reader = chatlog.BubbleReader(read=read, settle_sec=0,
                                  on_failure=lambda name, attempt, total: failures.append((name, attempt, total)))
    for now in (0, 1, 2):
        reader.update([box], zone, now, reg, None, 30, [(0, 0, 300, 200)])
    text[0] = '새 문장'
    saved = []
    for now in range(3, 10):
        saved += reader.update([box], zone, now, reg, None, 30, [(0, 0, 300, 200)])
    return {'first_failed_reads': 3, 'total_ocr_calls': len(calls),
            'failure_logs': failures, 'new_sentence_saved': saved,
            'expected_rule': 'log each failure; ignore this bubble after three failures',
            'issue_reproduced': len(calls) != 3 or len(failures) != 3 or bool(saved)}


def resized_bubble_bypasses_position_block():
    zone = scene.background(300, 200)
    original = detect.Box(100, 20, 120, 30)
    wider = detect.Box(80, 20, 140, 30)  # right edge/attachment stays at x=220
    reg = cats.CatRegistry()
    text = ['첫 문장']
    reader = chatlog.BubbleReader(read=lambda crop: [ocr.Line(text[0], 0, 0, 100, 20, 0.99)])
    reader.update([original], zone, 0, reg, None, 30, [(0, 0, 300, 200)])
    first = reader.update([original], zone, 1, reg, None, 30, [(0, 0, 300, 200)])
    text[0] = '다른 문장'
    reader.update([wider], zone, 2, reg, None, 30, [(0, 0, 300, 200)])
    second = reader.update([wider], zone, 3, reg, None, 30, [(0, 0, 300, 200)])
    return {'first_at_second_1': first, 'second_at_second_3': second,
            'same_right_edge': original.x + original.w == wider.x + wider.w,
            'issue_reproduced': bool(second)}


report = {'animation_delays_ocr': animated_bubble(),
          'same_visible_sentence_duplicated': duplicate_same_visible_message(),
          'setup_lost_after_target_edit': calibration_overwritten_by_target_edit(),
          'real_korean_ocr': real_language_ocr(),
          'three_failed_ocr_reads_then_ignore': failed_ocr_then_new_text(),
          'resized_bubble_bypasses_4sec_block': resized_bubble_bypasses_position_block()}
destination = ROOT / 'docs' / 'md' / 'qa_results_4sec_2026-10-14.json'
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=True, indent=2))
