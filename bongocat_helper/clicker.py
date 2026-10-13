"""Real mouse clicks (SetCursorPos + SendInput) and the F12 emergency stop key."""
import ctypes
import random
import time
from ctypes import wintypes

INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
VK_F12 = 0x7B


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]   # largest member of the real union on x64

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _send(flags):
    inp = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, flags, 0, None))
    if ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
        raise OSError("SendInput failed (game running as admin? then run this as admin too)")


class Clicker:
    """click(x, y) at absolute screen coords, then put the cursor back where it was."""

    def click(self, x, y):
        user32 = ctypes.windll.user32
        old, now = wintypes.POINT(), wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(old)):
            raise OSError("GetCursorPos failed")
        # a failed move would click wherever the cursor happens to be: never send the click then
        if not user32.SetCursorPos(int(x), int(y)) or not user32.GetCursorPos(ctypes.byref(now)) \
                or (now.x, now.y) != (int(x), int(y)):
            raise OSError(f"cursor could not be moved to ({x}, {y}); click not sent")
        time.sleep(0.02)
        _send(MOUSEEVENTF_LEFTDOWN)
        time.sleep(random.uniform(0.03, 0.06))
        _send(MOUSEEVENTF_LEFTUP)
        time.sleep(0.03)
        user32.SetCursorPos(old.x, old.y)


def stop_pressed():
    """True while F12 is held (checked every loop)."""
    return bool(ctypes.windll.user32.GetAsyncKeyState(VK_F12) & 0x8000)
