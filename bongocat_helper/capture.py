"""Screen capture (mss) and coordinate helpers. Call set_dpi_aware() before anything else."""
import ctypes

import mss
import numpy as np


def set_dpi_aware():
    # Without this, capture and click coordinates drift apart at 125%/150% scaling.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()


class Capturer:
    """mss handles are thread-bound: create one per thread."""

    def __init__(self):
        self._sct = mss.MSS()

    def monitors(self):
        return self._sct.monitors  # [0] = all monitors combined, [1..] = each monitor

    def monitor(self, index):
        mons = self._sct.monitors
        if not 1 <= index < len(mons):
            raise ValueError(f"monitor {index} not found (have 1..{len(mons) - 1})")
        return mons[index]

    def grab(self, monitor_index, region=None):
        """BGR frame of a monitor, or only `region` [x, y, w, h] (monitor-local) of it."""
        mon = self.monitor(monitor_index)
        box = dict(mon)
        if region and region[2] > 0 and region[3] > 0:
            x, y, w, h = region
            box = {"left": mon["left"] + x, "top": mon["top"] + y, "width": w, "height": h}
        shot = self._sct.grab(box)
        return np.ascontiguousarray(np.asarray(shot)[:, :, :3])  # BGRA -> BGR

    def close(self):
        self._sct.close()


def crop(frame, rect):
    """Crop [x, y, w, h], clamped to the frame. Raises if nothing is left."""
    x, y, w, h = (int(v) for v in rect)
    fh, fw = frame.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(fw, x + w), min(fh, y + h)
    if w <= 0 or h <= 0 or x1 <= x0 or y1 <= y0:
        raise ValueError(f"empty crop {rect} for frame {fw}x{fh}")
    return frame[y0:y1, x0:x1]


def to_screen(mon, x, y, region=None):
    """Point in a grabbed image -> absolute screen coordinates for clicking."""
    ox, oy = (region[0], region[1]) if region else (0, 0)
    return mon["left"] + ox + x, mon["top"] + oy + y
