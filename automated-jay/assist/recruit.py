"""Where can each template unit or hero be recruited right now? Game data + live memory.

Game data (9.0.4):
  - units are gated by buildings only (building_units_allowed). No table locks these units behind a
    technology, so the tech automation does not gate recruitment.
      Stormvermin (Swords & Shields)  <- Clan Armoury (wh2_main_skv_clanrats_3)
      Stormfiends (Ratling Cannons)   <- Equipment Warpforge (wh3_dlc29_skv_stormfiends_2)
  - Warlock Engineers: hero recruitment is enabled province-wide by the Construction Cavern chain
    (wh2_main_skv_engineers_1..3) or Galbaraz's oathgold landmark (agent_enable_recruitment_engineer_skv).
  - recruitment draws on buildings anywhere in the province the army stands in.
Live state: every owned region's finished buildings (memory, bot/sensor/world.py). A building still
under construction does not count.

    python -X utf8 -m assist.recruit
"""
from __future__ import annotations

from bot import config
import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from . import gamedata as gd
from bot.sensor.world import World, current_faction, find_player_faction, region_provinces

HERO_ENABLE_EFFECT = {"wh2_main_skv_warlock_engineer": "wh2_main_effect_agent_enable_recruitment_engineer_skv"}


def unit_buildings() -> dict[str, set[str]]:
    """unit -> the building levels that recruit it, for the player's faction."""
    return _unit_buildings(current_faction())


@lru_cache(maxsize=4)
def _unit_buildings(faction: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for r in gd._load("building_units_allowed_tables"):
        if r.get("faction") not in ("", faction, None):   # the dump's "enabled" column is False on valid rows
            continue
        out[r["unit"]].add(r["building"])
    return dict(out)


@lru_cache(maxsize=1)
def hero_buildings() -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for r in gd._load("building_effects_junction_tables"):
        for hero, eff in HERO_ENABLE_EFFECT.items():
            if r["effect"] == eff:
                out[hero].add(r["building"])
    return dict(out)


def building_name(level_key: str) -> str:
    return gd.level_name(level_key)


def live_buildings(w: World, F: int) -> dict[str, dict[str, list[str]]]:
    """province -> region -> finished building level keys."""
    prov, _ = region_provinces()
    out: dict[str, dict[str, list[str]]] = defaultdict(dict)
    for r in w.faction_regions(F):
        key = w.region_key(r)
        if not key:
            continue
        out[prov.get(key, key)][key] = [s.building for s in w.slots(r) if s.building and s.active]
    return dict(out)


def sources(w: World | None = None) -> dict[str, list[tuple[str, str, str]]]:
    """template unit/hero key -> [(province, region, building level)] where it can be recruited now."""
    w = w or World()
    F = find_player_faction(w)
    t = json.load(open(config.STRATEGY_DIR / "automation.json", encoding="utf-8"))["army_builder"]["template"]
    need = {**{u: unit_buildings().get(u, set()) for u in t["units"]},
            **{h: hero_buildings().get(h, set()) for h in t["heroes"]}}
    live = live_buildings(w, F)
    out: dict[str, list[tuple[str, str, str]]] = {k: [] for k in need}
    for p, regions in live.items():
        for reg, blds in regions.items():
            for b in blds:
                for k, allowed in need.items():
                    if b in allowed:
                        out[k].append((p, reg, b))
    return out


def report(src: dict) -> list[str]:
    from .army import unit_name
    lines = []
    for k, where in src.items():
        nm = unit_name(k) if "_cha_" not in k and "warlock_engineer" not in k else "Warlock Engineer"
        if where:
            provs = sorted({gd.loc().get("provinces_onscreen_" + p, p) for p, _, _ in where})
            lines.append(f"{nm}: {', '.join(provs)}")
        else:
            blds = unit_buildings().get(k) or hero_buildings().get(k) or set()
            lines.append(f"{nm}: nowhere yet (needs {' or '.join(sorted(building_name(b) for b in blds))})")
    return lines


if __name__ == "__main__":
    print("\n".join(report(sources())))
