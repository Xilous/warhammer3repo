"""Experiments: see and drive the game while it is NOT the foreground window.

  python -X utf8 -m tools.bg shot OUT.png            # PrintWindow(PW_RENDERFULLCONTENT) capture of the game window
  python -X utf8 -m tools.bg key esc                 # PostMessage WM_KEYDOWN/UP to the game window
  python -X utf8 -m tools.bg click X Y               # PostMessage mouse move + left click at client coords
  python -X utf8 -m tools.bg fg                      # report which window is in the foreground
Never changes focus.
"""
from __future__ import annotations
import ctypes
import sys
import time

import win32api
import win32con
import win32gui
import win32ui
from PIL import Image

from bot import config

PW_RENDERFULLCONTENT = 0x2
VK = {"esc": win32con.VK_ESCAPE, "enter": win32con.VK_RETURN, "space": win32con.VK_SPACE,
      "shift": win32con.VK_SHIFT, "tab": win32con.VK_TAB}


def hwnd() -> int:
    h = win32gui.FindWindow(None, config.WINDOW_TITLE)
    if not h:
        sys.exit("game window not found")
    return h


def shot(path: str) -> None:
    h = hwnd()
    l, t, r, b = win32gui.GetClientRect(h)
    w, hh = r - l, b - t
    hdc = win32gui.GetWindowDC(h)
    mdc = win32ui.CreateDCFromHandle(hdc)
    sdc = mdc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mdc, w, hh)
    sdc.SelectObject(bmp)
    ok = ctypes.windll.user32.PrintWindow(h, sdc.GetSafeHdc(), PW_RENDERFULLCONTENT | 1)  # 1 = client only
    info = bmp.GetInfo()
    data = bmp.GetBitmapBits(True)
    im = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), data, "raw", "BGRX", 0, 1)
    win32gui.DeleteObject(bmp.GetHandle())
    sdc.DeleteDC()
    mdc.DeleteDC()
    win32gui.ReleaseDC(h, hdc)
    if len(sys.argv) > 3 and sys.argv[3] == "--small":
        im = im.resize((im.width * 2 // 3, im.height * 2 // 3))
    im.save(path)
    ext = im.getextrema()
    print(f"PrintWindow ok={ok} size={im.size} extrema={ext}")


def key(name: str) -> None:
    h = hwnd()
    vk = VK.get(name) or ord(name.upper())
    scan = win32api.MapVirtualKey(vk, 0)
    win32api.PostMessage(h, win32con.WM_KEYDOWN, vk, 1 | (scan << 16))
    time.sleep(0.05)
    win32api.PostMessage(h, win32con.WM_KEYUP, vk, 1 | (scan << 16) | (0xC0 << 24))


def click(x: int, y: int) -> None:
    h = hwnd()
    lp = win32api.MAKELONG(x, y)
    win32api.PostMessage(h, win32con.WM_MOUSEMOVE, 0, lp)
    time.sleep(0.05)
    win32api.PostMessage(h, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
    time.sleep(0.05)
    win32api.PostMessage(h, win32con.WM_LBUTTONUP, 0, lp)


def main() -> int:
    cmd = sys.argv[1]
    if cmd == "shot":
        shot(sys.argv[2])
    elif cmd == "key":
        key(sys.argv[2])
    elif cmd == "click":
        click(int(sys.argv[2]), int(sys.argv[3]))
    elif cmd == "fg":
        f = win32gui.GetForegroundWindow()
        print("foreground:", f, repr(win32gui.GetWindowText(f)), "game:", hwnd())
    return 0


if __name__ == "__main__":
    sys.exit(main())
