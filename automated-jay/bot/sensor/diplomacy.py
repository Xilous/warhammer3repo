"""Diplomacy state from memory: who can be a player's faction (major), treaties, treasuries, borders.

Decoded on 9.0.4, 2026-10-21, from the faction script interface's Lua bindings (the live binding table next to
is_human, natives disassembled), and checked live on turn 1 of a single-player Clan Scruten campaign:

  faction F   is_dead          byte F+0x10C0 != 0 (binding 0x1427d0864); live 2026-10-21: 250 of 559 factions dead,
                               none holding a region, none met or at war with the player
              can_be_human     byte F+0xEB5 != 0 (binding 0x14279cde8): the factions a player can pick at lord
                               select. 1 for all 109 lord-select factions in the campaign (landless hordes too:
                               Beastmen, the Warriors of Chaos lords), 0 for the 451 others (minor factions, quest
                               factions, separatists, the Chaos challengers). This is "major" for the assistant.
              treasury         i32 F+0xD58 (binding 0x14281e244); matched the HUD and the diplomacy panel (2567)
  relationship entry e of F's list [F+0xDB8] (count u32 +4, base +8, stride 0x78; the other faction at e+0x28):
              state            i32 [[e+0x30]+0x20]: 0 war, 1 peace, 2 defensive alliance (defensive_allies_with),
                               3 military alliance (military_allies_with), 7 vassal of (is_vassal_of); 2..7 = ally,
                               vassal or client state (is_ally_vassal_or_client_state_of, FUN_1423b5a30)
              flags            byte e+0x74: bit 0 trade agreement (trade_agreement_with), bit 2 met, bit 3
                               non-aggression pact (non_aggression_pact_with)
  strength    faction_strength (binding 0x1427bbefc), the campaign AI's own measure:
                 B = [[[[[F+0x3A8]+0x90]+0x6CD0]+0x990]+0x10]
                 H = [[B+0xE0]+0x280]: open-addressing table, capacity u32 H+0x80, empty key u32 H+0x84, entries
                     [H+0x78] of 16 bytes {u32 key, entry*}, probed from (u32 F+8) % capacity (FUN_142b558e8) -> E
                 M = [B+0x1D8]+0x1E8: a map whose nodes form a list from [M+8] back to M+8 (node: next +0, key u32
                     +0x10, strength u32 +0x14), key u32 E+0x40 (FUN_142b12330)
              Read live 2026-10-21 (Scruten turn 1): Scruten 2.79 M, Bloody Spearz 2.77 M, Disciples of the Maw 2.53 M
              ... Stirland 0.78 M; Zhufbar (at war with the player) 0. Not yet compared with the panel's Strength Rank.
"""
from __future__ import annotations
import struct
from dataclasses import dataclass, field

from .world import World, is_human

CAN_BE_HUMAN = 0xEB5
DEAD = 0x10C0
TREASURY = 0xD58
REL_LIST, REL_STRIDE, REL_OTHER, REL_STATE, REL_FLAGS = 0xDB8, 0x78, 0x28, 0x30, 0x74
WAR, PEACE = 0, 1
TRADE, MET, NAP = 1, 4, 8


@dataclass(frozen=True)
class Rel:
    state: int          # 0 war, 1 peace, 2..7 ally / vassal / client
    flags: int          # e+0x74

    @property
    def war(self) -> bool:
        return self.state == WAR

    @property
    def met(self) -> bool:
        return bool(self.flags & MET)

    @property
    def treaty(self) -> bool:
        """Any treaty a war would break or that ties the two: trade, non-aggression, alliance, vassal, client."""
        return 2 <= self.state <= 7 or bool(self.flags & (TRADE | NAP))


@dataclass
class Faction:
    key: str
    ptr: int
    major: bool                       # can_be_human
    human: bool
    rebel: bool                       # factions table is_rebel
    regions: int
    treasury: int
    strength: int = 0                 # faction_strength (0 when not found or not met)
    rels: dict[str, Rel] = field(default_factory=dict)     # other faction key -> relationship
    dead: bool = False                # is_dead: wiped out


def _i32(w: World, a: int) -> int:
    return struct.unpack("<i", w.pm.read_bytes(a, 4))[0]


def can_be_human(w: World, f: int) -> bool:
    return w.pm.read_bytes(f + CAN_BE_HUMAN, 1)[0] != 0


def is_dead(w: World, f: int) -> bool:
    return w.pm.read_bytes(f + DEAD, 1)[0] != 0


def treasury(w: World, f: int) -> int:
    return _i32(w, f + TREASURY)


def strengths(w: World, fs: list[int]) -> dict[int, int]:
    """faction_strength for each faction in fs (see the module docstring), the AI's map walked once; 0 when the AI
    holds no entry for a faction."""
    out = {f: 0 for f in fs}
    if not fs:
        return out
    try:
        q, u32 = w.q, w.u32
        B = q(q(q(q(q(fs[0] + 0x3A8) + 0x90) + 0x6CD0) + 0x990) + 0x10)
        H = q(q(B + 0xE0) + 0x280)
        cap, empty, arr = u32(H + 0x80), u32(H + 0x84), q(H + 0x78)
        want: dict[int, int] = {}                      # E+0x40 key -> faction
        for f in fs:
            key = u32(f + 8)
            i = key % cap
            for _ in range(cap):
                k = u32(arr + 16 * i)
                if k == key:
                    want[u32(q(arr + 16 * i + 8) + 0x40)] = f
                    break
                if k == empty:
                    break
                i = (i + 1) % cap
        M = q(B + 0x1D8) + 0x1E8
        head = M + 8
        n = q(head)
        for _ in range(100_000):
            if not n or n == head or len(want) == 0:
                break
            f = want.pop(u32(n + 0x10), None)
            if f is not None:
                out[f] = u32(n + 0x14)
            n = q(n)
    except Exception:
        pass
    return out


def relations(w: World, f: int, only: set[int] | None = None) -> dict[int, Rel]:
    """f's relationship with every faction in its list, or with those in `only` (faction pointer -> Rel). The list
    is read in one block; the state pointer is followed only for the entries kept."""
    rel = w.q(f + REL_LIST)
    if not rel:
        return {}
    n, base = min(w.u32(rel + 4), 4000), w.q(rel + 8)
    try:
        raw = w.pm.read_bytes(base, n * REL_STRIDE) if n else b""
    except Exception:
        return {}
    out = {}
    for i in range(n):
        o = struct.unpack_from("<Q", raw, REL_STRIDE * i + REL_OTHER)[0]
        if not o or (only is not None and o not in only):
            continue
        try:
            st = _i32(w, struct.unpack_from("<Q", raw, REL_STRIDE * i + REL_STATE)[0] + 0x20)
        except Exception:
            continue
        out[o] = Rel(st, raw[REL_STRIDE * i + REL_FLAGS])
    return out


def neighbours_of(w: World, f: int) -> set[str]:
    """Keys of the factions owning a region next to one of f's regions."""
    out = set()
    for r in w.faction_regions(f):
        for n in w.neighbours(r):
            o = w.region_owner(n)
            if o and o != f:
                k = w.faction_name(o)
                if k:
                    out.add(k)
    return out


def read(w: World, F: int) -> tuple[Faction, dict[str, Faction], set[str]]:
    """The player's faction, every faction it has a relationship with, and the keys of the factions bordering the
    player. An AI faction the player has met and that holds land also gets its relationships with the majors the
    player has met and with the humans (all a deal needs); the others' rels stay empty."""
    from assist import gamedata as gd
    rebel = {r["key"] for r in gd._load("factions_tables") if r.get("is_rebel")}

    def make(f: int) -> Faction:
        k = w.faction_name(f) or hex(f)
        return Faction(k, f, can_be_human(w, f), is_human(w, f), k in rebel, len(w.faction_regions(f)),
                       treasury(w, f), dead=is_dead(w, f))

    me = make(F)
    names: dict[int, str] = {F: me.key}
    others: dict[str, Faction] = {}
    mine = relations(w, F)
    for o in mine:
        fo = make(o)
        names[o] = fo.key
        others[fo.key] = fo
    me.rels = {names[o]: r for o, r in mine.items()}
    met = [F] + [fo.ptr for fo in others.values() if me.rels[fo.key].met]
    st = strengths(w, met)
    me.strength = st[F]
    for fo in others.values():
        fo.strength = st.get(fo.ptr, 0)
    wanted = {F} | {fo.ptr for fo in others.values() if fo.human or (fo.major and me.rels[fo.key].met)}
    for fo in others.values():
        if not fo.human and not fo.rebel and not fo.dead and fo.regions and me.rels[fo.key].met:
            fo.rels = {names[o]: r for o, r in relations(w, fo.ptr, wanted).items()}
    return me, others, neighbours_of(w, F)
