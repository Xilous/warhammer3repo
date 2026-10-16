"""Fixed game configuration the bot assumes. Change the game, change this file.

Everything downstream (click coordinates, screenshot templates, memory anchors)
is only valid for the configuration written here.
"""
from pathlib import Path

PROCESS_NAME = "Warhammer3.exe"
WINDOW_TITLE = "Total War: WARHAMMER 3"     # exact title of the 9.0 game window (class "Warhammer3")

# Game must run borderless windowed at this resolution with this UI scale.
RESOLUTION = (1920, 1080)      # primary monitor as of 2026-10-16
UI_SCALE = 1.0

# End Turn hotkeys (WH3 defaults). Plain Enter stops at warnings such as
# "Lord not moved" and pans to them; Shift+Enter ends the turn and skips warnings.
END_TURN_KEY = "enter"
END_TURN_SKIP_WARNINGS = True

# Repo-relative locations.
ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
ANCHORS_FILE = ROOT / "anchors.json"     # written by tools/probe.py
RUNS_DIR = ROOT / "runs"                 # per-run jsonl logs
RE_DIR = REPO / "re"                     # reverse-engineering outputs
DB_DIR = REPO / "tww" / "db"             # dumped game DB tables

# Offsets from the reverse-engineering notes (re/NOTES.md, 9.0 build).
# campaign_variables float[1068] lives at:
CV_OFFSET_MODEL = 0x5BE8      # campaign-model holder + this
CV_OFFSET_ENGINE = 0x18CD4    # autoresolver engine/db object + this
CV_COUNT = 1068
