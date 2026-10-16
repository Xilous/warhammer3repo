"""Hover the mouse over screen points and save what the game shows (tooltips). Clicks nothing.

  python -X utf8 -m tools.hover OUTDIR name=x,y [name=x,y ...]

Raises the game, hovers each point, saves OUTDIR/tip_<name>.png (a box around the point),
then returns focus to the terminal.
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

import win32api

from bot import config
from bot.focus import game_focus
from tools.ui import grab


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    args = sys.argv[2:]
    W, H = config.RESOLUTION
    with game_focus():
        for a in args:
            name, xy = a.split("=")
            x, y = (int(v) for v in xy.split(","))
            win32api.SetCursorPos((x, y))
            time.sleep(1.4)
            im = grab()
            im.crop((max(0, x - 700), max(0, y - 320), min(W, x + 260), min(H, y + 320))).save(out / f"tip_{name}.png")
        win32api.SetCursorPos((W // 2, H // 2 + 100))
    print("saved", len(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
