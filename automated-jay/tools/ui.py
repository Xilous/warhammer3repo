"""Drive the game from the command line: screenshots, clicks, keys.

Screenshots never touch focus (window capture works while the game is behind other windows).
The game only accepts real input while it is the foreground window, so a chain that clicks or presses
keys raises the game for the duration of the chain and then ALWAYS puts the user's terminal back in
front (bot/focus.py), verified with retries, even if a command fails.

Every input primitive here first checks that the game is the foreground window and raises
bot.focus.InputAborted when it is not (the player alt-tabbed away): input never lands in another window.
Held keys and mouse buttons are always released in `finally`.

  python -X utf8 -m tools.ui shot OUT.png [--scale 0.6667]   # full screenshot (optionally downscaled)
  python -X utf8 -m tools.ui crop OUT.png x0 y0 x1 y1 [--zoom 2]
  python -X utf8 -m tools.ui click X Y [--right] [--double]   # full-resolution coordinates
  python -X utf8 -m tools.ui move X Y
  python -X utf8 -m tools.ui key NAME [--hold MOD]
  python -X utf8 -m tools.ui type TEXT                       # types text into the focused field
  python -X utf8 -m tools.ui wait SECONDS
Several commands can be chained with ' + ', e.g.  click 960 540 + wait 2 + shot a.png
"""
from __future__ import annotations
import contextlib
import functools
import sys
import time

import pydirectinput
import win32api
import win32con
import win32gui
from PIL import Image

from bot import config
from bot.focus import InputAborted, game_focus, require_game_front   # noqa: F401  (InputAborted re-exported)
from tools import timing

pydirectinput.PAUSE = 0.03


def _timed(kind: str):
    """Record the primitive into the active timing trace (tools/timing.py): kind, ms, where."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            if not timing.active():
                return fn(*a, **kw)
            t = time.perf_counter()
            k = "rclick" if kw.get("right") or (len(a) > 2 and a[2] is True and kind == "click") else kind
            with timing.quiet():
                try:
                    return fn(*a, **kw)
                finally:
                    timing.input_event(k, (time.perf_counter() - t) * 1000,
                                       at=[int(v) for v in a[:2]] if len(a) >= 2 and kind != "key" else a[:1])
        return wrapper
    return deco


@_timed("click")
def click_at(x: int, y: int, right: bool = False) -> None:
    """The game ignores pydirectinput/SendInput button events but accepts legacy mouse_event
    after a SetCursorPos (verified 2026-10-16). Raises InputAborted when the game is not in front."""
    down, up = ((win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP) if right
                else (win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP))
    require_game_front()
    win32api.SetCursorPos((x, y))
    time.sleep(0.2)
    require_game_front(at=(x, y))            # again right before the button: the player may have just left
    win32api.mouse_event(down, 0, 0, 0, 0)
    try:
        time.sleep(0.12)
    finally:
        win32api.mouse_event(up, 0, 0, 0, 0)
    time.sleep(0.1)


def move_to(x: int, y: int) -> None:
    """Move the cursor (hover, park). Raises InputAborted when the game is not in front."""
    require_game_front()
    win32api.SetCursorPos((int(x), int(y)))


@_timed("dclick")
def double_click(x: int, y: int) -> None:
    move_to(x, y)
    time.sleep(0.2)
    require_game_front(at=(x, y))
    for _ in range(2):
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        try:
            time.sleep(0.05)
        finally:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.07)


@_timed("drag")
def drag(x0: int, y0: int, x1: int, y1: int, steps: int = 25) -> None:
    """Left-drag from (x0, y0) to (x1, y1); the button is released even if the drag is interrupted."""
    move_to(x0, y0)
    time.sleep(0.2)
    require_game_front(at=(x0, y0))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    try:
        time.sleep(0.12)
        for i in range(1, steps + 1):
            win32api.SetCursorPos((x0 + (x1 - x0) * i // steps, y0 + (y1 - y0) * i // steps))
            time.sleep(0.015)
        time.sleep(0.12)
    finally:
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.5)


@_timed("wheel")
def wheel(x: int, y: int, notches: int, pause: float = 0.12) -> None:
    """Mouse wheel over (x, y): positive notches scroll up / left."""
    move_to(x, y)
    time.sleep(0.05)
    for _ in range(abs(notches)):
        require_game_front(at=(x, y))        # a wheel event goes to the window under the cursor
        win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, 120 if notches > 0 else -120, 0)
        time.sleep(pause)


@_timed("key")
def press(key: str) -> None:
    require_game_front()
    pydirectinput.press(key)


@contextlib.contextmanager
def held(key: str):
    """Hold a key for the duration of the block; it is released even if the block raises."""
    require_game_front()
    pydirectinput.keyDown(key)
    try:
        yield
    finally:
        pydirectinput.keyUp(key)


@_timed("hold")
def hold_key(key: str, seconds: float) -> None:
    with held(key):
        time.sleep(seconds)


def type_text(text: str) -> None:
    """Slow, held key presses: the game drops characters typed at normal automation speed,
    and ignores shifted capitals, so text should be lowercase."""
    for ch in text:
        hold_key("space" if ch == " " else ch, 0.04)
        time.sleep(0.09)


def grab() -> Image.Image:
    """Capture the game window itself (PrintWindow), so it works with the game in the background."""
    import ctypes
    import win32ui
    h = win32gui.FindWindow(None, config.WINDOW_TITLE)
    l, t, r, b = win32gui.GetClientRect(h)
    w, hh = r - l, b - t
    hdc = win32gui.GetWindowDC(h)
    mdc = win32ui.CreateDCFromHandle(hdc)
    sdc = mdc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mdc, w, hh)
    sdc.SelectObject(bmp)
    ctypes.windll.user32.PrintWindow(h, sdc.GetSafeHdc(), 0x2 | 0x1)   # full content, client area
    info = bmp.GetInfo()
    im = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1)
    win32gui.DeleteObject(bmp.GetHandle())
    sdc.DeleteDC()
    mdc.DeleteDC()
    win32gui.ReleaseDC(h, hdc)
    return im.copy()


def run(args: list[str]) -> None:
    cmd, rest = args[0], args[1:]
    opt = lambda name, default=None: rest[rest.index(name) + 1] if name in rest else default
    if cmd == "shot":
        im = grab()
        s = float(opt("--scale", 1))
        if s != 1:
            im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        im.save(rest[0])
    elif cmd == "crop":
        x0, y0, x1, y1 = (int(v) for v in rest[1:5])
        z = float(opt("--zoom", 1))
        im = grab().crop((x0, y0, x1, y1))
        if z != 1:
            im = im.resize((int(im.width * z), int(im.height * z)), Image.LANCZOS)
        im.save(rest[0])
    elif cmd == "click":
        x, y = int(rest[0]), int(rest[1])
        right = "--right" in rest
        for _ in range(2 if "--double" in rest else 1):
            click_at(x, y, right)
    elif cmd == "move":
        move_to(int(rest[0]), int(rest[1]))
    elif cmd == "key":
        mod = opt("--hold")
        with held(mod) if mod else contextlib.nullcontext():
            time.sleep(0.05 if mod else 0)
            press(rest[0])
            time.sleep(0.05 if mod else 0)
    elif cmd == "type":
        type_text(" ".join(rest))
    elif cmd == "wait":
        time.sleep(float(rest[0]))
    else:
        sys.exit(f"unknown command {cmd}")


INPUT_CMDS = {"click", "move", "key", "type"}


def main() -> int:
    chunks, cur = [], []
    for a in sys.argv[1:]:
        if a == "+":
            chunks.append(cur)
            cur = []
        else:
            cur.append(a)
    if cur:
        chunks.append(cur)
    if any(c[0] in INPUT_CMDS for c in chunks):
        with game_focus():
            for c in chunks:
                run(c)
    else:
        for c in chunks:
            run(c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
