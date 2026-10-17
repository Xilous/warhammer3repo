"""Static game data the assistant needs, read from the repo's DB dump (../tww/db, ../tww/loc_en.json).

Regenerate the dump after a game patch with the parent repo's scripts (see the repo README);
tables this module needs beyond the default set are dumped with
  python -X utf8 scripts/game/dumpdb.py <table> ...
from the repo root.
"""
from __future__ import annotations
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from bot import config

REPO = config.REPO
DB = config.DB_DIR
LOC = config.LOC_FILE

SKAVEN_AVAILABILITY = ("wh2_main_bas_skv", "everyone")


def _load(table: str) -> list[dict]:
    return json.load(open(DB / f"{table}.json", encoding="utf-8"))


@dataclass(frozen=True)
class Level:
    chain: str
    index: int          # position in the chain (0-based, as in building_levels.level)
    key: str            # building level key
    tier: int           # main-building tier required (primary_slot_building_building_level_requirement)
    cost: int
    turns: int


@lru_cache(maxsize=1)
def loc() -> dict[str, str]:
    return json.load(open(LOC, encoding="utf-8"))


def place_name(key: str) -> str:
    """In-game name of a region or province key (the key itself when the game has none)."""
    L = loc()
    return L.get("regions_onscreen_" + key) or L.get("provinces_onscreen_" + key) or key


def _tr(text: str) -> str:
    for _ in range(3):
        m = re.search(r"\{\{tr:([^}]+)\}\}", text or "")
        if not m:
            break
        text = text.replace(m.group(0), loc().get(m.group(1), ""))
    return text


@lru_cache(maxsize=None)
def level_name(level_key: str) -> str:
    L = loc()
    for k in ("building_culture_variants_name_" + level_key, "building_levels_onscreen_name_" + level_key):
        if k in L:
            return _tr(L[k])
    # Culture variants are keyed level + culture + subculture [+ faction]; prefer Clan Skryre, then any Skaven variant.
    prefix = "building_culture_variants_name_" + level_key + "wh"
    best, rank = None, -1
    for k, v in L.items():
        if not k.startswith(prefix):
            continue
        r = 2 if k.endswith("wh2_main_skv_clan_skryre") else 1 if "wh2_main_skv_skaven" in k else 0
        if r > rank:
            best, rank = v, r
    return _tr(best) if best is not None else level_key


@lru_cache(maxsize=1)
def chains() -> dict[str, list[Level]]:
    out: dict[str, list[Level]] = defaultdict(list)
    for r in _load("building_levels_tables"):
        out[r["chain"]].append(Level(
            chain=r["chain"], index=int(r["level"]), key=r["level_name"],
            tier=int(r["primary_slot_building_building_level_requirement"] or 0),
            cost=int(float(r["create_cost"] or 0)), turns=int(float(r["create_time"] or 0)),
        ))
    for v in out.values():
        v.sort(key=lambda l: l.index)
    return dict(out)


def main_tier(chain: str, index: int) -> int:
    """Main-building chains count tiers by level index (0 = ruin, 1..5 = tier)."""
    return index


def main_max_index(chain: str) -> int:
    return chains()[chain][-1].index


@lru_cache(maxsize=1)
def slot_counts() -> dict[str, dict[int, int]]:
    """Building slots unlocked by each main-building level (excluding the main slot itself),
    from the 'construction_slot(_multiple)_dummy' effect the game shows in the tooltip."""
    out: dict[str, dict[int, int]] = defaultdict(dict)
    lv = {l.key: l for ls in chains().values() for l in ls}
    for r in _load("building_effects_junction_tables"):
        if r["effect"] in ("wh_main_effect_construction_slot_dummy", "wh_main_effect_construction_slot_multiple_dummy"):
            l = lv.get(r["building"])
            if l:
                out[l.chain][l.index] = int(float(r["value"]))
    return dict(out)


def slots_at(main_chain: str, index: int) -> int:
    table = slot_counts().get(main_chain, {})
    best = 0
    for i, n in table.items():
        if i <= index:
            best = max(best, n)
    return best


@lru_cache(maxsize=1)
def skaven_chains() -> frozenset[str]:
    return frozenset(r["building_chain"] for r in _load("building_chain_availability_sets_tables")
                     if r["id"] in SKAVEN_AVAILABILITY)


@lru_cache(maxsize=1)
def landmark_sets() -> dict[str, list[str]]:
    """landmark place name -> landmark chains Skaven can build there."""
    bc = {r["key"]: r for r in _load("building_chains_tables")}
    out: dict[str, list[str]] = defaultdict(list)
    for r in _load("building_chain_set_items_tables"):
        s = r["set"]
        if not s.startswith("wh3_main_secondary_addon_landmark_") or r["remove"]:
            continue
        place = s[len("wh3_main_secondary_addon_landmark_"):]
        found = [r["chain"]] if r["chain"] else [k for k, c in bc.items() if c["building_superchain"] == r["super_chain"]]
        for c in found:
            if c in skaven_chains() and c in chains() and c not in out[place]:
                out[place].append(c)
    return dict(out)


def landmarks_for_region(region_key: str) -> list[str]:
    """Best-effort: landmark sets are named after the place, region keys end with the place name."""
    place = region_key.split("_region_", 1)[-1]
    return list(landmark_sets().get(place, []))
