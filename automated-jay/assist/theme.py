"""Clan Brass, the widget's look (player's pick, 2026-10-18: option B of
https://claude.ai/artifact/1PeaRJy6ajNvXvKhon2Nm9): dark iron, brass accents, condensed caps, tabular numbers.
Shared by the rail (assist/rail.py) and its fold-out panel (assist/railpanel.py).
"""
from __future__ import annotations

BASE = "#0c0a08"          # behind everything (the panel's frame)
PANEL = "#17130e"         # the rail and the panel
PANEL2 = "#1f1a13"        # inset boxes (the log, hover)
LINE = "#3a3024"          # separators, empty segments, disabled borders
BRASS = "#c9973f"         # the accent: headings, done steps, the main button
BRASS_HI = "#d9b46a"      # hover on brass
TITLE = "#f1e3c4"         # big titles
INK = "#eadfcd"           # body text
TEXT2 = "#d8cbb2"         # secondary body text
MUTED = "#a8936f"         # labels, small caps
DIM = "#6f6250"           # disabled
GOOD = "#b8d98a"          # affordable, met, positive numbers
BAD = "#c2553f"           # the shortfall in the affordability bar
WARN = "#f0b49f"          # not affordable, not met
AMBER = "#ffce54"         # a step running now
RED = "#ff8b80"           # a step failed, errors
ON_BRASS = "#1a1209"      # text on a brass button

# rail stripe colour by state
STATE = {"waiting": LINE, "automating": AMBER, "your turn": BRASS, "paused": "#e0894a", "error": RED}

HEAD = ("Bahnschrift SemiBold Condensed", "Bahnschrift", "Segoe UI Semibold")   # Oswald in the mockup
BODY = ("Segoe UI",)                                                              # Source Sans 3 in the mockup
MONO = ("Consolas",)                                                              # IBM Plex Mono in the mockup


def font(families, size, weight="normal"):
    import tkinter.font as tkfont
    have = set(tkfont.families())
    fam = next((f for f in families if f in have), "Segoe UI")
    return (fam, size, weight)


def money(n: int | None, sign: bool = False) -> str:
    if n is None:
        return "—"
    s = f"{abs(n):,}"
    if sign:
        return ("+" if n >= 0 else "−") + s
    return ("−" if n < 0 else "") + s
