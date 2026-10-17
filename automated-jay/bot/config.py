"""Fixed game configuration the bot assumes. Change the game, change this file.

Everything downstream (click coordinates, screenshot templates, memory anchors)
is only valid for the configuration written here.
"""
import shutil
import sys
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

# Locations. From the repo: everything relative to automated-jay/ and its parent repo (game data in ../tww, RE
# outputs in ../re). As the distributable exe (tools/build_exe.py, PyInstaller): the game data ships inside the exe
# (BUNDLE/data, read-only) and the player's own files (strategy/*.json, anchors.json, runs/) live next to the exe,
# created from the bundled defaults on first start, so ticks and edits survive updates of the exe.
FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    ROOT = Path(sys.executable).resolve().parent
    BUNDLE = Path(getattr(sys, "_MEIPASS", ROOT))
    REPO = ROOT
    RE_DIR = BUNDLE / "data" / "re"
    DB_DIR = BUNDLE / "data" / "db"
    LOC_FILE = BUNDLE / "data" / "loc_en.json"
    BEELINE_FILE = BUNDLE / "data" / "skv_beeline.json"
else:
    ROOT = Path(__file__).resolve().parent.parent
    BUNDLE = ROOT
    REPO = ROOT.parent
    RE_DIR = REPO / "re"                     # reverse-engineering outputs
    DB_DIR = REPO / "tww" / "db"             # dumped game DB tables
    LOC_FILE = REPO / "tww" / "loc_en.json"
    BEELINE_FILE = REPO / "tww" / "skv_beeline.json"
STRATEGY_DIR = ROOT / "strategy"         # the player's decisions (automation, settlements, skills, popup ignore list)
ANCHORS_FILE = ROOT / "anchors.json"     # written by tools/probe.py
RUNS_DIR = ROOT / "runs"                 # per-run jsonl logs


def _seed_user_files() -> None:
    """Exe only: put the bundled default strategy files and anchors next to the exe if they are not there yet."""
    src = BUNDLE / "defaults"
    if not src.is_dir():
        return
    for f in src.rglob("*"):
        dst = ROOT / f.relative_to(src)
        if f.is_file() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
    RUNS_DIR.mkdir(exist_ok=True)


if FROZEN:
    _seed_user_files()

# Offsets from the reverse-engineering notes (re/NOTES.md, 9.0 build).
# campaign_variables float[1068] lives at:
CV_OFFSET_MODEL = 0x5BE8      # campaign-model holder + this
CV_OFFSET_ENGINE = 0x18CD4    # autoresolver engine/db object + this
CV_COUNT = 1068
