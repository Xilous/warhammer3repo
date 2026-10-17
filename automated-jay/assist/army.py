"""Army template: compare an army (from memory) with the doomstack template in strategy/automation.json.

The template is lord (Ikit Claw, Thanquol or a Verminlord Warpseer), 1 Warlock Engineer, 6 Stormvermin (Swords &
Shields) and 12 Stormfiends (Ratling Cannons). Character units (lord and embedded heroes) appear in the
army's unit list with "_cha_" in their key.

Toggles: strategy/automation.json -> army_builder.enabled_armies =
[{"cqi": 55, "name": "Ikit Claw", "general_id": 100}].
The cqi is the game's own id for the army and survives save/load, but it is only unique within one campaign: a test
campaign and the player's real campaign hand out the same cqis. So a tick also stores the general's character id
(u32 at character +0x110) and name, and a tick whose cqi now belongs to an army under a different general is
ignored (tick_for). Entries ticked before the id was stored are matched by the general's name.
"""
from __future__ import annotations

from bot import config
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import gamedata as gd

AUTOMATION = config.STRATEGY_DIR / "automation.json"


def load_automation() -> dict:
    return json.load(open(AUTOMATION, encoding="utf-8"))


def save_automation(d: dict) -> None:
    tmp = AUTOMATION.with_suffix(".tmp")
    json.dump(d, open(tmp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    tmp.replace(AUTOMATION)


def enabled_armies() -> dict[int, dict]:
    """cqi -> tick entry {"cqi", "name", "general_id"} ("general_id" is missing in entries made before it was stored)."""
    return {e["cqi"]: e for e in load_automation()["army_builder"].get("enabled_armies", [])}


def set_enabled(cqi: int, name: str, on: bool, general_id: int | None = None) -> None:
    d = load_automation()
    lst = [e for e in d["army_builder"].get("enabled_armies", []) if e["cqi"] != cqi]
    if on:
        e = {"cqi": cqi, "name": name}
        if general_id:
            e["general_id"] = general_id
        lst.append(e)
    d["army_builder"]["enabled_armies"] = lst
    save_automation(d)


def tick_for(army, ticked: dict[int, dict] | None = None) -> tuple[bool, str]:
    """(the builder acts on this army, why a tick is ignored). A tick is keyed by cqi, which another campaign reuses:
    it counts only while the army's general is the one ticked (character id; the name for entries without an id)."""
    e = (enabled_armies() if ticked is None else ticked).get(army.cqi)
    if e is None:
        return False, ""
    gid = e.get("general_id")
    same = gid == army.general_id if gid else e.get("name", "") == army.general_name
    if same:
        return True, ""
    return False, (f"tick ignored: it was set for {e.get('name') or '?'}" + (f" (id {gid})" if gid else "")
                   + f", but this army (cqi {army.cqi}) is led by {army.general_name} (id {army.general_id}),"
                   " probably another campaign; tick it again to automate this army")


def unit_name(key: str) -> str:
    return gd.loc().get("land_units_onscreen_name_" + key, key)


@dataclass
class Delta:
    lord_ok: bool
    heroes_missing: dict[str, int] = field(default_factory=dict)
    heroes_to_move: list[str] = field(default_factory=list)      # names of free heroes that can join
    missing: dict[str, int] = field(default_factory=dict)       # unit key -> how many to recruit
    disband: list[str] = field(default_factory=list)            # unit keys to disband (one entry each)
    extra_heroes: list[str] = field(default_factory=list)       # embedded hero unit keys beyond the template;
                                                                # never disbanded automatically (player removes them)

    @property
    def matches(self) -> bool:
        return (self.lord_ok and not self.heroes_missing and not self.missing and not self.disband
                and not self.extra_heroes)

    def summary(self) -> str:
        if self.matches:
            return "matches template"
        bits = []
        if not self.lord_ok:
            bits.append("lord is not Ikit, Thanquol or a Warpseer")
        for name in self.heroes_to_move:
            bits.append(f"move {name} into this army")
        for k, n in self.heroes_missing.items():
            n -= len(self.heroes_to_move)
            if n > 0:
                bits.append(f"recruit {n} {k.split('_')[-2].title()} {k.split('_')[-1].title()} and move them in")
        for k, n in self.missing.items():
            bits.append(f"recruit {n} {unit_name(k)}")
        if self.disband:
            c = Counter(self.disband)
            bits.append("disband " + ", ".join(f"{n} {unit_name(k)}" for k, n in c.items()))
        for k in self.extra_heroes:
            bits.append(f"extra hero ({unit_name(k)}): remove it yourself")
        return "; ".join(bits)


def delta(army, free_heroes: list | None = None) -> Delta:
    """free_heroes: Character objects roaming on their own (not in any army)."""
    t = load_automation()["army_builder"]["template"]
    lord_ok = army.general_subtype in t["lord"]
    chars = [u.key for u in army.units if "_cha_" in u.key]
    troops = [u.key for u in army.units if "_cha_" not in u.key]
    lord_key = army.units[0].key if army.units else None              # the general is always the first unit
    heroes_missing = {}
    for hero, n in t["heroes"].items():
        have = sum(1 for k in chars if hero.split("_", 3)[-1] in k)
        if have < n:
            heroes_missing[hero] = n - have
    extra_heroes, kept = [], Counter()
    for k in chars[1:] if chars and chars[0] == lord_key else chars:
        hero = next((h for h in t["heroes"] if h.split("_", 3)[-1] in k), None)
        if hero is not None and kept[hero] < t["heroes"][hero]:
            kept[hero] += 1
        else:
            extra_heroes.append(k)
    want = Counter(t["units"])
    have = Counter(troops)
    coming = have + Counter(k for k in getattr(army, "queued", []) if k and k != "?")   # queued count as present
    missing = {k: n - coming.get(k, 0) for k, n in want.items() if coming.get(k, 0) < n}
    disband = []
    for k, n in have.items():
        extra = n - want.get(k, 0)
        disband += [k] * max(0, extra)
    to_move = []
    pool = list(free_heroes or [])
    for hero, n in heroes_missing.items():
        cands = [c for c in pool if c.subtype == hero][:n]
        to_move += [f"{c.name} ({(c.region or '').split('_region_')[-1].replace('_', ' ').title()})" for c in cands]
        for c in cands:
            pool.remove(c)
    return Delta(lord_ok=lord_ok, heroes_missing=heroes_missing, heroes_to_move=to_move, missing=missing,
                 disband=disband, extra_heroes=extra_heroes)
