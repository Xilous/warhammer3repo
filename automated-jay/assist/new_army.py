"""New armies, raised when the player asks (player rule 2026-10-18, replacing the builder's own decision): the
dashboard shows what every army costs, what a refill would make it cost and what the next army would cost
(assist/army_finance.py); the player decides. "Raise next army" on the dashboard asks for one, and the next army pass
raises it when
  1. a province can recruit the whole template (assist/army_builder.eligible, the builder's own test);
  2. a Verminlord Warpseer is in the Recruit Lord pool (its Verminlords tab) and the Raise button is active (Lord cap).
Asked for by the player, it is raised whatever income would be after it (player rule 2026-10-21: "the create new
playbook army button should never be locked out": a treasury of 100k pays for an army that secures a frontline while
another expands). Since 2026-10-24 (player): each press asks for one more army; a pass raises as many as the hard
requirements allow (capacity: free recruiting provinces, Warlock Engineers within the cap, Warpseers in the pool), one
per province, and the rest wait. Raised by itself (auto_create), it also needs an engineer (free, or room under the cap) and
income after it (army_finance) at or above army_builder.income_reserve.
The Warpseer is raised at a settlement of an eligible province that no other army of ours stands in, and the new army
is ticked: the builder recruits the template there in the same pass, and unticks it once it matches (army_builder).
army_builder.auto_create true brings back the old behaviour (raised by itself whenever all of the above hold).

Supply Lines (game script wh_campaign_setup.lua, apply_upkeep_penalty): every army with a general after the first
adds 1% (normal), 2% (hard) or 4% (very hard, legendary) to the upkeep of every unit. The Recruit Lord panel states
both the % (upkeep_alert/tx_line1 "...increase your total army upkeep by 1%") and the gold it adds to the armies
already fielded (tx_line2 "...estimated to increase by: 172"). Until the panel has been read once, 4% is assumed.

UI ids (9.0.4, 2026-10-18): settlement button_group_settlement/button_create_army -> root character_panel; lord type
tabs lord_parent/list_box/<type> (wh3_skv_verminlord = Verminlords); candidates general_candidate_<n>_ (tooltip
"<name>\\n<subtype>", child button_wh3), footer/button_raise.
"""
from __future__ import annotations

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


def budget(w: World, F: int) -> tuple[int, str]:
    """(gold per turn left after the ticked refills and the next army, how it was worked out), from memory."""
    from .army_finance import compute
    f = compute(w, F)
    reserve = int(load_automation()["army_builder"].get("income_reserve", 0))
    left = f.after_next - reserve
    return left, (f"income {f.income:+d}, ticked refills {-f.ticked_extra:+d}, next army {-f.next_army:+d} "
                  f"({f.supply_pct}% Supply Lines)" + (f", reserve -{reserve}" if reserve else "") + f" = {left:+d}")


def _request_file():
    from bot import config
    return config.RUNS_DIR / "raise_army.request"


def requested() -> int:
    """Armies asked for and not raised yet (player choice 2026-10-24: one more per press; presses add up)."""
    try:
        return max(0, int(_request_file().read_text(encoding="utf-8").strip() or 0))
    except (OSError, ValueError):
        return 0


def _set_requested(n: int) -> None:
    try:
        f = _request_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        if n > 0:
            f.write_text(str(n), encoding="utf-8")
        elif f.exists():
            f.unlink()
    except OSError:
        pass


def request_raise() -> None:
    """The dashboard's "Create new playbook army": one more army asked for; army passes raise them as the hard
    requirements allow (capacity), the rest wait for the next pass."""
    _set_requested(requested() + 1)


def capacity(w: World, F: int, taken: frozenset = frozenset()) -> tuple[int, dict]:
    """How many playbook armies can be raised right now, from memory, and each limit (player rule 2026-10-24: the hard
    requirements decide, not a fixed number): provinces that recruit the whole template and recruit for no other army
    this pass (taken: those army_builder.plan_provinces gave the ticked armies), Warlock Engineers (free and unclaimed,
    plus room under the engineer cap), Verminlord Warpseers in the Recruit Lord pool. The Lord cap is the Recruit Lord
    panel's (its Raise button), checked at each raise."""
    from .army_builder import ENGINEER, _load_claims, eligible, free_engineer_slots
    from .army_finance import pool_subtypes
    elig = eligible(w, F, set(load_automation()["army_builder"]["template"]["units"]))
    provinces = len([p for p in elig if p not in taken])
    claims = _load_claims()
    free = [c for c in characters(w, F) if c.embedded_force == 0 and c.subtype == ENGINEER
            and w.u32(c.ptr + 0x110) not in claims]
    slots = free_engineer_slots(w, F)
    engineers = len(free) + (max(slots, 0) if slots is not None else provinces)
    warpseers = pool_subtypes(w, F).count(WARPSEER)
    limits = {"provinces": provinces, "engineers": engineers, "warpseers": warpseers}
    return min(limits.values()), limits


def _limits_text(limits: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in limits.items())


def create_many(ui: UI, w: World, F: int, log, taken: frozenset = frozenset()) -> tuple[list[str], list]:
    """Raise the armies asked for, as many as capacity() allows now, each in its own free recruiting province. ->
    (log lines, the new armies). What cannot be raised now stays asked for."""
    ab = load_automation()["army_builder"]
    auto = ab.get("auto_create", False)
    want = 1 if auto else requested()
    if not want:
        return [], []
    n, limits = capacity(w, F, taken)
    if n <= 0:
        short = ", ".join(f"{k} {v}" for k, v in limits.items() if v <= 0)
        return [f"new army: {want} asked for, none can be raised now (no {short})"], []
    lines, news, used = [], [], set(taken)
    prov = region_provinces()[0]
    for _ in range(min(want, n)):
        got, new = create(ui, w, F, log, skip=frozenset(used))
        lines += got
        if new is None:
            break
        news.append(new)
        used.add(prov.get(new.region or "", new.region))
        if not auto:
            _set_requested(requested() - 1)
    left = 0 if auto else requested()
    if left:
        lines.append(f"new army: {left} more asked for, raised once a free recruiting province, an engineer and a "
                     f"Warpseer are there (now: {_limits_text(capacity(w, F, frozenset(used))[1])})")
    return lines, news


def raise_site(w: World, F: int, elig: dict, skip: frozenset = frozenset()) -> str | None:
    """An owned settlement of an eligible province that none of our armies stands in and that recruits for no other
    army this pass (skip); province capitals first."""
    from .army_builder import held_settlements, settlement_pos
    prov, cap = region_provinces()
    pos = settlement_pos(w, F)
    taken = held_settlements(w, F, pos, except_cqi=-1)
    sites = [r for r in pos if prov.get(r) in elig and prov.get(r) not in skip and r not in taken]
    return min(sites, key=lambda r: (not cap.get(r), r)) if sites else None


def warpseer_card(ui: UI):
    """The first Verminlord Warpseer candidate card of the open Recruit Lord panel."""
    name = gd.loc().get("agent_subtypes_onscreen_name_override_" + WARPSEER) or "Verminlord Warpseer"
    from .army_builder import card_text
    for c, i, _r in ui.nodes(ui.root_child("character_panel")):
        if i.startswith("general_candidate_") and card_text(ui, c).split("||")[0].strip().endswith(name):
            return c
    return None


def create(ui: UI, w: World, F: int, log, skip: frozenset = frozenset()) -> tuple[list[str], object | None]:
    """Raise one new Warpseer army if every condition holds, in a recruiting province not in skip. -> (log lines, the
    new army or None). create_many decides how many."""
    from .army_builder import (ENGINEER, clear, eligible, free_engineer_slots, region_name,
                               select_settlement, settlement_pos, _load_claims)
    from .heroes import park
    ab = load_automation()["army_builder"]
    t = ab["template"]
    elig = eligible(w, F, set(t["units"]))
    if not elig:
        return ["new army: no province can recruit the whole template yet"], None
    claims = _load_claims()
    free = [c for c in characters(w, F) if c.embedded_force == 0 and c.subtype == ENGINEER
            and w.u32(c.ptr + 0x110) not in claims]
    slots = free_engineer_slots(w, F)
    no_engineer = not free and slots is not None and slots <= 0
    if no_engineer:                  # a hard requirement since 2026-10-24 (player): an engineer within the cap for it
        return ["new army: no Warlock Engineer for it (none free, engineer cap full)"], None
    from .army_finance import pool_subtypes
    if WARPSEER not in pool_subtypes(w, F):
        return ["new army: no Verminlord Warpseer in the Recruit Lord pool (the Dominating Scheme brings one)"], None
    b = budget(w, F)
    if b[0] < 0 and ab.get("auto_create", False):          # raised by itself: only when it pays; asked for: shown
        return [f"new army: not affordable yet ({b[1]})"], None
    # the Lord's recruitment cost, before any click: agent_subtypes.cost (2026-10-22, live: the Recruit Lord panel showed
    # exactly the table's cost for every Lord type, Warpseer 1000, Grey Seer 850, Warlord 550, Warlock Master 1200, and
    # "You have insufficient funds" against the treasury). Asked for by the player the whole treasury may pay for it;
    # raised by itself, only what the buildings and queued units leave (army_builder.spendable).
    from .army_builder import spendable, treasury
    cost = next((int(r.get("cost") or 0) for r in gd._load("agent_subtypes_tables") if r["key"] == WARPSEER), 0)
    gold = spendable(w, F) if ab.get("auto_create", False) else treasury(w, F)
    if cost and gold < cost:
        return [f"new army: no gold for the Verminlord Warpseer ({gold} to spend, {cost} needed)"], None
    site = raise_site(w, F, elig, skip)
    if site is None:
        return ["new army: every recruiting province has an army in it or recruits for another army"], None
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
    from bot.sensor import commands             # paced by the game: the command, then the new army in memory
    _st, new = commands.act(w.pm, lambda: click(ui, raise_btn) and None,
                            lambda: next((a for a in armies(w, F) if a.cqi not in before
                                          and a.general_subtype == WARPSEER), None))
    clear(ui)
    park()
    if new is None:
        return ["new army: raising the Warpseer did not go through"], None
    set_enabled(new.cqi, new.general_name, True, new.general_id, new.turn, new.rank)
    lines.append(f"new army: raised {new.general_name} (Verminlord Warpseer) at {region_name(site)} and ticked it "
                 f"({b[1]})" + ("; its Warlock Engineer follows once the engineer cap has room" if no_engineer else ""))
    log(lines[-1])
    return lines, new
