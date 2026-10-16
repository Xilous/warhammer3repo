"""Extract building chain icons from the game's ui.pack into assist/templates/buildings/<icon>.png.

  python -X utf8 -m tools.extract_icons

Which icons: every building level Skaven can build (availability sets) plus landmark chains, as named
in building_culture_variants (one icon per chain in practice).
"""
from __future__ import annotations
import io
import json
import os
import sys
from pathlib import Path

import zstandard
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "game"))
import packread as P  # noqa: E402

from assist import gamedata as gd  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "assist" / "templates" / "buildings"


def get(path: str, e) -> bytes:
    name, off, size, comp = e
    with open(path, "rb") as f:
        f.seek(off)
        d = f.read(size)
    if comp:
        zd = zstandard.ZstdDecompressor()
        for s in (4, 0):
            try:
                return zd.decompress(d[s:], max_output_size=50_000_000)
            except Exception:
                pass
        raise RuntimeError(f"cannot decompress {name}")
    return d


def wanted_icons() -> dict[str, list[str]]:
    variants = json.load(open(gd.DB / "building_culture_variants_tables.json", encoding="utf-8"))
    skv = gd.skaven_chains()
    chains = gd.chains()
    lvl_chain = {l.key: c for c, ls in chains.items() for l in ls}
    icons: dict[str, list[str]] = {}
    for r in variants:
        c = lvl_chain.get(r["building"])
        if c is None or c not in skv:
            continue
        if r["culture"] not in ("", "wh2_main_skv_skaven") or r["faction"] not in ("", "wh2_main_skv_clan_skryre"):
            continue
        icons.setdefault(r["icon"], [])
        if c not in icons[r["icon"]]:
            icons[r["icon"]].append(c)
    return icons


def level_icons() -> dict[str, str]:
    """building level key -> icon, preferring the Clan Skryre variant, then Skaven, then generic."""
    variants = json.load(open(gd.DB / "building_culture_variants_tables.json", encoding="utf-8"))
    best: dict[str, tuple[int, str]] = {}
    for r in variants:
        rank = 3 if r["faction"] == "wh2_main_skv_clan_skryre" else 2 if r["culture"] == "wh2_main_skv_skaven" else             1 if not r["culture"] and not r["faction"] else 0
        if rank and rank > best.get(r["building"], (0, ""))[0]:
            best[r["building"]] = (rank, r["icon"])
    return {k: v for k, (_, v) in best.items()}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    icons = wanted_icons()
    path = os.path.join(P.GAME, "ui.pack")
    h, idx = P.read_index(path)
    by = {e[0].lower().replace("\\", "/"): e for e in idx}
    got = 0
    for icon in icons:
        e = by.get(f"ui/buildings/icons/{icon.lower()}.png")
        if e is None:
            continue
        Image.open(io.BytesIO(get(path, e))).convert("RGBA").save(OUT / f"{icon}.png")
        got += 1
    json.dump(icons, open(OUT / "_icon_to_chains.json", "w"), indent=1)
    json.dump(level_icons(), open(OUT / "_level_to_icon.json", "w"), indent=1)
    print(f"{got}/{len(icons)} icons extracted to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
