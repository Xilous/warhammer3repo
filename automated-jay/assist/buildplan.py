"""Settlement build planner: the player's fixed priority list applied to one province.

Input is the province's current state (main building, port, what sits in each unlocked slot,
which landmarks the settlement offers). Output per settlement:
  - the final layout the list leads to at max tier
  - the next legitimate step for each layout item (upgrade main, construct, upgrade, wait, replace)
The planner never decides anything the list doesn't: it only orders work the player already chose.

    python -X utf8 -m assist.buildplan          # demo on a few example provinces
"""
from __future__ import annotations

from bot import config
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import gamedata as gd

STRATEGY = config.STRATEGY_DIR / "settlements.json"

# Game fact, unverified in-game: a port settlement's port building occupies one of the slots its
# main building unlocks (the player describes it as "the 2nd slot").
PORT_TAKES_A_SLOT = True


# ---------------------------------------------------------------- state model

@dataclass
class Building:
    chain: str
    index: int

    @property
    def name(self) -> str:
        return gd.level_name(gd.chains()[self.chain][self._pos()].key)

    def _pos(self) -> int:
        ls = gd.chains()[self.chain]
        return next(i for i, l in enumerate(ls) if l.index == self.index)


@dataclass
class Settlement:
    name: str
    capital: bool
    main: Building
    port: Building | None = None
    slots: list[Building | None] = field(default_factory=list)   # unlocked slots besides main and port
    landmarks: list[str] = field(default_factory=list)           # landmark chains buildable here
    region: str | None = None

    @property
    def kind(self) -> str:
        return "capital" if self.capital else "minor"


@dataclass
class Province:
    name: str
    settlements: list[Settlement]


# ---------------------------------------------------------------- plan model

@dataclass(frozen=True)
class Target:
    item: str
    chain: str
    index: int

    @property
    def name(self) -> str:
        return gd.level_name(level_at(self.chain, self.index).key)


@dataclass
class Action:
    settlement: str
    kind: str          # upgrade_main | upgrade_port | construct | upgrade | wait | replace | off_plan
    item: str
    detail: str
    slot: int | None = None
    cost: int = 0
    turns: int = 0
    level_key: str | None = None      # the building level this action builds or upgrades to

    def __str__(self) -> str:
        money = f"  ({self.cost} gold, {self.turns} turns)" if self.cost or self.turns else ""
        where = f" slot {self.slot}" if self.slot is not None else ""
        return f"{self.kind:12s} {self.item}{where}: {self.detail}{money}"


@dataclass
class SettlementPlan:
    settlement: Settlement
    final_slots: int
    layout: list[Target]
    actions: list[Action]


# ---------------------------------------------------------------- helpers

def strategy() -> dict:
    return json.load(open(STRATEGY, encoding="utf-8"))


def level_at(chain: str, index: int) -> gd.Level:
    return next(l for l in gd.chains()[chain] if l.index == index)


def chain_for(entry: dict, kind: str) -> str | None:
    c = entry.get("chain")
    if isinstance(c, dict):
        return c.get(kind)
    return c


def max_main_index(s: Settlement) -> int:
    return gd.main_max_index(s.main.chain)


def reachable_index(chain: str, tier: int) -> int | None:
    """Highest level of `chain` whose main-tier requirement is <= tier; None if not even the first."""
    best = None
    for l in gd.chains()[chain]:
        if l.tier <= tier:
            best = l.index
    return best


def final_slot_count(s: Settlement) -> int:
    n = gd.slots_at(s.main.chain, max_main_index(s))
    if s.port is not None and PORT_TAKES_A_SLOT:
        n -= 1
    return max(n, 0)


def current_tier(s: Settlement) -> int:
    return gd.main_tier(s.main.chain, s.main.index)


# ---------------------------------------------------------------- layout

def final_layout(s: Settlement, allowed_per_province) -> list[Target]:
    """Walk the priority list and fill the slots the settlement will have at max tier."""
    strat = strategy()
    max_tier = gd.main_tier(s.main.chain, max_main_index(s))
    n = final_slot_count(s)
    out: list[Target] = []
    for entry in strat["priority"]:
        if entry.get("landmarks"):
            cands = list(s.landmarks)
        else:
            c = chain_for(entry, s.kind)
            cands = [c] if c else []
        for c in cands:
            if c not in gd.chains():
                continue
            if entry.get("per_province") and not allowed_per_province(c, s):
                continue
            idx = reachable_index(c, max_tier)
            if idx is None:
                continue
            if len(out) >= n:
                return out
            out.append(Target(entry["name"], c, idx))
    return out


def per_province_rules() -> dict[str, int]:
    out: dict[str, int] = {}
    for e in strategy()["priority"]:
        if e.get("per_province"):
            for kind in ("capital", "minor"):
                c = chain_for(e, kind)
                if c:
                    out[c] = e["per_province"]
    return out


def plan_province(p: Province) -> list[SettlementPlan]:
    limits = per_province_rules()
    order = sorted(p.settlements, key=lambda s: not s.capital)    # capital first, then as given

    owner: dict[str, str] = {}            # existing per-province buildings stay where they are
    for s in order:
        for b in s.slots:
            if b and b.chain in limits and b.chain not in owner:
                owner[b.chain] = s.name
    used: dict[str, int] = defaultdict(int)

    def allowed(chain: str, s: Settlement) -> bool:
        if chain in owner:
            return owner[chain] == s.name
        return used[chain] < limits.get(chain, 1)

    plans = []
    for s in order:
        layout = final_layout(s, allowed)
        for t in layout:
            if t.chain in limits:
                used[t.chain] += 1
        plans.append(SettlementPlan(s, final_slot_count(s), layout, next_actions(s, layout)))
    return plans


# ---------------------------------------------------------------- next steps

def _step(s: Settlement, kind: str, item: str, chain: str, to_index: int, slot: int | None) -> Action:
    l = level_at(chain, to_index)
    return Action(s.name, kind, item, f"-> {gd.level_name(l.key)}", slot, l.cost, l.turns, l.key)


def next_actions(s: Settlement, layout: list[Target]) -> list[Action]:
    acts: list[Action] = []
    tier = current_tier(s)
    max_main = max_main_index(s)

    # 1. main building first: it caps everything else
    if s.main.index < max_main:
        acts.append(_step(s, "upgrade_main", "Main building", s.main.chain, s.main.index + 1, 1))

    # 2. port, always slot 2
    if s.port is not None:
        final = reachable_index(s.port.chain, gd.main_tier(s.main.chain, max_main))
        now = reachable_index(s.port.chain, tier)
        if now is not None and s.port.index < now:
            acts.append(_step(s, "upgrade_port", "Port", s.port.chain, s.port.index + 1, 2))
        elif final is not None and s.port.index < final:
            need = level_at(s.port.chain, s.port.index + 1).tier
            acts.append(Action(s.name, "wait", "Port", f"next level needs main building tier {need}", 2))

    # 3. layout items in priority order
    first_slot = 3 if s.port is not None else 2
    BUSY = "__constructing__"           # slot with a new building under construction (chain unknown)
    existing = {b.chain: i for i, b in enumerate(s.slots) if b is not None and b.chain != BUSY}
    planned = {t.chain for t in layout}
    free = [i for i, b in enumerate(s.slots) if b is None]
    off_plan = [i for i, b in enumerate(s.slots) if b is not None and b.chain != BUSY and b.chain not in planned]

    for t in layout:
        if t.chain in existing:
            i = existing[t.chain]
            b = s.slots[i]
            if b.index >= t.index:
                continue
            nxt = level_at(t.chain, b.index + 1)
            if nxt.tier <= tier:
                acts.append(_step(s, "upgrade", t.item, t.chain, b.index + 1, first_slot + i))
            else:
                acts.append(Action(s.name, "wait", t.item, f"{gd.level_name(nxt.key)} needs main building tier {nxt.tier}",
                                   first_slot + i))
            continue
        first = gd.chains()[t.chain][0]
        if first.tier > tier:
            acts.append(Action(s.name, "wait", t.item, f"{gd.level_name(first.key)} needs main building tier {first.tier}"))
            continue
        if free:
            i = free.pop(0)
            acts.append(_step(s, "construct", t.item, t.chain, first.index, first_slot + i))
        elif off_plan:
            i = off_plan.pop(0)
            acts.append(Action(s.name, "replace", t.item,
                               f"demolish {s.slots[i].name} and build {gd.level_name(first.key)} (needs your OK)",
                               first_slot + i, first.cost, first.turns))
        else:
            acts.append(Action(s.name, "wait", t.item, "no free slot until the main building is upgraded"))

    for i in off_plan:
        acts.append(Action(s.name, "off_plan", s.slots[i].name, "not on the list; leave it or demolish when a slot is needed",
                           first_slot + i))
    return acts


# ---------------------------------------------------------------- report

def describe(plans: list[SettlementPlan]) -> str:
    lines = []
    for sp in plans:
        s = sp.settlement
        head = f"{s.name} ({s.kind}{', port' if s.port else ''}) main {s.main.name}, {len(s.slots)} slots now, {sp.final_slots} at max"
        lines.append(head)
        lines.append("  final layout: " + (", ".join(f"{t.name}" for t in sp.layout) or "(none)"))
        for a in sp.actions:
            lines.append("  " + str(a))
    return "\n".join(lines)


def _demo() -> None:
    B = Building
    major, minor, port = "wh2_main_skv_settlement_major", "wh2_main_skv_settlement_minor", "wh2_main_skv_port"
    sb = "wh2_main_special_settlement_skavenblight"
    examples = [
        Province("Fresh conquest, non-port capital with one landmark + two minors (one a port)", [
            Settlement("Capital", True, B(major, 2), None, [None, None], ["wh2_main_special_hellpit_pits"]),
            Settlement("Minor A", False, B(minor, 1), None, [None]),
            Settlement("Minor port B", False, B(minor, 2), B(port, 1), [None]),
        ]),
        Province("Port capital at tier 5 with a landmark", [
            Settlement("Port capital", True, B(major, 5), B(port, 3),
                       [B("wh2_main_skv_energy", 2), B("wh2_main_skv_farm", 2), B("wh2_main_skv_industry", 2),
                        B("wh2_main_skv_order", 3), None, None], ["wh2_main_special_hellpit_pits"]),
        ]),
        Province("Skavenblight", [
            Settlement("Skavenblight", True, B(sb, 3), None, [B("wh2_main_skv_farm", 1), B("wh2_main_skv_clanrats", 0),
                                                              None, None, None, None],
                       gd.landmarks_for_region("wh3_main_combi_region_skavenblight")),
        ]),
    ]
    for p in examples:
        print(f"=== {p.name}")
        print(describe(plan_province(p)))
        print()


if __name__ == "__main__":
    _demo()
