"""Status colours shared by the assistant window and its overlay (assist/app.py): state -> (background, text).

The old stand-alone always-on-top Widget class that used to live here was replaced by assist/app.py; it is kept
in legacy/assist/widget.py.
"""
from __future__ import annotations

COLORS = {
    "waiting": ("#2b2b2b", "#bdbdbd"),
    "automating": ("#5a3d00", "#ffd27a"),
    "your turn": ("#123d1a", "#8dff9c"),
    "paused": ("#3a1f1f", "#ffb0b0"),
    "error": ("#4a0000", "#ff7070"),
}
