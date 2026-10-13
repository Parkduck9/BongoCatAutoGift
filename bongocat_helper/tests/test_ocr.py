from pathlib import Path

import numpy as np
import pytest

import ocr

FONT = Path(r"C:\Windows\Fonts\malgun.ttf")
MODEL = Path(__file__).resolve().parent.parent / "models" / ocr.MODEL_FILE
real_ocr = pytest.mark.skipif(not (FONT.exists() and MODEL.exists()), reason="font or OCR model missing")


@pytest.mark.parametrize("s", ["156 758", "03:29", "100", "1000", "1,000", " 12.5 "])
def test_is_numeric_true(s):
    assert ocr.is_numeric(s)


@pytest.mark.parametrize("s", ["리네", "야옹 1", "", "abc"])
def test_is_numeric_false(s):
    assert not ocr.is_numeric(s)


def test_normalize_strips_spaces_and_nfc():
    decomposed = "\u1105\u1175\u1102\u1166"  # 리네 as conjoining jamo
    assert ocr.normalize(f"  {decomposed} ") == "리네"
    assert ocr.normalize("리 네") == "리네"


def blank(h=60, w=120):
    return np.full((h, w, 3), 255, np.uint8)


def test_ink_mask_handles_both_polarities():
    img = blank()
    img[20:30, 10:50] = 0
    assert ocr.ink_mask(img).sum() == 10 * 40
    assert ocr.ink_mask(255 - img).sum() == 10 * 40  # light text on dark box


def test_split_lines_finds_rows_and_ink_extent():
    img = blank(80, 120)
    img[10:22, 30:90] = 0
    img[40:52, 20:60] = 0
    assert ocr.split_lines(img) == [(30, 10, 60, 12), (20, 40, 40, 12)]


def test_split_lines_empty_image():
    assert ocr.split_lines(blank()) == []


def render(lines, size=20):
    from PIL import Image, ImageDraw, ImageFont

    if isinstance(lines, str):
        lines = [lines]
    font = ImageFont.truetype(str(FONT), size)
    width = 40 + size * max(len(l) for l in lines)
    img = Image.new("RGB", (width, size // 2 + int(size * 1.6) * len(lines)), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((20, size // 4 + int(size * 1.6) * i), line, fill="black", font=font)
    return np.array(img)[:, :, ::-1].copy()  # RGB -> BGR


NAMES = ["리네", "철수", "민지", "하늘", "김철수", "봉고", "고양이", "수아", "지민", "태양"]


@real_ocr
@pytest.mark.parametrize("size", [14, 20, 28])
def test_recognize_names(size):
    got = [ocr.normalize(ocr.recognize(render(n, size))[0]) for n in NAMES]
    assert got == NAMES


@real_ocr
def test_read_lines_two_line_bubble_with_offset():
    lines = ocr.read_lines(render(["야옹 야옹", "선물 고마워"]), offset=(100, 200))
    assert [l.text for l in lines] == ["야옹 야옹", "선물 고마워"]
    assert lines[0].y < lines[1].y
    assert all(l.x >= 100 and l.y >= 200 for l in lines)


@real_ocr
def test_read_lines_drops_numeric():
    assert ocr.read_lines(render("156 758")) == []


def test_word_gaps_ignores_syllable_gaps():
    mask = np.zeros((10, 80), bool)
    for x in (0, 10, 20):       # syllables 8px wide, 2px apart
        mask[:, x:x + 8] = True
    for x in (40, 50):          # 12px gap before this word
        mask[:, x:x + 8] = True
    assert ocr.word_gaps(mask, 10) == [34.0]


def test_insert_spaces_by_relative_position():
    assert ocr.insert_spaces("야옹야옹", [50], 0, 100) == "야옹 야옹"
    assert ocr.insert_spaces("리네", [], 0, 100) == "리네"


@pytest.mark.parametrize("s", ["155580|", "|157 444", "1'000", "03:29."])
def test_is_numeric_ignores_ocr_junk_around_digits(s):
    assert ocr.is_numeric(s)


@pytest.mark.parametrize("s", ["리네1", "ㅋㅋ", "Rine"])
def test_is_numeric_false_for_names_with_letters(s):
    assert not ocr.is_numeric(s)
