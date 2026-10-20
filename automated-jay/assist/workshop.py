"""Ikit's Forbidden Workshop (player build, 2026-10-17): a Construction Cavern for workshop level 2.

The Stormfiend Ratling Cannon upgrades are workshop parts (wh3_dlc29_ikit_workshop_stormfiend_ranged_type_0/1/2);
the third needs workshop level 2, and one of level 2's requirements is a Construction Cavern (any level) standing in
any settlement. So, at workshop level 1 the building step makes sure one exists: if there is none, it builds one in a
settlement it manages (never a frontline settlement); while it is being built, and for the turn it is first seen
finished, the off-list rule leaves it alone; the turn after, it is released, and the off-list rule replaces it with
the planned building. After that the requirement counts as met (no second Cavern while the workshop is still level 1).

Since 2026-10-20 the Cavern line is on the settlement list (the Warp-Turbine Plant recruits the army's Warp-Doom
Magma-Cannons, strategy/settlements.json): a settlement whose plan holds the chain builds it as a normal building, and
that one counts. So no temporary Cavern is built while any managed settlement plans the chain, a temporary slot chosen
earlier but not started yet is dropped, and a planned Cavern is never held back from its upgrades. The temporary
Cavern below is only the fallback for when no managed settlement plans the chain.

One Cavern, ever (player rule 2026-10-17: "only 1 cavern needs to be built, ever, anywhere in my territory"). The
slot is chosen once and recorded BEFORE the first click (runs/workshop.json "cavern"); from then on the step only
ever works on that slot: demolish what stands there, build the Cavern there once the slot is free, then leave it.
Why it is recorded: memory shows no building key for a building going up in an empty slot (the slot is only
"constructing"), and a demolished building stays in its slot, "constructing", until the end of the turn; reading
"no Cavern" in either state built a second Cavern and demolished more buildings for it (turns 50-52 of the 2026-10-17
campaign: Magritta lost its Equipment Warpforge and its Clan Armoury, Skavenblight two buildings).

Memory (9.0.4, from the faction's has_effect_bundle Lua binding): the faction's effect bundles are an array at
faction+0x1158 (count u32 +4, array [+8], stride 0x38), each entry -> record, key = string object at record+8. The
workshop level shows as wh2_dlc12_workshop_level_<N>_dummy (none: level 0).
Kept across turns (runs/workshop.json): the Cavern's slot and the turn it was chosen, whether its construction was
started, and when it was first seen finished. A turn below the one the slot was chosen on (an earlier save, or another
campaign) or another faction starts the record over.
"""
from __future__ import annotations
import json
import re

from bot import config
from bot.sensor.world import string_object

SKRYRE = "wh2_main_skv_clan_skryre"               # the workshop is Ikit's (Thanquol's Clan Scruten has none)
CAVERN_CHAIN = "wh2_main_skv_engineers"          # Construction Cavern -> Warp-Forge -> Warp-Turbine Plant
CAVERN = "wh2_main_skv_engineers_1"
STATE = config.RUNS_DIR / "workshop.json"
LEVEL_RE = re.compile(r"workshop_level_(\d+)_dummy$")


def faction_bundles(w, F: int) -> list[str]:
    out = []
    try:
        C = F + 0x1158
        n, arr = w.u32(C + 4), w.q(C + 8)
        for i in range(min(n, 2000)):
            try:
                k = string_object(w.pm, w.q(arr + 0x38 * i) + 8)
                if k:
                    out.append(k)
            except Exception:
                pass
    except Exception:
        pass
    return out


def workshop_level(w, F: int) -> int:
    levels = [int(m.group(1)) for k in faction_bundles(w, F) if (m := LEVEL_RE.search(k))]
    return max(levels, default=0)


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d: dict) -> None:
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(d), encoding="utf-8")
    except OSError:
        pass


def caverns(models) -> list[tuple]:
    """(settlement, slot index, under construction) of every Construction Cavern line building (any level)."""
    out = []
    for owned in models.values():
        for o in owned:
            for idx, s in enumerate(o.slot_states):
                if s.building and s.building.startswith(CAVERN_CHAIN + "_"):
                    out.append((o, idx, bool(s.constructing)))
    return out


def commit(region: str, idx: int, turn: int, started: bool = False, faction: str | None = None) -> None:
    """Record the one Cavern's slot (before the first click on it), and later that its construction was started."""
    st = _load()
    c = st.get("cavern") or {"at": f"{region}:{idx}", "turn": turn, "faction": faction}
    if started:
        c["started"] = True
    st["cavern"] = c
    _save(st)


def _committed(st: dict):
    c = st.get("cavern")
    if not c:
        return None
    region, _, idx = c["at"].rpartition(":")
    return region, int(idx), bool(c.get("started"))


def plan(w, F: int, models, blocked: dict, turn: int, off_list=(), priority_of=None, special=(),
         can_host=lambda o: True, faction: str | None = None, planned=lambda o: False):
    """-> (protected: set of (region, slot) the off-list rule must leave alone, build: (settlement, slot, demolish
    first?) to build a Cavern in or None, note: str or None). off_list: (settlement, slot) of off-list buildings the
    building step is about to replace anyway: with no free slot, the Cavern takes one of those slots first.
    planned(o): the settlement's plan holds the Cavern chain (the Warp-Turbine Plant, 2026-10-20)."""
    if w.faction_name(F) != SKRYRE:
        return set(), None, None
    level = workshop_level(w, F)
    st = _load()
    since = (st.get("cavern") or {}).get("turn") or min((st.get("seen") or {}).values(), default=0)
    if (turn or 0) < since or (faction and (st.get("cavern") or {}).get("faction") not in (None, faction)):
        st = {}                                            # an earlier save, or another campaign: start over
    if level != 1:
        if st:
            _save({})
        return set(), None, None
    if st.get("met"):
        return set(), None, None
    st["turn"] = turn
    seen = st.setdefault("seen", {})
    protected, found = set(), caverns(models)
    for o, idx, building in found:
        key = f"{o.region}:{idx}"
        keep = not planned(o)                              # a planned one is never replaced: no need to hold it back
        if building:
            if keep:
                protected.add((o.region, idx))
            continue
        first = seen.setdefault(key, turn)
        if turn <= first:
            if keep:
                protected.add((o.region, idx))              # finished: kept for the turn it is first seen
        else:
            st["met"] = True                               # the turn after: released, the requirement counts as met
    _save(st)
    if found or st.get("met"):
        return protected, None, None
    mine = _committed(st)
    on_plan = any(planned(o) for p, owned in models.items() for o in owned if o.region not in blocked)
    if on_plan and not (mine and mine[2]):                 # the planned Cavern line counts: no temporary one
        if mine:
            st.pop("cavern", None)                         # chosen earlier, never started: dropped
            _save(st)
        return protected, None, None
    if mine:                                               # the one Cavern's slot: nothing is ever chosen again
        region, idx, started = mine
        protected.add((region, idx))
        o = next((x for xs in models.values() for x in xs if x.region == region), None)
        s = o.slot_states[idx] if o is not None and idx < len(o.slot_states) else None
        if started and (s is None or not s.constructing):  # cancelled, or the settlement lost: never another one
            st["met"] = True
            _save(st)
            return set(), None, None
        if started or s.constructing:                      # going up, or the old building is demolished at the end
            return protected, None, None                   # of the turn
        if o.region in blocked:
            return protected, None, f"the Construction Cavern waits: {o.region} is on the frontline now"
        return protected, (o, idx, bool(s.building)), None
    # can_host: the settlement's main building is high enough for a Construction Cavern (tier 3, player note
    # 2026-10-17; from the game data in assist/build.py)
    for p, owned in models.items():                        # none yet: a free slot in a managed (not frontline) settlement
        for o in owned:
            if o.region in blocked or not can_host(o):
                continue
            for idx, s in enumerate(o.slot_states):
                if idx > 0 and s.type == "secondary" and s.active and not s.building and not s.constructing:
                    return protected, (o, idx, False), None
    for o, idx in off_list:                                # no free slot: an off-list building's slot, first
        st = o.slot_states[idx]                           # (a Cavern only fits a secondary slot, never the port)
        if o.region not in blocked and st.type == "secondary" and not st.constructing and can_host(o):
            return protected, (o, idx, True), None
    # worst case (player rule 2026-10-17): temporarily replace the lowest-priority building on the settlement list
    # (lowest level on a tie) in a managed settlement; once the Cavern has counted, the off-list rule puts the
    # planned building back
    worst = None
    if priority_of is not None:
        for p, owned in models.items():
            for o in owned:
                if o.region in blocked or not can_host(o):
                    continue
                for idx, s in enumerate(o.slot_states):
                    if idx == 0 or s.type != "secondary" or not s.building or s.constructing:
                        continue
                    if any(k in s.building for k in special):
                        continue
                    rank = priority_of(o, s.building)
                    key = (rank, -(s.level or 0))
                    if worst is None or key > worst[0]:
                        worst = (key, o, idx)
    if worst:
        _key, o, idx = worst
        return protected, (o, idx, True), None
    return protected, None, ("a Construction Cavern is needed (workshop level 2) but no managed settlement with a "
                             "tier 3 main building has a slot for it")


# ------------------------------------------------------------------ buying the Stormfiend Ratling Cannon upgrades
# Player rule (2026-10-17): the three Stormfiend Ratling Cannon upgrades are bought as soon as they can be (they
# cost Warp-Fuel and food, not gold). Owned = the faction carries the upgrade's effect bundle (memory). The panel:
# HUD button_ikit_workshop -> root ikit_workshop_panel; tab buttons header_list/button_holder_<tab>/button_<tab>, of
# which only the label (child "tx", the top 50 px) is clickable (the button's centre lies below it: a click there
# did nothing); the Weapon Teams tab holds tab_weapon_teams/upgrade_list/<upgrade key>, state "available" or
# "locked_level" (workshop level too low), child icon_check visible once owned, cost/dy_reactor_cores (Warp-Fuel)
# and cost/dy_food. Closed with button_ok.
UPGRADES = ["wh3_dlc29_ikit_workshop_stormfiend_ranged_type_0",
            "wh3_dlc29_ikit_workshop_stormfiend_ranged_type_1",
            "wh3_dlc29_ikit_workshop_stormfiend_ranged_type_2"]
# (the panel shows type_2 "locked_level" below level 2). At workshop level 0 none of them is listed: the 2026-10-18
# campaign opened the panel every pass and waited 1.5 s for each, twice per pass ("not shown"); at level 1 the first
# two were found and bought (2026-10-17)
LEVEL_NEEDED = {"wh3_dlc29_ikit_workshop_stormfiend_ranged_type_0": 1,
                "wh3_dlc29_ikit_workshop_stormfiend_ranged_type_1": 1,
                "wh3_dlc29_ikit_workshop_stormfiend_ranged_type_2": 2}


def run(log=print) -> str:
    from bot.focus import game_focus
    from bot.sensor.ui import UI
    from bot.sensor.world import World, find_player_faction
    from tools import wait
    from tools.ui import click
    from . import gamedata as gd
    w = World()
    F = find_player_faction(w)
    if F is None:
        return "player faction not found"
    if w.faction_name(F) != SKRYRE:
        return "no Forbidden Workshop (Clan Skryre only)"
    owned = set(faction_bundles(w, F))
    todo = [k for k in UPGRADES if k not in owned]
    if not todo:
        return "Stormfiend Ratling Cannon upgrades: all 3 owned"
    level = workshop_level(w, F)                           # memory first: no panel opened for a part still locked
    todo = [k for k in todo if level >= LEVEL_NEEDED.get(k, 0)]
    if not todo:
        need = min(LEVEL_NEEDED.get(k, 0) for k in UPGRADES if k not in owned)
        return f"Stormfiend Ratling Cannon upgrades: the rest waits for workshop level {need} (now {level})"
    ui = UI(w.s)
    ui.find_root()
    out = []
    with game_focus():
        if not ui.root_child("ikit_workshop_panel"):          # (a click on the HUD button would close it)
            b = ui.cached("button_ikit_workshop") or ui.first("button_ikit_workshop")
            if b is None:
                return "Forbidden Workshop button not found"
            click(ui, b)
        panel = wait.wait_until(lambda: ui.root_child("ikit_workshop_panel"), 3.0, "Forbidden Workshop", must=False)
        if not panel:
            return "the Forbidden Workshop did not open"
        try:
            tab = ui.first("button_weapon_teams", under=panel)
            label = ui.child(tab, "tx") if tab else None
            if label is not None and not (ui.state(tab) or "").startswith("selected"):
                click(ui, label)
                wait.wait_until(lambda: (ui.state(tab) or "").startswith("selected"), 2.0, "Weapon Teams tab",
                                must=False)
            for key in todo:
                item = wait.wait_until(lambda k=key: ui.first(k, under=panel), 1.5, f"{key} shown", must=False)
                name = gd.loc().get(f"rituals_display_name_{key}", key)
                if item is None:
                    out.append(f"{name}: not shown")
                    continue
                if (ui.state(item) or "").startswith("locked"):
                    out.append(f"{name}: waits for the workshop level")
                    continue
                wait.stable_rect(ui, item, n=3, timeout=1.5, must=False, what=f"{key} still")
                from bot.sensor import commands  # paced by the game: the purchase command, then the bundle in memory
                with commands.Watch(w.pm) as cw:
                    click(ui, item)
                    box = wait.wait_until(lambda: ui.root_child("dialogue_box") or (cw.count and "sent"), 0.8,
                                          "confirmation", must=False)
                    if box and box != "sent":
                        tick = ui.first("button_tick", under=box)
                        if tick:
                            click(ui, tick)
                            wait.gone(ui, box, timeout=2.0, must=False, what="confirmation closed")
                    sent = wait.wait_until(lambda k=key: cw.count or not cw.ok or k in faction_bundles(w, F),
                                           commands.MISS_S, "purchase command", must=False)
                if sent and wait.wait_until(lambda k=key: k in faction_bundles(w, F), commands.EFFECT_CAP_S,
                                            f"{key} bought", must=False):
                    out.append(f"bought {name}")
                    log(f"workshop: bought {name}")
                else:
                    out.append(f"{name}: not bought (not enough Warp-Fuel or food?)")
        finally:
            p = ui.root_child("ikit_workshop_panel")
            ok = ui.first("button_ok", under=p) if p else None
            if ok:
                click(ui, ok)
                wait.gone(ui, p, timeout=2.0, must=False, what="Forbidden Workshop closed")
    return "Stormfiend Ratling Cannon upgrades: " + "; ".join(out)
