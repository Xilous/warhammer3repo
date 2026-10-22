"""The army courier (player decisions 2026-10-21): the faction leader's own army (Ikit Claw or Thanquol) recruits the
units the playbook armies have lost and carries them to the front, so the playbook armies (led by Verminlord
Warpseers) never walk back to recruit. The leader's army exists anyway, so the courier adds no Supply Lines.

One action a turn, decided from memory (`decide`, pure):
  1. no courier (no Ikit / Thanquol army) -> nothing; the playbook armies march back to recruit as before
  2. units in the courier's recruitment queue -> wait (it stays until they are recruited)
  3. the target = the ticked playbook army that is missing template units and stands outside a recruiting province,
     nearest to the courier (region hops, then the most units missing)
  4. no target -> park: stay in a recruiting province, or march to the nearest one (carrying nothing)
  5. in a recruiting province with room and gold -> recruit what the target still needs beyond what it carries
  6. carrying units the target needs -> go to the target army (right-click its lord's flag; the walk goes on next
     turn until it arrives)
  7. otherwise -> march to the nearest recruiting province
The hand-over on arrival (the game's unit exchange panel) is not automated yet: its panel is recorded in
runs/courier_panels.jsonl, closed with Escape, and the player merges the units ("merge the units yourself").

Courier settings: automation.json army_builder.courier (true; off = the playbook armies march back to recruit), in
the widget's settings.
"""
from __future__ import annotations
import json
import time
from collections import Counter
from dataclasses import dataclass, field

from bot import config
from bot.sensor.camera import character_pos
from bot.sensor.world import armies, characters, region_provinces
from tools import wait
from tools.ui import click, press
from .army import delta, enabled_armies, load_automation, tick_for, unit_name

LEADERS = ("wh2_dlc12_skv_ikit_claw", "wh3_dlc29_skv_thanquol")
FULL = 20
PANEL_LOG = config.RUNS_DIR / "courier_panels.jsonl"


def enabled() -> bool:
    try:
        return bool(load_automation()["army_builder"].get("courier", True))
    except Exception:
        return True


def find(w, F):
    """The courier: the faction leader's field army (Ikit Claw or Thanquol), or None."""
    return next((a for a in armies(w, F) if a.general_subtype in LEADERS and not a.garrison), None)


@dataclass
class Need:
    cqi: int
    name: str
    missing: dict[str, int]          # template unit -> how many
    hops: int                        # region hops from the courier


@dataclass
class Plan:
    action: str                      # none, wait, park, recruit, deliver, march, idle
    why: str = ""
    target: Need | None = None
    want: dict[str, int] = field(default_factory=dict)   # recruit: unit -> how many
    region: str | None = None        # park / march: where


def decide(cargo: dict[str, int], queued: int, room: int, in_recruit_province: bool, needs: list[Need],
           can_afford, nearest_recruit: str | None, recruitable: set[str]) -> Plan:
    """Pure: the courier's action this turn. cargo: template units it carries; queued: units in its recruitment
    queue; room: free unit slots; can_afford(want) -> True when the gold allows recruiting that; nearest_recruit: the
    nearest recruiting settlement (None when there is none); recruitable: units its province recruits now."""
    if queued:
        return Plan("wait", f"{queued} units in recruitment; it leaves once they are recruited")
    if not needs:
        if in_recruit_province:
            return Plan("idle", "no playbook army is missing units; waiting in a recruiting province")
        if nearest_recruit is None:
            return Plan("idle", "no playbook army is missing units; no recruiting province to wait in")
        return Plan("park", "no playbook army is missing units", region=nearest_recruit)
    t = min(needs, key=lambda n: (n.hops, -sum(n.missing.values())))
    useful = {u: min(n, cargo.get(u, 0)) for u, n in t.missing.items() if cargo.get(u, 0)}
    more = {u: n - cargo.get(u, 0) for u, n in t.missing.items() if n > cargo.get(u, 0)}
    if in_recruit_province and more and room > 0:
        want, left = {}, room
        for u, n in more.items():                          # template order (the Stormfiends first)
            if u in recruitable and left > 0:
                want[u] = min(n, left)
                left -= want[u]
        if want and can_afford(want):
            return Plan("recruit", f"for {t.name}", target=t, want=want)
        if not useful:
            return Plan("idle", f"{t.name} needs units; no gold to recruit them this turn" if want else
                        f"{t.name} needs units this province cannot recruit", target=t)
    if useful:
        return Plan("deliver", f"{sum(useful.values())} units for {t.name}", target=t)
    if nearest_recruit is None:
        return Plan("idle", "no province can recruit the template yet", target=t)
    return Plan("march", f"to recruit for {t.name}", target=t, region=nearest_recruit)


# ------------------------------------------------------------------ the step (memory, then the clicks)
def needs(w, F, courier, template_lords) -> list[Need]:
    """Ticked playbook armies (template lord) missing template units outside a recruiting province, with their hops
    from the courier."""
    from .army_builder import eligible, hops_from
    prov, _ = region_provinces()
    own = {w.region_key(r) for r in w.faction_regions(F)}
    tmpl = load_automation()["army_builder"]["template"]["units"]
    ticked = enabled_armies(w.faction_name(F))
    hop = {w.region_key(r): h for r, h in hops_from(w, courier.region_obj, limit=40)} if courier.region_obj else {}
    out = []
    for a in armies(w, F):
        if a.cqi == courier.cqi or a.general_subtype not in template_lords or not tick_for(a, ticked)[0]:
            continue
        miss = {u: n for u, n in delta(a, []).missing.items() if u in tmpl}
        if not miss:
            continue
        here = prov.get(a.region or "") if a.region in own else None
        if here in eligible(w, F, set(miss)):
            continue                                       # it recruits for itself where it stands
        out.append(Need(a.cqi, a.general_name, miss, hop.get(a.region, 99)))
    return out


def run(ui, w, F, log, verify: bool = False) -> list[str]:
    """The courier's turn (called by the army step after the playbook armies). Lines for the step's report."""
    from .army_builder import (closest_target, eligible, move_to, recruit_local, select_army, spendable, base_prices)
    if not enabled():
        return []
    c = find(w, F)
    if c is None:
        return []
    ab = load_automation()["army_builder"]
    tmpl = ab["template"]
    lords = set(tmpl["lord"])
    prov, _ = region_provinces()
    own = {w.region_key(r) for r in w.faction_regions(F)}
    here = prov.get(c.region or "") if c.region in own else None
    elig = eligible(w, F, set(tmpl["units"]))
    cargo = Counter(u.key for u in c.units if u.key in tmpl["units"])
    room = FULL - len(c.units) - len(c.queued)
    ns = needs(w, F, c, lords)
    near = closest_target(w, F, c, elig) if elig else None
    prices = base_prices()
    afford = lambda want: spendable(w, F) >= min(prices.get(u, 0) for u in want)
    p = decide(dict(cargo), len(c.queued), room, here in elig, ns, afford, near[0] if near else None,
               set(elig.get(here, set())) if here else set())
    name = f"courier {c.general_name}"
    if p.action in ("wait", "idle", "none"):
        return [f"{name}: {p.why}"]
    if verify:                                             # orders are not issued twice
        return []
    if not select_army(ui, c):
        return [f"{name}: could not select the army"]
    if p.action == "recruit":
        return [f"{name} ({p.why}): " + "; ".join(recruit_local(ui, w, F, p.want, log, mf=c.force_ptr))]
    if p.action in ("park", "march"):
        return [f"{name} ({p.why}): " + move_to(ui, w, c, p.region)]
    return [f"{name} ({p.why}): " + go_to_army(ui, w, F, c, p.target)]


def go_to_army(ui, w, F, courier, need: Need) -> str:
    """Right-click the target lord's flag with the courier selected: the courier walks to it, and the game opens its
    unit exchange panel on arrival. The hand-over is not automated yet: that panel is recorded and closed."""
    from .heroes import FLAG_H, bring_into_view, in_safe, jump_row, lords_row, map_label, park
    from .army_builder import select_army
    target = next((a for a in armies(w, F) if a.cqi == need.cqi), None)
    if target is None:
        return f"{need.name} not found"
    lord = next((ch for ch in characters(w, F) if ch.ptr == target.general_ptr), None)
    if lord is None:
        return f"{need.name}'s lord not found"
    lid = w.u32(lord.ptr + 0x110)
    lx, ly = character_pos(w.pm, lord.ptr)
    flag_id = f"label_{lid}"
    flag, jumped = bring_into_view(w, ui, lx, ly, flag_id, FLAG_H, jump=lambda: jump_row(ui, lords_row(ui, lid)))
    if jumped:
        select_army(ui, courier)
        flag = map_label(ui, flag_id)
    if flag is None or not in_safe(flag):
        return f"could not bring {need.name}'s flag on screen"
    before = {cid for _c, cid in ui.root_children()}
    p0 = character_pos(w.pm, courier.general_ptr)
    click(ui, flag.ptr, right=True)
    moved = wait.wait_until(lambda: character_pos(w.pm, courier.general_ptr) != p0, 1.5, "courier on the march",
                            must=False)
    from .heroes import wait_until_stopped
    wait_until_stopped(w, courier.general_ptr)
    new = sorted({cid for _c, cid in ui.root_children()} - before - {"tooltip_default"})
    if new:
        try:
            with open(PANEL_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": round(time.time(), 1), "courier": courier.general_name,
                                    "target": need.name, "panels": new}) + "\n")
        except Exception:
            pass
        press("esc")                                       # (the exchange is cancelled: nothing moves)
        wait.wait_until(lambda: not ({cid for _c, cid in ui.root_children()} & set(new)), 1.5, "panel closed",
                        must=False)
        park()
        units = ", ".join(f"{n} {unit_name(u)}" for u, n in need.missing.items())
        return f"reached {need.name}: merge the units yourself ({units}); the hand-over is not automated yet"
    park()
    return f"walking to {need.name} ({need.hops} regions away)" if moved else f"did not move toward {need.name}"
