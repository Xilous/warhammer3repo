"""Army finances for the dashboard (player request 2026-10-18): what each army costs now, what a refill to the
template would make it cost, and what the next army would cost, Supply Lines included. The player decides when an
army is raised or ticked; this only does the sums. Everything from memory (bot/sensor/economy.py, world.armies) and
the game tables (main_units upkeep).

Upkeep per unit = its base upkeep (main_units_tables) x (1 + Supply Lines % x (armies - 1)). The game computes the
rest live per unit (FUN_1424B7E24: base x (100 + upkeep effects) %), nothing stores it; 2026-10-18 the base sum was
exactly the game's figure (Thanquol 3,446). A calibration on last turn's upkeep (the faction's turn record, which
is also what the game's TotalArmyUpkeep shows) was dropped: it carried last turn's units and read 3,696. A refill removes the units that are not in the template (the builder
disbands them, so they stop costing) and adds the missing ones and the Warlock Engineer. A new army adds its own
upkeep, and one more Supply Lines step on every unit of every army.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .army import delta, enabled_armies, tick_for
from .new_army import ENGINEER_UNIT, template_upkeep, upkeep_of


@dataclass
class ArmyCost:
    name: str
    cqi: int
    ticked: bool
    now: int                  # upkeep per turn now
    refilled: int             # upkeep per turn once it matches the template
    removed: int              # units a refill disbands
    income_if_refilled: int = 0   # the projected income once this army is refilled (the other ticked refills
                                  # counted too)


@dataclass
class Finance:
    income: int               # projected net income per turn (the game's last-turn figures, as the HUD shows them)
    armies: list[ArmyCost] = field(default_factory=list)
    supply_pct: int = 1
    difficulty: str = ""
    k: float = 1.0
    ticked_extra: int = 0     # what the ticked refills will add, all together
    next_army: int = 0        # what one more (template) army adds in all: its own upkeep plus Supply Lines
    next_own: int = 0
    next_supply: int = 0

    @property
    def after_ticked(self) -> int:
        return self.income - self.ticked_extra

    @property
    def after_next(self) -> int:
        return self.after_ticked - self.next_army

    def verdict(self) -> str:
        """One line: can the player afford a new army (the ticked refills counted first)."""
        if self.after_next >= 0:
            return f"✓ You can afford a new army: income after it {self.after_next:+d}/turn"
        return (f"✗ A new army is not affordable: income after it would be {self.after_next:+d}/turn "
                f"(needs {-self.after_next} more per turn)")

    def lines(self) -> list[str]:
        n = len(self.armies)
        out = [f"Income {self.income:+d}/turn · {n} arm{'y' if n == 1 else 'ies'} · Supply Lines {self.supply_pct}% per "
               f"extra army ({self.difficulty})"]
        for a in self.armies:
            s = f"{a.name}: {a.now}/turn"
            if a.refilled != a.now or a.removed:
                s += (f" → {a.refilled} if {'rebuilt' if a.removed else 'refilled'} ({a.refilled - a.now:+d}"
                      + (f"; {a.removed} units disbanded" if a.removed else "") + ")")
            if a.ticked:
                s += "  [ticked]"
            out.append(s)
        if self.ticked_extra:
            out.append(f"Ticked refills: {-self.ticked_extra:+d}/turn → income {self.after_ticked:+d}")
        out.append(f"Next army: {-self.next_army:+d}/turn ({self.next_own} its own, {self.next_supply} Supply Lines"
                   f" on the others) → income {self.after_next:+d}")
        return out


def _base(units, up) -> int:
    return sum(up.get(u, 0) for u in units)


def compute(w, F) -> Finance:
    from bot.sensor import economy
    from bot.sensor.world import armies
    up = upkeep_of()
    eco = economy.read(w, F)
    fielded = armies(w, F)
    n = len(fielded)
    pct = eco.supply_pct
    mult = 1 + pct / 100 * max(0, n - 1)
    bases = {a.cqi: _base([u.key for u in a.units], up) for a in fielded}
    est = sum(bases.values()) * mult
    k = 1.0
    _ = est
    ticked = enabled_armies()
    fin = Finance(eco.net, [], pct, eco.difficulty, round(k, 3))
    after_bases = {}
    for a in fielded:
        d = delta(a, [])
        lord = [a.units[0].key] if a.units else []
        keep = [u.key for u in a.units[1:]]
        for key in d.disband:
            if key in keep:
                keep.remove(key)
        added = [k2 for k2, c in d.missing.items() for _ in range(c)]
        added += [ENGINEER_UNIT] * sum(d.heroes_missing.values())
        after = _base(lord + keep + added, up) if d.lord_ok else bases[a.cqi]
        after_bases[a.cqi] = after
        on = tick_for(a, ticked)[0]
        fin.armies.append(ArmyCost(a.general_name, a.cqi, on, round(bases[a.cqi] * mult * k),
                                   round(after * mult * k), len(d.disband) if d.lord_ok else 0))
        if on:
            fin.ticked_extra += round((after - bases[a.cqi]) * mult * k)
    for c in fin.armies:                           # with the ticked refills, plus this one when it is not ticked
        c.income_if_refilled = fin.income - fin.ticked_extra - (0 if c.ticked else c.refilled - c.now)
    # the next army: a Warpseer with the template, and one more Supply Lines step on everything fielded
    base_planned = sum(after_bases[a.cqi] if tick_for(a, ticked)[0] else bases[a.cqi] for a in fielded)
    mult2 = 1 + pct / 100 * n
    fin.next_own = round(template_upkeep() * mult2 * k)
    fin.next_supply = round(base_planned * pct / 100 * k)
    fin.next_army = fin.next_own + fin.next_supply
    return fin


def pool_subtypes(w, F) -> list[str]:
    """Subtypes in the faction's Recruit Lord / Recruit Hero pool, from memory (Cco
    CharacterRecruitmentPoolEntriesForAgentSubtype, 0x14202E1F8, 9.0.4): pool [F+0x1578], list sentinel +0x18,
    first [+0x20], node next +8; block [node+0x18]: count u32 +0xC, array [+0x10] of entries; entry -> character
    details [e+0x18], subtype record [D+0x1F8] (key string object [rec+8])."""
    from bot.sensor.world import string_object
    out = []
    P = w.q(F + 0x1578)
    if not P:
        return out
    n = w.q(P + 0x20)
    for _ in range(200):
        if not n or n == P + 0x18:
            break
        B = w.q(n + 0x18)
        for i in range(min(w.u32(B + 0xC), 256)):
            rec = w.q(w.q(w.q(w.q(B + 0x10) + 8 * i) + 0x18) + 0x1F8)
            k = string_object(w.pm, w.q(rec + 8)) if rec else None
            if k:
                out.append(k)
        n = w.q(n + 8)
    return out


def checks(w, F) -> list[tuple[str, bool, str]]:
    """(label, met, what to do when not) for each thing a new playbook army needs: a Verminlord Warpseer in the
    Recruit Lord pool, a Warlock Engineer for it (one free, or the engineer cap has room) and a province that
    recruits the whole template. Affordability is shown, not required: the player decides."""
    from .army_builder import ENGINEER, _load_claims, eligible, free_engineer_slots
    from .army import load_automation
    from .new_army import WARPSEER
    from bot.sensor.world import characters
    t = load_automation()["army_builder"]["template"]
    claims = _load_claims()
    free = [c for c in characters(w, F) if c.embedded_force == 0 and c.subtype == ENGINEER
            and w.u32(c.ptr + 0x110) not in claims]
    slots = free_engineer_slots(w, F)
    eng = bool(free) or slots is None or slots > 0
    return [
        ("Verminlord Warpseer in the Recruit Lord pool", WARPSEER in pool_subtypes(w, F),
         "the Dominating Scheme brings one"),
        ("Warlock Engineer free" if free else "Warlock Engineer (cap has room)", eng, "none free, engineer cap full"),
        ("Province recruiting Ratling Cannons + Magma Cannons", bool(eligible(w, F, set(t["units"]))),
         "none yet"),
    ]


def readiness(w, F, fin: Finance | None = None) -> tuple[bool, str]:
    """(a new playbook army can be created now, what is missing)."""
    cs = checks(w, F)
    missing = [f"{label}: {why}" for label, ok, why in cs if not ok]
    return not missing, "; ".join(missing)
