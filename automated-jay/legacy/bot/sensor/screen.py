"""Screenshot sensor: fallback and unknown-screen detector.

Deliberately minimal for the PoC: grabs the game window and exposes a hash so the
loop can tell "screen changed" from "screen stuck". OCR and template matching come later.
"""
from __future__ import annotations
import hashlib

import mss
import win32gui

from .. import config
from ..schema import State


class ScreenSensor:
    name = "screen"

    def __init__(self) -> None:
        self.hwnd = win32gui.FindWindow(None, config.WINDOW_TITLE)

    def grab(self):
        with mss.mss() as sct:
            if self.hwnd:
                l, t, r, b = win32gui.GetWindowRect(self.hwnd)
                mon = {"left": l, "top": t, "width": r - l, "height": b - t}
            else:
                mon = sct.monitors[1]
            return sct.grab(mon)

    def fingerprint(self) -> str:
        img = self.grab()
        small = bytes(img.raw[::97])   # cheap subsample
        return hashlib.blake2b(small, digest_size=8).hexdigest()

    def read(self) -> State:
        s = State(source=self.name)
        s.extras["fingerprint"] = self.fingerprint()
        return s
