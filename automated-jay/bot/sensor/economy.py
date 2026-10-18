"""The faction's economy from memory: last turn's income and expenses, and the campaign difficulty (Supply Lines).

Decoded 2026-10-18 (9.0.4) from the Lua bindings faction:income() (0x1427CD73C), faction:net_income()
(0x1427E4708), faction:upkeep() (0x14282898C) and model:combined_difficulty_level() (0x1427A6820):

faction F:   a ring of 10 turn records, stride 0xF4; the last finished turn is i = u32 F+0xD54 - 1 (+10 when < 0).
             income  = sum of i32 [F+0x3C8 + i*0xF4 + 0x60 .. +0x88)        (faction:income())
             expense = sum of i32 [F+0x490 + i*0xF4 .. F+0x4BC + i*0xF4)    (11 entries; net_income = income - this)
             army upkeep i32 F+0x494 + i*0xF4, navy upkeep i32 F+0x498 + i*0xF4 (faction:upkeep() = their sum)
model m:     difficulty index u32 [[m+0x5BB0]+0xE0]+0xC0: 0 easy, 1 normal, 2 hard, 3 very hard, 4 legendary
             (combined_difficulty_level 1, 0, -1, -2, -3)
Supply Lines (wh_campaign_setup.lua apply_upkeep_penalty): every army with a general from the second on carries a
factionwide upkeep effect of 1% (easy, normal), 2% (hard) or 4% (very hard, legendary), in both campaigns; so with
N armies every unit's upkeep is raised by (N - 1) x that %.
"""
from __future__ import annotations
import struct
from dataclasses import dataclass

from .world import World

SUPPLY_PCT = {0: 1, 1: 1, 2: 2, 3: 4, 4: 4}
DIFFICULTY = {0: "easy", 1: "normal", 2: "hard", 3: "very hard", 4: "legendary"}


@dataclass
class Economy:
    income: int            # last turn
    expenses: int          # last turn
    army_upkeep: int       # last turn
    navy_upkeep: int       # last turn
    difficulty: str
    supply_pct: int        # Supply Lines upkeep % per army after the first

    @property
    def net(self) -> int:
        return self.income - self.expenses


def read(w: World, F: int) -> Economy:
    pm = w.pm
    i32s = lambda a, n: struct.unpack(f"<{n}i", pm.read_bytes(a, 4 * n))
    i = w.u32(F + 0xD54) - 1
    if i < 0:
        i += 10
    rec = F + i * 0xF4
    income = sum(i32s(rec + 0x3C8 + 0x60, 10))
    expenses = sum(i32s(rec + 0x490, 11))
    army, navy = i32s(rec + 0x494, 2)
    m = w.s.model
    d = w.u32(w.q(w.q(m + 0x5BB0) + 0xE0) + 0xC0) if m else 1
    return Economy(income, expenses, army, navy, DIFFICULTY.get(d, "?"), SUPPLY_PCT.get(d, 4))
