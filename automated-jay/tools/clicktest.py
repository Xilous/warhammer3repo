"""Try several ways of delivering a left click to the focused game; report which one changes the screen.

  python -X utf8 -m tools.clicktest X Y OUTDIR
"""
from __future__ import annotations
import ctypes
import ctypes.wintypes as wt
import sys
import time

import win32api
import win32con
import win32gui
from PIL import ImageChops

from bot.focus import game_focus
from tools.ui import grab

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def send_mouse(flags: int, x: int = 0, y: int = 0) -> None:
    inp = INPUT(type=0)
    inp.mi = MOUSEINPUT(x, y, 0, flags, 0, 0)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def abs_xy(x: int, y: int) -> tuple[int, int]:
    W, H = win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)
    return int(x * 65535 / (W - 1)), int(y * 65535 / (H - 1))


def method_mouse_event(x, y, h):
    win32api.SetCursorPos((x, y)); time.sleep(0.2)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0); time.sleep(0.12)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def method_sendinput_abs(x, y, h):
    ax, ay = abs_xy(x, y)
    M, A = 0x0001, 0x8000
    send_mouse(M | A, ax, ay); time.sleep(0.2)
    send_mouse(M | A | 0x0002, ax, ay); time.sleep(0.12)
    send_mouse(M | A | 0x0004, ax, ay)


def method_postmessage_focused(x, y, h):
    win32api.SetCursorPos((x, y)); time.sleep(0.2)
    cx, cy = win32gui.ScreenToClient(h, (x, y))
    lp = win32api.MAKELONG(cx, cy)
    win32api.PostMessage(h, win32con.WM_MOUSEMOVE, 0, lp); time.sleep(0.05)
    win32api.PostMessage(h, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp); time.sleep(0.12)
    win32api.PostMessage(h, win32con.WM_LBUTTONUP, 0, lp)


METHODS = [("mouse_event", method_mouse_event), ("sendinput_abs", method_sendinput_abs),
           ("postmessage_focused", method_postmessage_focused)]


def main() -> int:
    x, y, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    with game_focus() as h:
        for name, fn in METHODS:
            before = grab()
            fn(x, y, h)
            time.sleep(1.2)
            after = grab()
            d = ImageChops.difference(before, after).convert("L")
            changed = sum(1 for p in d.getdata() if p > 40)
            after.resize((1280, 720)).save(f"{out}/click_{name}.png")
            print(f"{name:22s} changed_pixels={changed}")
            if changed > 20000:
                print("  -> this method works")
                break
            # move off the button so hover doesn't count as change next time
            win32api.SetCursorPos((960, 1000)); time.sleep(0.4)
    return 0


if __name__ == "__main__":
    sys.exit(main())
