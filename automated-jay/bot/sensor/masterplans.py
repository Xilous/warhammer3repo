"""Thanquol's Masterplans read from memory: plans, Risk, Alarm, loot, cards, Underlings, cooldowns, Warpstone, Secrets.

Decoded on 9.0.4 (2026-10-18) from the Lua bindings (cm:model():chaotic_plans_manager(), plan:region() ... ->
native function, live binding tables {name*, func*}) and the panel's Cco context functions (GetChanceToDrawNegative
Token, AccumulatedPooledResource, GetPositiveTokenPctToDraw ... -> the function LEA'd just before the name),
decompiled with Ghidra (tools/ghidra_quick, decomp_plans*, decomp_cco*). Checked against a live Kill-Stab (Zhufbar,
turn 2: start turn, Underling, drawn cards, card pool, Warpstone 157 as the panel showed).

model m:     plans manager M = [m+0x6DC8]; turn index u32 [[m+0x6CB0]+8] (the value plan turns and cooldowns use);
             campaign variables as floats: base Risk m+0x6C80 (2000 = 20%), Alarm threshold m+0x6C64 (4),
             pay at max Alarm m+0x6C8C (2500 = 25%); script states [m+0x6D38]
hash map H:  count u32 H+0; node list sentinel at H+8 ([H+8] first, node+0 next); node +0x10 u32 key,
             +0x14 u32 value (cooldowns) or +0x18 the value object (plans, inventories)
M:           active plans M+0x118 (key region id u32 R+8; value = plan P at node+0x18)
             Secrets inventory M+0xE8 (key faction id u32 F+8; value V: four hash maps like H at V+0x10, V+0x40,
             V+0x70, V+0xA0, token record [node+0x18]; bought Secrets land in them, checked 2026-10-18: Warpfire
             Equipment Racks bought -> wh3_dlc29_military_mod_pool_skryre_warpfire_throwers_1 in V+0x70)
             Underling cooldowns M+0x188 (key family-member id; value = turn index it ends)
             settlement cooldowns M+0x248 (key region id; value = turn index it ends)
             Underlings besieging after a Kill-Stab M+0x1B8 (key family-member id)
plan P:      region [P+0], faction [P+8], start turn index u32 P+0x10; drawn cards: count u32 P+0x28, list sentinel
             P+0x30, first [P+0x38], node next +8, token record [node+0x28]; Underling family-member id u32 P+0x88;
             plan record [P+0x90] (type key string object [rec+0x38]+8: military / economic / magic; base draws
             per turn i32 rec+0x44, increase per turn i32 rec+0x48, min turns to complete i32 rec+0x4C, runtime id
             u32 rec+0x54); loot: accumulated pooled resources at P+0xB8 (count u32 P+0xC4, array [P+0xC8], stride
             0x30: resource record [e], value i32 e+0x28; Alarm, Guards, Elites, Warpstone are among them),
             accumulated treasury i32 P+0x100; card pool (Rewards still drawable): count u32 P+0x15C, array [P+0x160]
             of {token record, i32 weight} (stride 0x10); settlement Risk level u32 P+0x188
token rec:   key string object at rec+0x48; Risk added when drawn i32 rec+0x120 (500 = 5 points); max copies +0x124
Risk:        min(10000, round(base) + level Risk + bonus(sub 3) x 100 + sum of the drawn cards' +0x120) / 100 %,
             level Risk from the DB list [db+0xE00] (db = [[[m+0x5BB0]+0xA0]+0x20]: count u32 +0xC, array [+0x10];
             row key i32 +0x1C = P+0x188, Risk i32 +0x34)
bonus:       effect bonus values (sorted array: count u32 X+4, array [X+8], stride 0x20; key u64 = category << 56 |
             sub << 40 | plan record id, record [e+0x10], value float e+0x18) on the faction (X = F+0x1A8) and on the
             Underling (X = C+0x128); category 0xF: sub 0 = plan type unlocked (> 0), 1 = draws per turn, 3 = Risk %
Alarm max:   Alarm >= round(threshold); can complete: turn index >= start + min turns (as can_execute_plan)
draws next:  base + (next turn index - start - 1) x increase + bonus(sub 1) (GetAmountOfTokensDrawnOnNextTurn)
pooled res.: faction manager [F+0x1B80]: count u32 +0x14, array [+0x18], stride 0x48: resource record [e]
             (key: char* at [[rec+8]+8]), value i32 e+0x20
script state [m+0x6D38] +0xD0 is a hash map like H keyed u64 (family id | 5 << 32): value at node+0x18 = {count u32
             +4, array [+8] of {interned name, value byte +8}}; "schemer_unlocked" says an Underling is unlocked
character:   family-member id u32 [[C+0x3F0]+8]+8; Underling subtypes wh3_dlc29_skv_schemer_*; wounded turns u32
             [C+0x3F0]+0x510 and army [[C+0x3B0]] (both checked by is_schemer_available_for_plans; 2026-10-18: the
             Grey Seer after a lost Kill-Stab battle read 4 and no army, and his card had no New Masterplan button)
"""
from __future__ import annotations
import struct
from dataclasses import dataclass, field

from .world import World, _cstr, character_name, character_subtype, find_player_faction, string_object

SCHEMER = "wh3_dlc29_skv_schemer_"
ALARM_KEY = "wh3_dlc29_chaotic_plans_alarm"
WARPSTONE_KEY = "wh3_dlc29_skv_warpstone"


@dataclass
class Plan:
    region: str
    region_obj: int
    type: str                    # military (Kill-Stab), economic (Steal-Take), magic (Great-Smart)
    start: int                   # turn index
    schemer: int                 # family-member id
    drawn: list[str]
    pool: list[tuple[str, int]]  # (card, draw weight)
    resources: dict[str, int]    # accumulated pooled resources (loot, Alarm, Guards, Elites)
    treasury: int                # accumulated gold
    risk: float                  # %
    alarm: int
    alarm_max: int
    can_complete: bool
    draws_next: int


@dataclass
class Underling:
    ptr: int
    family: int
    subtype: str
    name: str
    unlocked: bool
    on_plan: bool
    cooldown: int                # turns left
    besieging: bool
    wounded: int = 0             # turns until he recovers (his army was lost, e.g. in a Kill-Stab battle)
    has_army: bool = True

    @property
    def free(self) -> bool:
        """As is_schemer_available_for_plans (0x1428CCC38): unlocked, no cooldown, not wounded, his one-unit army
        alive, not on a plan and not besieging."""
        return (self.unlocked and not self.on_plan and not self.besieging and self.cooldown == 0
                and self.wounded == 0 and self.has_army)


@dataclass
class State:
    turn_index: int
    plans: list[Plan] = field(default_factory=list)
    underlings: list[Underling] = field(default_factory=list)
    region_cooldowns: dict[str, int] = field(default_factory=dict)   # region key -> turns left
    warpstone: int = 0
    inventory: list[str] = field(default_factory=list)               # Secrets tokens owned
    unlocked_types: set[str] = field(default_factory=set)


class Reader:
    def __init__(self, w: World | None = None) -> None:
        self.w = w or World()

    # ---------------------------------------------------------------- primitives
    def i32(self, a: int) -> int:
        return struct.unpack("<i", self.w.pm.read_bytes(a, 4))[0]

    def f32(self, a: int) -> float:
        return struct.unpack("<f", self.w.pm.read_bytes(a, 4))[0]

    def nodes(self, H: int, limit: int = 4000):
        """Hash-map nodes: list sentinel at H+8, node+0 next."""
        w = self.w
        n = w.q(H + 8)
        for _ in range(limit):
            if not n or n == H + 8:
                return
            yield n
            n = w.q(n)

    def tokens(self, sentinel: int, first: int, rec_off: int, limit: int = 200) -> list[str]:
        w, out = self.w, []
        n = first
        for _ in range(limit):
            if not n or n == sentinel:
                break
            out.append(string_object(w.pm, w.q(n + rec_off) + 0x48) or "?")
            n = w.q(n + 8)
        return out

    def bonus(self, X: int, sub: int, rec_id: int) -> float:
        w = self.w
        n, arr = w.u32(X + 4), w.q(X + 8)
        key = (0xF << 56) | (sub << 40) | rec_id
        tot = 0.0
        for i in range(min(n, 20000)):
            if w.q(arr + 0x20 * i) == key:
                tot += self.f32(arr + 0x20 * i + 0x18)
        return tot

    @staticmethod
    def rnd(x: float) -> int:
        return int(x - 0.5) if x <= 0 else int(x + 0.5)

    def res_key(self, rec: int) -> str | None:
        try:
            return _cstr(self.w.pm, self.w.q(self.w.q(rec + 8) + 8))
        except Exception:
            return None

    # ---------------------------------------------------------------- reads
    def state(self, F: int | None = None) -> State | None:
        w = self.w
        m = w.s.model
        if not m:
            return None
        F = F or find_player_faction(w)
        if F is None:
            return None
        M = w.q(m + 0x6DC8)
        if not M:
            return None
        turn = w.u32(w.q(m + 0x6CB0) + 8)
        st = State(turn)
        chars = self._underling_chars(F)
        for node in self.nodes(M + 0x118):
            P = node + 0x18
            if w.q(P + 8) != F:
                continue
            st.plans.append(self._plan(m, F, P, turn, chars))
        busy = {p.schemer for p in st.plans}
        besieging = {w.u32(n + 0x10) for n in self.nodes(M + 0x1B8)}
        cds = {w.u32(n + 0x10): w.u32(n + 0x14) for n in self.nodes(M + 0x188)}
        unlocked = self._unlocked_families(m)
        for fam, (C, sub) in chars.items():
            force = w.q(C + 0x3B0)
            st.underlings.append(Underling(C, fam, sub, character_name(w, C), unlocked.get(fam, False),
                                           fam in busy, max(0, cds.get(fam, 0) - turn), fam in besieging,
                                           w.u32(w.q(C + 0x3F0) + 0x510), bool(force and w.q(force))))
        rid = self._region_ids(F)
        for n in self.nodes(M + 0x248):
            left = w.u32(n + 0x14) - turn
            if left > 0:
                st.region_cooldowns[rid.get(w.u32(n + 0x10), str(w.u32(n + 0x10)))] = left
        st.warpstone = self.pooled(F).get(WARPSTONE_KEY, 0)
        fid = w.u32(F + 8)
        for n in self.nodes(M + 0xE8):
            if w.u32(n + 0x10) == fid:
                V = n + 0x18
                for H in (V + 0x10, V + 0x40, V + 0x70, V + 0xA0):      # (the four GetOwnedTokensCount... walks)
                    for t in self.nodes(H, limit=500):
                        k = string_object(w.pm, w.q(t + 0x18) + 0x48) if w.q(t + 0x18) else None
                        if k and k.startswith("wh3_"):
                            st.inventory.append(k)
        st.unlocked_types = self.unlocked_types(F)
        return st

    def _plan(self, m: int, F: int, P: int, turn: int, chars: dict) -> Plan:
        w = self.w
        R = w.q(P)
        rec = w.q(P + 0x90)
        ptype = string_object(w.pm, w.q(rec + 0x38) + 8) or "?"
        start = w.u32(P + 0x10)
        drawn_risk, drawn = 0, []
        n = w.q(P + 0x38)
        for _ in range(200):
            if not n or n == P + 0x30:
                break
            t = w.q(n + 0x28)
            drawn.append(string_object(w.pm, t + 0x48) or "?")
            drawn_risk += self.i32(t + 0x120)
            n = w.q(n + 8)
        pool = []
        cnt, arr = w.u32(P + 0x15C), w.q(P + 0x160)
        for i in range(min(cnt, 200)):
            pool.append((string_object(w.pm, w.q(arr + 0x10 * i) + 0x48) or "?", self.i32(arr + 0x10 * i + 8)))
        res = {}
        cnt, arr = w.u32(P + 0xC4), w.q(P + 0xC8)
        for i in range(min(cnt, 64)):
            e = arr + 0x30 * i
            k = self.res_key(w.q(e)) if w.q(e) else None
            if k:
                res[k] = res.get(k, 0) + self.i32(e + 0x28)
        rid = w.u32(rec + 0x54)
        fam = w.u32(P + 0x88)
        C = chars.get(fam, (0, ""))[0]
        bon = lambda sub: self.bonus(F + 0x1A8, sub, rid) + (self.bonus(C + 0x128, sub, rid) if C else 0.0)
        level_risk = 0
        db = w.q(w.q(w.q(m + 0x5BB0) + 0xA0) + 0x20)
        L = w.q(db + 0xE00)
        lvl = w.u32(P + 0x188)
        for i in range(min(w.u32(L + 0xC), 64)):
            row = w.q(w.q(L + 0x10) + 8 * i)
            if self.i32(row + 0x1C) == lvl:
                level_risk = self.i32(row + 0x34) + self.rnd(self.f32(m + 0x6C80))
                break
        risk = max(0, min(10000, level_risk + int(bon(3) * 100) + max(0, drawn_risk)))
        nxt = turn + 1
        draws = 0
        if start < nxt:
            draws = max(1, self.i32(rec + 0x44) + (nxt - start - 1) * self.i32(rec + 0x48) + self.rnd(bon(1)))
        return Plan(w.region_key(R) or "?", R, ptype, start, fam, drawn, pool, res, self.i32(P + 0x100),
                    risk / 100.0, res.get(ALARM_KEY, 0), self.rnd(self.f32(m + 0x6C64)),
                    turn >= start + self.i32(rec + 0x4C), draws)

    def _underling_chars(self, F: int) -> dict[int, tuple[int, str]]:
        """family-member id -> (character, subtype) for the faction's Underlings."""
        w, out = self.w, {}
        n, arr = w.u32(F + 0xF24), w.q(F + 0xF28)
        for i in range(min(n, 500)):
            try:
                C = w.q(w.q(arr + 8 * i))
                sub = character_subtype(w, C) or ""
                if sub.startswith(SCHEMER):
                    out[w.u32(w.q(w.q(C + 0x3F0) + 8) + 8)] = (C, sub)
            except Exception:
                continue
        return out

    def _unlocked_families(self, m: int) -> dict[int, bool]:
        """family-member id -> the "schemer_unlocked" script state."""
        w, out = self.w, {}
        S = w.q(m + 0x6D38)
        if not S:
            return out
        for n in self.nodes(S + 0xD0, limit=200000):
            key = w.q(n + 0x10)
            if key >> 32 != 5:
                continue
            V = n + 0x18
            cnt, arr = w.u32(V + 4), w.q(V + 8)
            for i in range(min(cnt, 64)):
                name = self._interned(w.q(arr + 0x10 * i))
                if name == "schemer_unlocked":
                    out[key & 0xFFFFFFFF] = bool(w.pm.read_bytes(arr + 0x10 * i + 8, 1)[0])
        return out

    def _interned(self, p: int) -> str | None:
        if not p:
            return None
        for f in (lambda: string_object(self.w.pm, p), lambda: _cstr(self.w.pm, p),
                  lambda: _cstr(self.w.pm, self.w.q(p)), lambda: _cstr(self.w.pm, self.w.q(p + 8))):
            try:
                s = f()
            except Exception:
                s = None
            if s:
                return s
        return None

    def _region_ids(self, F: int) -> dict[int, str]:
        """region id (u32 R+8) -> key, for every region (walked from ours through the neighbour graph)."""
        w, out = self.w, {}
        front = list(w.faction_regions(F))
        seen = set(front)
        while front:
            r = front.pop()
            k = w.region_key(r)
            if k:
                out[w.u32(r + 8)] = k
            for nb in w.neighbours(r):
                if nb not in seen:
                    seen.add(nb)
                    front.append(nb)
        return out

    def pooled(self, F: int) -> dict[str, int]:
        w, out = self.w, {}
        prm = w.q(F + 0x1B80)
        if not prm:
            return out
        for i in range(min(w.u32(prm + 0x14), 64)):
            e = w.q(prm + 0x18) + 0x48 * i
            k = self.res_key(w.q(e))
            if k:
                out[k] = self.i32(e + 0x20)
        return out

    def unlocked_types(self, F: int) -> set[str]:
        """Plan types the faction may start (effect bonus category 0xF, sub 0 > 0, as IsChaoticPlanUnlocked)."""
        w, out = self.w, set()
        X = F + 0x1A8
        n, arr = w.u32(X + 4), w.q(X + 8)
        for i in range(min(n, 20000)):
            e = arr + 0x20 * i
            k = w.q(e)
            if k >> 56 == 0xF and (k >> 40) & 0xFFFF == 0 and self.f32(e + 0x18) > 0:
                rec = w.q(e + 0x10)
                t = string_object(w.pm, w.q(rec + 0x38) + 8) if rec else None
                if t:
                    out.add(t)
        return out


def read(w: World | None = None) -> State | None:
    return Reader(w).state()


if __name__ == "__main__":
    import pprint
    pprint.pprint(read())
