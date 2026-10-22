"""How fast a building pays for itself, for the spending order (player decision 2026-10-21): every building still
reaches its highest tier; among the buildings that are not critical, the gold goes first to the one that pays for
itself soonest (cost / the gold per turn it adds). Nothing is ever refused for paying back slowly (a 20-turn
break-even filter was simulated and removed the same day: it stalled upgrades worth 25% of a province's income).

From the game data (building_effects_junction_tables):
  income      every building's base income: effects wh_main_effect_economy_gdp_<category>, scope building_to_building_own
  bonuses     wh_main_effect_economy_gdp_mod_<category | all>, percentage on other buildings: scope
              province_to_region_own = every building in the province (the Warpstone Reactor +30/40/50%),
              region_to_region_own = every building in the settlement
  added       a new building: its income x (1 + the bonuses on it); an upgrade: the difference to the level before; a
              replacement: minus what the demolished building made; a level with a bonus: the extra percentage x the
              base income of everything it covers
  payback     build turns + cost / added (inf when it adds no gold: built last, still built)
Faction-wide bonuses (technologies, commandments, skills) are not counted: they scale every building alike.
"""
from __future__ import annotations
import math
from functools import lru_cache

from . import gamedata as gd

GDP = "wh_main_effect_economy_gdp_"
MOD = "wh_main_effect_economy_gdp_mod_"
OWN = "building_to_building_own"
PROVINCE, REGION = "province_to_region_own", "region_to_region_own"
BUSY = "__constructing__"


@lru_cache(maxsize=1)
def _effects() -> tuple[dict, dict]:
    """(level key -> {category: base income}, level key -> {(scope, category): percent})."""
    inc: dict[str, dict[str, float]] = {}
    mod: dict[str, dict[tuple[str, str], float]] = {}
    for r in gd._load("building_effects_junction_tables"):
        e, sc, v = r["effect"], r["effect_scope"], float(r["value"] or 0)
        if e.startswith(MOD) and sc in (PROVINCE, REGION):
            k = (sc, e[len(MOD):])
            mod.setdefault(r["building"], {})[k] = mod.get(r["building"], {}).get(k, 0) + v
        elif e.startswith(GDP) and sc == OWN:
            c = e[len(GDP):]
            inc.setdefault(r["building"], {})[c] = inc.get(r["building"], {}).get(c, 0) + v
    return inc, mod


@lru_cache(maxsize=1)
def _chain_index() -> dict[str, str]:
    return {l.key: l.chain for ls in gd.chains().values() for l in ls}


def level_key(chain: str, index: int) -> str | None:
    if chain == BUSY:
        return None
    return next((l.key for l in gd.chains().get(chain, []) if l.index == index), None)


def buildings(s) -> list[str]:
    """Level keys standing in a settlement model (main, port, slots)."""
    return [k for b in [s.main, s.port] + list(s.slots) if b is not None for k in [level_key(b.chain, b.index)] if k]


def _bonus(keys_province: list[str], keys_region: list[str], category: str) -> float:
    _inc, mod = _effects()
    pct = 0.0
    for keys, scope in ((keys_province, PROVINCE), (keys_region, REGION)):
        for k in keys:
            for (sc, c), v in mod.get(k, {}).items():
                if sc == scope and c in ("all", category):
                    pct += v
    return pct


def income(key: str | None, keys_province: list[str], keys_region: list[str]) -> float:
    """What one building level makes per turn with the bonuses that apply to it."""
    if not key:
        return 0.0
    inc, _mod = _effects()
    return sum(v * (1 + _bonus(keys_province, keys_region, c) / 100) for c, v in inc.get(key, {}).items())


def added_income(s, province: list, a) -> float:
    """Gold per turn the action adds. s: the settlement model, province: every settlement model of the province
    (s included), a: buildplan.Action."""
    inc, mod = _effects()
    new = getattr(a, "level_key", None)
    old = None
    if a.kind in ("upgrade", "upgrade_main", "upgrade_port") and new:
        ch = _chain_index().get(new)
        lv = next((l for l in gd.chains().get(ch, []) if l.key == new), None) if ch else None
        old = level_key(lv.chain, lv.index - 1) if lv else None
    elif a.kind == "replace" and getattr(a, "slot", None) is not None:
        i = a.slot - (3 if s.port is not None else 2)
        b = s.slots[i] if 0 <= i < len(s.slots) else None
        old = level_key(b.chain, b.index) if b else None
    prov_keys = [k for t in province for k in buildings(t)]
    reg_keys = buildings(s)
    gain = income(new, prov_keys, reg_keys) - income(old, prov_keys, reg_keys)
    for (sc, c), v in mod.get(new, {}).items():
        dv = v - (mod.get(old, {}).get((sc, c), 0) if old else 0)
        covered = prov_keys if sc == PROVINCE else reg_keys
        gain += sum(val for k in covered if k != old for cc, val in inc.get(k, {}).items() if c in ("all", cc)) * dv / 100
    return gain


def payback(s, province: list, a) -> float:
    """Turns until the action has paid for itself (build time included); inf when it adds no gold."""
    gain = added_income(s, province, a)
    if gain <= 0:
        return math.inf
    return (getattr(a, "turns", 0) or 0) + (getattr(a, "cost", 0) or 0) / gain
