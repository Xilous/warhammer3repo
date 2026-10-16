"""Hands: ordinary OS-level keyboard and mouse input, nothing injected into the game.

Safety rule: refuse to act unless the game window is in the foreground. The bot must
never type into whatever else happens to be focused.
"""
from __future__ import annotations
import time

import pydirectinput
import win32gui

from .. import config

pydirectinput.PAUSE = 0.05
pydirectinput.FAILSAFE = True   # slam the mouse into a screen corner to abort


class GameNotFocused(RuntimeError):
    pass


class Hands:
    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.hwnd = win32gui.FindWindow(None, config.WINDOW_TITLE)

    def focused(self) -> bool:
        return bool(self.hwnd) and win32gui.GetForegroundWindow() == self.hwnd

    def focus(self) -> None:
        if self.hwnd and not self.focused():
            win32gui.SetForegroundWindow(self.hwnd)
            time.sleep(0.3)

    def _guard(self, what: str) -> bool:
        if self.dry_run:
            print(f"[dry-run] {what}")
            return False
        if not self.focused():
            raise GameNotFocused(what)
        return True

    def key(self, name: str) -> None:
        if self._guard(f"key {name}"):
            pydirectinput.press(name)

    def click(self, x: int, y: int) -> None:
        # pydirectinput button events are ignored by the game; legacy mouse_event works.
        if self._guard(f"click {x},{y}"):
            from tools.ui import click_at
            click_at(x, y)

    def chord(self, mod: str, name: str) -> None:
        if self._guard(f"key {mod}+{name}"):
            pydirectinput.keyDown(mod)
            try:
                time.sleep(0.05)
                pydirectinput.press(name)
                time.sleep(0.05)
            finally:
                pydirectinput.keyUp(mod)

    def end_turn(self) -> None:
        if config.END_TURN_SKIP_WARNINGS:
            self.chord("shift", config.END_TURN_KEY)
        else:
            self.key(config.END_TURN_KEY)
