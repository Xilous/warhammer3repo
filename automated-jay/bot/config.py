"""Fixed game configuration the bot assumes. Change the game, change this file.

Everything downstream (click coordinates, screenshot templates, memory anchors)
is only valid for the configuration written here.
"""
import json
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


_MISSING = object()


def merge_defaults(user, new, olds: list):
    """The player's value, the new release's default and the same value in earlier releases' defaults -> the value to
    keep. A value the player never changed (equal to an earlier default) follows the new default, a changed one is
    kept; keys new in the defaults are added, and a default the new release dropped goes too if it was never
    changed. Dicts are merged key by key, anything else (lists too) is one value."""
    if isinstance(user, dict) and isinstance(new, dict):
        out = {}
        for k, v in user.items():
            sub = [o.get(k, _MISSING) if isinstance(o, dict) else _MISSING for o in olds]
            if k in new:
                out[k] = merge_defaults(v, new[k], sub)
            elif not any(o is not _MISSING and o == v for o in sub):
                out[k] = v                     # the player's own key, or one the app wrote (anchors.json)
        for k, v in new.items():
            if k not in user and not any(isinstance(o, dict) and k in o for o in olds):
                out[k] = v                     # (a key earlier defaults had and the player's file lacks was removed)
        return out
    return new if any(o is not _MISSING and o == user for o in olds) else user


def _seed_user_files() -> None:
    """Exe only: put the bundled default strategy files and anchors next to the exe if they are not there yet, and
    bring files an earlier exe put there up to this release's defaults (merge_defaults: the player's changes and
    ticks are kept). Done once per release: runs/defaults_version.txt names the release the files were last brought
    up to; the earlier releases' defaults ship in BUNDLE/defaults_history/<release>/ (tools/build_exe.py). A file
    that changes is copied to runs/upgrade_backup/<release it came from>/ first."""
    src = BUNDLE / "defaults"
    if not src.is_dir():
        return
    RUNS_DIR.mkdir(exist_ok=True)
    marker = RUNS_DIR / "defaults_version.txt"
    tag = BUNDLE / "data" / "release.txt"
    release = tag.read_text(encoding="utf-8").strip() if tag.exists() else "dev"
    seen = marker.read_text(encoding="utf-8").strip() if marker.exists() else None
    if seen == release:
        return
    hist = BUNDLE / "defaults_history"
    bases = [hist / seen] if seen and (hist / seen).is_dir() else \
        sorted(p for p in hist.iterdir() if p.is_dir()) if hist.is_dir() else []
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(src)
        dst = ROOT / rel
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
            continue
        if f.suffix != ".json":
            continue
        try:
            user = json.loads(dst.read_text(encoding="utf-8"))
            olds = [json.loads((b / rel).read_text(encoding="utf-8")) for b in bases if (b / rel).exists()]
            out = merge_defaults(user, json.loads(f.read_text(encoding="utf-8")), olds)
        except (OSError, ValueError):
            continue                           # a file the player broke stays as it is
        if out != user:
            backup = RUNS_DIR / "upgrade_backup" / (seen or "before_" + release) / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, backup)
            dst.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    marker.write_text(release + "\n", encoding="utf-8")


if FROZEN:
    _seed_user_files()

# Offsets from the reverse-engineering notes (re/NOTES.md, 9.0 build).
# campaign_variables float[1068] lives at:
CV_OFFSET_MODEL = 0x5BE8      # campaign-model holder + this
CV_OFFSET_ENGINE = 0x18CD4    # autoresolver engine/db object + this
CV_COUNT = 1068
