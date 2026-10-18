"""New armies (player rule 2026-10-18): the army builder raises a new doomstack by itself, at most one per turn, when
  1. a province can recruit the whole template (assist/army_builder.eligible, the builder's own test);
  2. the new army can have its Warlock Engineer: one is free (unclaimed) or the engineer cap has room (the cap as the
     Recruit Hero panel last showed it, runs/caps.json; never read yet = not a reason to wait);
  3. income pays for the whole army: projected income (HUD treasury_holder/dy_income, the "(-8)" next to the treasury)
     minus the upkeep still to come from the troops and engineers ticked armies are missing (queued ones included:
     they pay nothing until recruited), with Supply Lines, minus the new army's upkeep with Supply
     Lines on it, minus the Supply Lines increase on the armies already fielded, stays at or above
     army_builder.income_reserve;
  4. a Verminlord Warpseer is in the Recruit Lord pool (its Verminlords tab) and the Raise button is active (Lord cap).
The Warpseer is raised at a settlement of an eligible province that no other army of ours stands in, and the new army
is ticked: the builder recruits the template there in the same pass, and unticks it once it matches (army_builder).

Supply Lines (game script wh_campaign_setup.lua, apply_upkeep_penalty): every army with a general after the first
adds 1% (normal), 2% (hard) or 4% (very hard, legendary) to the upkeep of every unit. The Recruit Lord panel states
both the % (upkeep_alert/tx_line1 "...increase your total army upkeep by 1%") and the gold it adds to the armies
already fielded (tx_line2 "...estimated to increase by: 172"). Until the panel has been read once, 4% is assumed.

UI ids (9.0.4, 2026-10-18): settlement button_group_settlement/button_create_army -> root character_panel; lord type
tabs lord_parent/list_box/<type> (wh3_skv_verminlord = Verminlords); candidates general_candidate_<n>_ (tooltip
"<name>\\n<subtype>", child button_wh3), footer/button_raise.
"""
from __future__ import annotations
import re

from bot.sensor.ui import UI
from bot.sensor.world import World, armies, characters, region_provinces
from tools import wait
from tools.ui import click
from . import gamedata as gd
from .army import delta, enabled_armies, load_automation, set_enabled, tick_for

WARPSEER = "wh3_dlc29_skv_verminlord_warpseer"
WARPSEER_UNIT = "wh3_dlc29_skv_cha_verminlord_warpseer"         # the lord's own unit card (main_units key)
ENGINEER_UNIT = "wh2_main_skv_cha_warlock_engineer"
VERMINLORD_TAB = "wh3_skv_verminlord"
SUPPLY_LINES_DEFAULT = 4                                         # % per army: the hardest difficulties' value


def upkeep_of() -> dict[str, int]:
    """main_units key -> base upkeep per turn."""
    return {r["unit"]: int(r.get("upkeep_cost") or 0) for r in gd._load("main_units_tables")}


def template_upkeep() -> int:
    """Base upkeep of a whole new army: Warpseer, its Warlock Engineer and the template's units."""
    up = upkeep_of()
    t = load_automation()["army_builder"]["template"]
    return (up.get(WARPSEER_UNIT, 0) + up.get(ENGINEER_UNIT, 0) * t["heroes"].get("wh2_main_skv_warlock_engineer", 0)
            + sum(up.get(k, 0) * n for k, n in t["units"].items()))


def pending_upkeep(w: World, F: int) -> int:
    """Base upkeep the ticked armies will add once their missing troops and Warlock Engineers are recruited: none of
    it is in the income yet. Units in the recruitment queue count as missing here (2026-10-18: Ikit's ticked army
    had its refill queued, delta() counts queued units as present, so the budget saw no upkeep to come and a
    Warpseer army was raised on top; queued units pay no upkeep until they are recruited)."""
    from dataclasses import replace
    up = upkeep_of()
    hero_unit = {"wh2_main_skv_warlock_engineer": ENGINEER_UNIT}
    ticked = enabled_armies()
    total = 0
    for a in armies(w, F):
        if not tick_for(a, ticked)[0]:
            continue
        d = delta(replace(a, queued=[]), [])
        total += sum(up.get(k, 0) * n for k, n in d.missing.items())
        total += sum(up.get(hero_unit.get(h, h), 0) * n for h, n in d.heroes_missing.items())
    return total


def _number(text: str | None) -> int | None:
    m = re.search(r"[-+]?[\d,]+", re.sub(r"\[\[.*?\]\]", "", text or ""))
    return int(m.group(0).replace(",", "")) if m else None


def income(ui: UI) -> int | None:
    """Projected income per turn, as the HUD shows it in brackets next to the treasury."""
    c = ui.first("dy_income", under="treasury_holder")
    return _number(ui.text(c)) if c else None


def budget(ui: UI, w: World, F: int, pct: float, increase: int | None = None) -> tuple[int, str] | None:
    """(gold per turn left after the new army, how it was worked out) or None when the income cannot be read.
    increase: the game's estimate of the Supply Lines increase on the armies already fielded; without it, pct of the
    fielded armies' base upkeep."""
    inc = income(ui)
    if inc is None:
        return None
    up = upkeep_of()
    fielded = armies(w, F)
    if increase is None:
        increase = round(pct / 100 * sum(up.get(u.key, 0) for a in fielded for u in a.units))
    supply = 1 + pct / 100 * len(fielded)               # Supply Lines on every unit once the new army is fielded
    new = round(template_upkeep() * supply)
    pend = round(pending_upkeep(w, F) * supply)
    reserve = int(load_automation()["army_builder"].get("income_reserve", 0))
    left = inc - pend - new - increase - reserve
    return left, (f"income {inc:+d}, still to recruit for ticked armies -{pend}, new army -{new}, Supply Lines "
                  f"{pct:g}% on the fielded armies -{increase}" + (f", reserve -{reserve}" if reserve else "")
                  + f" = {left:+d}")


def raise_site(w: World, F: int, elig: dict) -> str | None:
    """An owned settlement of an eligible province that none of our armies stands in; province capitals first."""
    from .army_builder import held_settlements, settlement_pos
    prov, cap = region_provinces()
    pos = settlement_pos(w, F)
    taken = held_settlements(w, F, pos, except_cqi=-1)
    sites = [r for r in pos if prov.get(r) in elig and r not in taken]
    return min(sites, key=lambda r: (not cap.get(r), r)) if sites else None


def _alert(ui: UI) -> tuple[float | None, int | None]:
    """(Supply Lines % per army, gold increase on the fielded armies) from the Recruit Lord panel."""
    l1 = ui.first("tx_line1", under="upkeep_alert")
    l2 = ui.first("tx_line2", under="upkeep_alert")
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", ui.text(l1) or "") if l1 else None
    return (float(m.group(1)) if m else None), (_number((ui.text(l2) or "").split(":")[-1]) if l2 else None)


def warpseer_card(ui: UI):
    """The first Verminlord Warpseer candidate card of the open Recruit Lord panel."""
    name = gd.loc().get("agent_subtypes_onscreen_name_override_" + WARPSEER) or "Verminlord Warpseer"
    from .army_builder import card_text
    for c, i, _r in ui.nodes(ui.root_child("character_panel")):
        if i.startswith("general_candidate_") and card_text(ui, c).split("||")[0].strip().endswith(name):
            return c
    return None


def create(ui: UI, w: World, F: int, log) -> tuple[list[str], object | None]:
    """Raise one new Warpseer army if every condition holds. -> (log lines, the new army or None)."""
    from .army_builder import (ENGINEER, clear, eligible, free_engineer_slots, load_caps, region_name, save_caps,
                               select_settlement, settlement_pos, _load_claims)
    from .heroes import park
    ab = load_automation()["army_builder"]
    if not ab.get("auto_create", True):
        return [], None
    t = ab["template"]
    elig = eligible(w, F, set(t["units"]))
    if not elig:
        return ["new army: no province can recruit the whole template yet"], None
    claims = _load_claims()
    free = [c for c in characters(w, F) if c.embedded_force == 0 and c.subtype == ENGINEER
            and w.u32(c.ptr + 0x110) not in claims]
    slots = free_engineer_slots(w, F)
    if not free and slots is not None and slots <= 0:
        return ["new army: no Warlock Engineer for it (none free, engineer cap full)"], None
    caps = load_caps()
    pct = caps.get("supply_lines_pct") or SUPPLY_LINES_DEFAULT
    b = budget(ui, w, F, pct)
    if b is None:
        return ["new army: the income on the HUD could not be read"], None
    if b[0] < 0:
        return [f"new army: not affordable yet ({b[1]})"], None
    site = raise_site(w, F, elig)
    if site is None:
        return ["new army: every settlement of the recruiting provinces has an army in it"], None
    clear(ui)
    if not select_settlement(ui, w, site, settlement_pos(w, F)[site]):
        return [f"new army: could not select {region_name(site)}"], None
    btn = wait.appears(ui, "button_create_army", under="button_group_settlement", timeout=2.0, must=False)
    if btn is None or ui.state(btn.ptr) == "inactive":
        clear(ui)
        return [f"new army: no Recruit Lord at {region_name(site)}"], None
    click(ui, btn.ptr)
    if wait.appears(ui, "button_raise", under="character_panel", timeout=3.0, must=False) is None:
        clear(ui)
        return ["new army: the Recruit Lord panel did not open"], None
    lines = []
    pct2, increase = _alert(ui)
    if pct2 is not None:
        save_caps(supply_lines_pct=pct2)
        pct = pct2
    b = budget(ui, w, F, pct, increase)
    if b is None or b[0] < 0:
        clear(ui)
        park()
        return [f"new army: not affordable yet ({b[1] if b else 'income unreadable'})"], None
    tab = wait.appears(ui, VERMINLORD_TAB, under="lord_parent", timeout=2.0, must=False)
    if tab is None:
        clear(ui)
        park()
        return ["new army: no Verminlords tab in the Recruit Lord panel"], None
    if not (ui.state(tab.ptr) or "").startswith("selected"):
        click(ui, tab.ptr)
    card = wait.wait_until(lambda: warpseer_card(ui), 2.0, "Warpseer candidate listed", must=False)
    if card is None:
        clear(ui)
        park()
        return ["new army: no Verminlord Warpseer in the Recruit Lord pool (the Dominating Scheme brings one)"], None
    if not ui.in_clip(card):
        clear(ui)
        park()
        return ["new army: the Warpseer candidate is scrolled out of view"], None
    pick = ui.child(card, "button_wh3") or card
    click(ui, pick)
    wait.wait_until(lambda: (ui.state(card) or "").startswith("selected"), 1.0, "Warpseer candidate selected",
                    must=False)
    raise_btn = ui.first("button_raise", under="character_panel")
    wait.stable(lambda: ui.state(raise_btn), n=2, timeout=1.0, what="Raise button state", ui=ui, must=False)
    if not (ui.state(card) or "").startswith("selected") or ui.state(raise_btn) == "inactive":
        clear(ui)
        park()
        return ["new army: the Warpseer could not be raised (Lord cap full or not enough gold)"], None
    before = {a.cqi for a in armies(w, F)}
    click(ui, raise_btn)
    new = wait.wait_until(lambda: next((a for a in armies(w, F) if a.cqi not in before
                                        and a.general_subtype == WARPSEER), None), 3.0, "new army in memory",
                          must=False)
    clear(ui)
    park()
    if new is None:
        return ["new army: raising the Warpseer did not go through"], None
    set_enabled(new.cqi, new.general_name, True, new.general_id)
    lines.append(f"new army: raised {new.general_name} (Verminlord Warpseer) at {region_name(site)} and ticked it "
                 f"({b[1]})")
    log(lines[-1])
    return lines, new
