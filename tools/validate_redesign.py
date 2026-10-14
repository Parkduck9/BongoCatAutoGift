"""Validate the design against reference images and virtual actions, never the OS mouse."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bongocat_helper"))

import cv2
import numpy as np
import cats
import detect
import ocr
from redesign_model import CatTable, ChatRecorder, Position, supported_text

CHECKS = []


def check(name, condition):
    assert condition, name
    CHECKS.append(name)


def white_regions(image):
    """Nested contours retain a bubble even when the surrounding desktop is white."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    h_img, w_img = gray.shape
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if x <= 0 or y <= 0 or x + w >= w_img or y + h >= h_img:
            continue
        if w >= 45 and 16 <= h <= 36 and cv2.contourArea(contour) / (w * h) >= 0.65:
            boxes.append((x, y, w, h))
    return boxes


def image_checks():
    paths = [Path(r"C:\Users\User\AppData\Local\Temp\codex-clipboard-a4284e2a-91b7-423c-9b0b-9f58428ee333.png"),
             Path(r"C:\Users\User\AppData\Local\Temp\codex-clipboard-0bdae648-30b1-4086-9148-eb8f44c4784e.png")]
    first, second = [cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR) for path in paths]
    boxes = detect.find_tag_boxes(first, 20)
    check("reference_1_name_region", len(boxes) == 1)
    name, score = ocr.recognize(cats.tag_interior(first, boxes[0]))
    check("reference_1_english_name", name == "Alucard")
    templates = [first[81:105, 43:67], first[82:106, 154:178]]
    gifts = sorted(detect.find_templates(first, templates, 0.95, scale=1), key=lambda hit: hit.x)
    check("reference_1_two_gift_positions", len(gifts) == 2 and gifts[0].c[0] < boxes[0].c[0] < gifts[1].c[0])
    bubble_boxes = [box for box in white_regions(second) if box[1] < second.shape[0] // 2]
    check("reference_2_bubble_on_white_background", len(bubble_boxes) == 1)
    counter_boxes = [box for box in white_regions(second) if box[1] > second.shape[0] // 2]
    check("reference_2_retains_unnamed_cat_anchor", len(counter_boxes) == 1)
    cx, cy, cw, ch = counter_boxes[0]
    counter, counter_score = ocr.recognize(second[cy + 2:cy + ch - 2, cx + 2:cx + cw - 2])
    own_table = CatTable()
    own_position = Position(2, (cx + cw // 2, cy + ch // 2), (162, 120), {})
    own_table.scan([own_position], lambda position: (counter, counter_score))
    check("reference_2_number_is_not_a_player_name", len(own_table.cats) == 1 and next(iter(own_table.cats.values())).name == "이름 미확인")
    x, y, w, h = bubble_boxes[0]
    crop = second[y:y + h, x:x + w]
    reads = []

    def read_once():
        reads.append(True)
        return [ocr.recognize(crop)]

    chat = ChatRecorder()
    row = chat.appeared(1, 0, read_once)
    for now in (1, 2, 3, 4, 5):
        chat.appeared(1, now, read_once)
    check("reference_2_one_ocr_call_and_one_log", len(reads) == 1 and len(chat.logs) == 1)
    check("reference_2_preserves_best_candidate", row is not None and row[3] in ("recognized", "estimated"))
    return {"first_image": {"name": name, "score": score, "name_box": vars(boxes[0]),
                            "gift_centers": [hit.c for hit in gifts]},
            "second_image": {"bubble_box": bubble_boxes[0], "saved_text": row[2],
                             "status": row[3], "score": row[4], "ocr_calls": len(reads),
                             "name_present": False, "counter_box": counter_boxes[0],
                             "counter_text": counter, "cat_records": len(own_table.cats)},
            "limits": ["Reference matching does not establish all-monitor detection accuracy.",
                       "A best OCR hypothesis is not proof of the intended text.",
                       "Decoded-script filtering cannot reject foreign text misread as Latin/Hangul."]}


def model_checks():
    p1 = Position(2, (110, 126), (110, 93), {"left": (55, 93), "right": (166, 93)})
    p2 = Position(2, (300, 126), (300, 93), {})
    table, reads = CatTable(), []
    table.scan([p1, p2], lambda position: reads.append(position) or ("Alucard", 0.99))
    check("duplicate_names_get_distinct_ids", len(table.cats) == 2 and len(set(table.cats)) == 2)
    table.scan([p1, p2], lambda position: reads.append(position) or ("Alucard", 0.99))
    check("unchanged_positions_do_not_repeat_name_ocr", len(reads) == 2)
    check("gift_defaults_to_unchecked", all(not cat.allow_gift for cat in table.cats.values()))
    cat_id = next(iter(table.cats))
    check("unchecked_cat_receives_no_gift", table.gift_action(cat_id, "left", p1, "Alucard") is None)
    table.edit(cat_id, "Alucard", True)
    check("checked_cat_receives_only_its_gift", table.gift_action(cat_id, "left", p1, "Alucard") == ("gift", cat_id, (55, 93)))
    check("fresh_wrong_name_blocks_gift", table.gift_action(cat_id, "left", p1, "다른 고양이") is None)
    check("fresh_wrong_position_blocks_touch", table.touch_action(cat_id, p2) is None)
    virtual_clicks = [table.touch_action(cat_id, p1)]
    check("touch_button_plans_one_body_click", virtual_clicks == [("touch", cat_id, (110, 93))])
    table.scan([], lambda position: ("", 0))
    check("room_exit_clears_positions", not table.cats)
    table.scan([p1], lambda position: ("", 0))
    unknown = next(iter(table.cats.values()))
    table.edit(unknown.id, "리네", False)
    check("unreadable_cat_is_retained_and_editable", unknown.name == "리네" and len(table.cats) == 1)

    movable = CatTable()
    movable.scan([p1], lambda position: ("Alucard", 0.99))
    known = next(iter(movable.cats.values()))
    movable.edit(known.id, "Alucard", True)
    moved = Position(2, (130, 126), (130, 93), {"left": (75, 93)})
    movable.scan([moved], lambda position: ("Alucard", 0.99))
    check("unique_moved_cat_keeps_manual_permission", known.id in movable.cats and movable.cats[known.id].position == moved)
    duplicate = CatTable()
    duplicate.scan([p1, p2], lambda position: ("동명이인", 0.99))
    for record in duplicate.cats.values():
        duplicate.edit(record.id, "동명이인", True)
    moved_second = Position(2, (320, 126), (320, 93), {})
    duplicate.scan([moved, moved_second], lambda position: ("동명이인", 0.99))
    check("ambiguous_movement_does_not_inherit_gift_permission", len(duplicate.cats) == 2 and all(not cat.allow_gift for cat in duplicate.cats.values()))

    chat, calls = ChatRecorder(), []
    low = lambda: calls.append(True) or [("아음 아음", 0.65)]
    first = chat.appeared(1, 0, low)
    check("low_confidence_candidate_is_marked_estimated", first[2:4] == ("아음 아음", "estimated"))
    chat.disappeared(1)
    check("three_second_block", chat.appeared(1, 2.99, low) is None and len(calls) == 1)
    check("new_bubble_can_be_read_at_three_seconds", chat.appeared(1, 3, low) is not None and len(calls) == 2)
    check("korean_and_english_supported", supported_text("Alucard 야옹 123"))
    check("other_decoded_scripts_skipped", not supported_text("こんにちは") and not supported_text("你好") and not supported_text("Привет"))
    failed = ChatRecorder()
    failed.appeared(1, 0, lambda: [])
    failed.appeared(1, 4, lambda: [("재시도하면 안 됨", 1)])
    check("empty_candidate_logs_failure_once", len(failed.logs) == 1 and failed.logs[0][3] == "failed")


model_checks()
images = image_checks()
report = {"scope": "design prototype; production exe unchanged; no real clicks",
          "passed_count": len(CHECKS), "passed": CHECKS, "reference_images": images}
out = ROOT / "docs" / "md" / "redesign_validation.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=True, indent=2))
