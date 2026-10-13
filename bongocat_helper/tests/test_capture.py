import numpy as np
import pytest

import capture


def frame(h=100, w=200):
    return np.arange(h * w * 3, dtype=np.uint32).reshape(h, w, 3).astype(np.uint8)


def test_crop_returns_region():
    f = frame()
    out = capture.crop(f, [10, 20, 30, 40])
    assert out.shape == (40, 30, 3)
    assert np.array_equal(out, f[20:60, 10:40])


def test_crop_clamps_to_frame():
    out = capture.crop(frame(), [190, 90, 50, 50])
    assert out.shape == (10, 10, 3)


@pytest.mark.parametrize("rect", [[0, 0, 0, 10], [0, 0, 10, -1], [300, 0, 10, 10], [0, 200, 10, 10]])
def test_crop_rejects_empty_or_outside(rect):
    with pytest.raises(ValueError):
        capture.crop(frame(), rect)


def test_to_screen_adds_monitor_origin():
    mon = {"left": -1920, "top": 0, "width": 1920, "height": 1080}
    assert capture.to_screen(mon, 100, 50) == (-1820, 50)
    assert capture.to_screen(mon, 100, 50, region=[10, 20, 0, 0]) == (-1810, 70)
