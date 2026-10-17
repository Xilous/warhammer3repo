"""Build the distributable exe: dist/automated-jay.exe, one file, no console window.

    python -X utf8 -m tools.build_exe            (from automated-jay/, with the repo's game data in ../tww and ../re)

1. data      the game DB tables the code reads (every "*_tables" name in assist/ and bot/, plus the campaign
             variables), the English localisation trimmed to the name keys the code shows (plus every key those
             names refer to with {{tr:...}}), the tech beeline and the RE outputs -> build/exe/data, shipped inside
             the exe (player decision 2026-10-17: game-derived data goes in the exe, never in the repo).
2. defaults  strategy/*.json and anchors.json -> build/exe/defaults; the exe copies them next to itself on first
             start (bot/config.py), so the player's edits and ticks survive a new exe.
3. PyInstaller --onefile --windowed.
Check the result with `dist/automated-jay.exe --selftest` (writes dist/runs/selftest.txt).
"""
from __future__ import annotations
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]          # automated-jay/
REPO = HERE.parent
OUT = HERE / "build" / "exe"
EXTRA_TABLES = {"campaign_variables_tables"}        # read by bot/sensor/cvtable.py through a path, not a literal
LOC_PREFIXES = ("land_units_onscreen_name_", "provinces_onscreen_", "regions_onscreen_",
                "building_culture_variants_name_", "building_levels_onscreen_name_",
                "character_skills_localised_name_", "factions_screen_name_", "technologies_onscreen_name_",
                "names_name_", "agent_subtypes_onscreen_name_override_")
TR = re.compile(r"\{\{tr:([^}]+)\}\}")


def tables() -> set[str]:
    found = set(EXTRA_TABLES)
    for p in list((HERE / "assist").rglob("*.py")) + list((HERE / "bot").rglob("*.py")):
        found |= set(re.findall(r'"([a-z0-9_]+_tables)"', p.read_text(encoding="utf-8")))
    return found


def trimmed_loc() -> dict[str, str]:
    full = json.load(open(REPO / "tww" / "loc_en.json", encoding="utf-8"))
    keep = {k: v for k, v in full.items() if k.startswith(LOC_PREFIXES)}
    todo = [v for v in keep.values()]
    while todo:                                      # names that point at other entries: keep those too
        for ref in TR.findall(todo.pop() or ""):
            if ref in full and ref not in keep:
                keep[ref] = full[ref]
                todo.append(full[ref])
    return keep


def build_data() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    db = OUT / "data" / "db"
    db.mkdir(parents=True)
    for t in sorted(tables()):
        src = REPO / "tww" / "db" / f"{t}.json"
        if not src.exists():
            sys.exit(f"missing game table {src}: dump it with the repo's scripts/game/dumpdb.py first")
        shutil.copy2(src, db / src.name)
    loc = trimmed_loc()
    (OUT / "data" / "loc_en.json").write_text(json.dumps(loc, ensure_ascii=False), encoding="utf-8")
    shutil.copy2(REPO / "tww" / "skv_beeline.json", OUT / "data" / "skv_beeline.json")
    (OUT / "data" / "re").mkdir()
    shutil.copy2(REPO / "re" / "cv_globals.json", OUT / "data" / "re" / "cv_globals.json")
    (OUT / "defaults" / "strategy").mkdir(parents=True)
    for f in (HERE / "strategy").glob("*.json"):
        shutil.copy2(f, OUT / "defaults" / "strategy" / f.name)
    shutil.copy2(HERE / "anchors.json", OUT / "defaults" / "anchors.json")
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    print(f"data: {len(tables())} tables, {len(loc)} names, {size:.1f} MB -> {OUT}")


def pyinstaller() -> None:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
           "--name", "automated-jay", "--distpath", str(HERE / "dist"), "--workpath", str(HERE / "build" / "pyi"),
           "--specpath", str(HERE / "build"), "--paths", str(HERE),
           "--add-data", f"{OUT / 'data'};data", "--add-data", f"{OUT / 'defaults'};defaults",
           "--hidden-import", "pydirectinput", "--hidden-import", "pymem",
           "--exclude-module", "cv2", "--exclude-module", "matplotlib", "--exclude-module", "scipy",
           "--exclude-module", "pandas", "--exclude-module", "mss", "--exclude-module", "pefile",
           str(HERE / "automated_jay.py")]
    subprocess.run(cmd, check=True, cwd=HERE)
    exe = HERE / "dist" / "automated-jay.exe"
    print(f"built {exe} ({exe.stat().st_size / 1e6:.1f} MB)")


def main() -> int:
    build_data()
    pyinstaller()
    return 0


if __name__ == "__main__":
    sys.exit(main())
