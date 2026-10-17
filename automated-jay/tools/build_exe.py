"""Build the distributable exe: dist/automated-jay.exe, one file, no console window.

    python -X utf8 -m tools.build_exe [--release automated-jay-vX.Y.Z]
                                                 (from automated-jay/, with the repo's game data in ../tww and ../re)

1. data      the game DB tables the code reads (every "*_tables" name in assist/ and bot/, plus the campaign
             variables), the English localisation trimmed to the name keys the code shows (plus every key those
             names refer to with {{tr:...}}), the tech beeline and the RE outputs -> build/exe/data, shipped inside
             the exe (player decision 2026-10-17: game-derived data goes in the exe, never in the repo).
2. defaults  strategy/*.json and anchors.json -> build/exe/defaults; the exe copies them next to itself on first
             start (bot/config.py), so the player's edits and ticks survive a new exe. Shipped without army ticks
             (the repo's automation.json holds the ticks of the campaign played from the repo: cqi 55 is Ikit's own
             army in any Ikit campaign). The defaults each earlier release (git tags automated-jay-v*) shipped go to
             build/exe/defaults_history/<tag>: a new exe brings an earlier one's files up to its defaults, keeping
             what the player changed. The release name goes to data/release.txt.
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
TAGS = "automated-jay-v*"


def shipped(rel: str, text: str, blank_ticks: bool = True) -> str:
    """A default file as the exe ships it: automation.json without army ticks."""
    if not (blank_ticks and rel.endswith("automation.json")):
        return text
    d = json.loads(text)
    d["army_builder"]["enabled_armies"] = []
    return json.dumps(d, indent=2, ensure_ascii=False) + "\n"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True, text=True,
                          encoding="utf-8").stdout


def defaults_history(release: str) -> list[str]:
    """Each earlier release's default files, as that release's build shipped them -> build/exe/defaults_history."""
    tags = [t for t in git("tag", "-l", TAGS).split() if t != release]
    for tag in tags:
        blanked = "enabled_armies" in git("show", f"{tag}:automated-jay/tools/build_exe.py")
        files = git("ls-tree", "-r", "--name-only", tag, "automated-jay/strategy/").split()
        for path in files + ["automated-jay/anchors.json"]:
            rel = path[len("automated-jay/"):]
            if not rel.endswith(".json"):
                continue
            dst = OUT / "defaults_history" / tag / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(shipped(rel, git("show", f"{tag}:{path}"), blanked), encoding="utf-8")
    return tags


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


def build_data(release: str) -> None:
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
    (OUT / "data" / "release.txt").write_text(release + "\n", encoding="utf-8")
    (OUT / "defaults" / "strategy").mkdir(parents=True)
    for f in list((HERE / "strategy").glob("*.json")) + [HERE / "anchors.json"]:
        rel = f.relative_to(HERE).as_posix()
        (OUT / "defaults" / rel).write_text(shipped(rel, f.read_text(encoding="utf-8")), encoding="utf-8")
    tags = defaults_history(release)
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    print(f"data: {len(tables())} tables, {len(loc)} names, {size:.1f} MB, release {release}, "
          f"defaults of {len(tags)} earlier releases -> {OUT}")


def pyinstaller() -> None:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
           "--name", "automated-jay", "--distpath", str(HERE / "dist"), "--workpath", str(HERE / "build" / "pyi"),
           "--specpath", str(HERE / "build"), "--paths", str(HERE),
           "--add-data", f"{OUT / 'data'};data", "--add-data", f"{OUT / 'defaults'};defaults",
           "--add-data", f"{OUT / 'defaults_history'};defaults_history",
           "--hidden-import", "pydirectinput", "--hidden-import", "pymem",
           "--exclude-module", "cv2", "--exclude-module", "matplotlib", "--exclude-module", "scipy",
           "--exclude-module", "pandas", "--exclude-module", "mss", "--exclude-module", "pefile",
           str(HERE / "automated_jay.py")]
    subprocess.run(cmd, check=True, cwd=HERE)
    exe = HERE / "dist" / "automated-jay.exe"
    print(f"built {exe} ({exe.stat().st_size / 1e6:.1f} MB)")


def main() -> int:
    args = sys.argv[1:]
    build_data(args[args.index("--release") + 1] if "--release" in args else "dev")
    pyinstaller()
    return 0


if __name__ == "__main__":
    sys.exit(main())
