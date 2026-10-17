"""Ikit's Forbidden Workshop (player build, 2026-10-17): a temporary Construction Cavern for workshop level 2.

The Stormfiend Ratling Cannon upgrades are workshop parts (wh3_dlc29_ikit_workshop_stormfiend_ranged_type_0/1/2);
the third needs workshop level 2, and one of level 2's requirements is a Construction Cavern (any level) standing in
any settlement. So, at workshop level 1 the building step makes sure one exists: if there is none, it builds one in a
settlement it manages (never a frontline province); while it is being built, and for the turn it is first seen
finished, the off-list rule leaves it alone; the turn after, it is released, and the off-list rule replaces it with
the planned building. After that the requirement counts as met (no second Cavern while the workshop is still level 1).

Memory (9.0.4, from the faction's has_effect_bundle Lua binding): the faction's effect bundles are an array at
faction+0x1158 (count u32 +4, array [+8], stride 0x38), each entry -> record, key = string object at record+8. The
workshop level shows as wh2_dlc12_workshop_level_<N>_dummy (none: level 0).
The only thing kept across turns is when the Cavern was first seen finished (runs/workshop.json); a turn number below
the one recorded means another save or campaign, and the record starts over.
"""
from __future__ import annotations
import json
import re

from bot import config
from bot.sensor.world import string_object

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


def plan(w, F: int, models, blocked: dict, turn: int, off_list=(), priority_of=None, special=(),
         can_host=lambda o: True):
    """-> (protected: set of (region, slot) the off-list rule must leave alone, build: (settlement, slot, demolish
    first?) to build a Cavern in or None, note: str or None). off_list: (settlement, slot) of off-list buildings the
    building step is about to replace anyway: with no free slot, the Cavern takes one of those slots first."""
    level = workshop_level(w, F)
    st = _load()
    if st.get("turn", 0) > (turn or 0):                    # another save or campaign: start over
        st = {}
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
        if building:
            protected.add((o.region, idx))
            continue
        first = seen.setdefault(key, turn)
        if turn <= first:
            protected.add((o.region, idx))                  # finished: kept for the turn it is first seen
        else:
            st["met"] = True                               # the turn after: released, the requirement counts as met
    _save(st)
    if found or st.get("met"):
        return protected, None, None
    # can_host: the settlement's main building is high enough for a Construction Cavern (tier 3, player note
    # 2026-10-17; from the game data in assist/build.py)
    for p, owned in models.items():                        # none yet: a free slot in a managed (not frontline) province
        if p in blocked:
            continue
        for o in owned:
            if not can_host(o):
                continue
            for idx, s in enumerate(o.slot_states):
                if idx > 0 and s.type == "secondary" and s.active and not s.building and not s.constructing:
                    return protected, (o, idx, False), None
    for o, idx in off_list:                                # no free slot: an off-list building's slot, first
        st = o.slot_states[idx]                           # (a Cavern only fits a secondary slot, never the port)
        if o.province not in blocked and st.type == "secondary" and not st.constructing and can_host(o):
            return protected, (o, idx, True), None
    # worst case (player rule 2026-10-17): temporarily replace the lowest-priority building on the settlement list
    # (lowest level on a tie) in a managed settlement; once the Cavern has counted, the off-list rule puts the
    # planned building back
    worst = None
    if priority_of is not None:
        for p, owned in models.items():
            if p in blocked:
                continue
            for o in owned:
                if not can_host(o):
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
