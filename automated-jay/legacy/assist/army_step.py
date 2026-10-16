"""Turn-start army step. Acts only on armies the player ticked in the window.

Done so far: free heroes the template needs are walked into the ticked army (assist/heroes.py).
Recruitment awareness: missing units are checked against assist/recruit.py (which provinces have a
finished building that recruits them right now), so the step never plans around a building that does
not exist yet. Not built yet: disbanding, recruiting, moving the army. Those are reported, not done.
"""
from __future__ import annotations

from bot.sensor.world import World, armies, characters, find_player_faction
from .army import delta, enabled_armies, load_automation
from .heroes import move_into_army


def run(log=print) -> str:
    ticked = enabled_armies()
    if not ticked:
        return "no army ticked"
    w = World()
    F = find_player_faction(w)
    if F is None:
        return "player faction not found"
    hero_types = load_automation()["army_builder"]["template"]["heroes"]
    out = []
    for a in armies(w, F):
        if a.cqi not in ticked:
            continue
        free = [c for c in characters(w, F) if c.embedded_force == 0 and c.subtype in hero_types]
        d = delta(a, free)
        if d.heroes_to_move and len(a.units) >= 20:
            out.append(f"{a.general_name}: army is full (20/20), hero cannot join")
        elif d.heroes_to_move:
            for c in free:
                if any(c.name in s for s in d.heroes_to_move):
                    out.append(move_into_army(c.name, a.general_name, log))
        rest = delta(a, [])
        if rest.missing or (d.heroes_missing and not d.heroes_to_move):
            from .recruit import sources
            from .army import unit_name
            from . import gamedata as gd
            src = sources(w)
            for k, n in list(rest.missing.items()) + [(h, 1) for h in d.heroes_missing if not d.heroes_to_move]:
                nm = unit_name(k) if k in rest.missing else "Warlock Engineer"
                where = sorted({gd.loc().get("provinces_onscreen_" + p, p) for p, _, _ in src.get(k, [])})
                if where:
                    out.append(f"{a.general_name}: needs {n} {nm}, recruitable in {', '.join(where)} (recruiting not automated yet)")
                else:
                    out.append(f"{a.general_name}: needs {n} {nm}, but no province has the building for it yet")
        if rest.disband:
            out.append(f"{a.general_name}: disbanding not automated yet")
    missing = [n for cqi, n in ticked.items() if cqi not in {a.cqi for a in armies(w, F)}]
    if missing:
        out.append("ticked army not found: " + ", ".join(missing))
    return "; ".join(out) if out else "ticked armies match"
