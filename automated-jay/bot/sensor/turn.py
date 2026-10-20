"""Whose turn it is, from memory: the faction(s) the campaign is currently running a turn for.

Decoded from the game's own Lua bindings (9.0.4, exe binding tables, disassembled 2026-10-17):

  model:turn_number()          [[model+0x6CB0]+0x08] + 1      (+0x10 holds the same number: the turn counter)
  model:world()                [model+0x6CA0] = world W
  world:whose_turn_is_it()     0x1426e9f38 on [W+0x310]
  model:is_player_turn()       0x1426ba85c([W+0x310], local faction)
  world:is_factions_turn_by_key(k)   0x1426ba85c([W+0x310], faction k)

  T = [W+0x310] (turn manager), R = [T+0x120] (current turn record):
    byte R+0x38 == 0: one faction at a time, the faction object at [R+0x30]
    byte R+0x38 == 1: simultaneous turns (multiplayer), the factions in the list u32 R+4 (count), [R+8] (array)

`is_factions_turn` is 0x1426ba85c: the same test the game's scripts make. Cheap (five reads), so it can be polled.
"""
from __future__ import annotations
import struct

WORLD = 0x6CA0           # model -> world
TURN_MANAGER = 0x310     # world -> turn manager
CURRENT = 0x120          # turn manager -> current turn record
MODE = 0x38              # byte in the record: 0 one faction, 1 simultaneous list
FACTION = 0x30           # record -> faction object (mode 0)
LIST_COUNT, LIST_ARRAY = 0x4, 0x8   # record -> faction list (mode 1)
MAX_LIST = 64


def _q(pm, a: int) -> int:
    return struct.unpack("<Q", pm.read_bytes(a, 8))[0]


def turn_record(pm, model: int) -> int | None:
    """The current turn record R, or None when it cannot be read (no campaign, loading)."""
    try:
        w = _q(pm, model + WORLD)
        if w < 0x10000:
            return None
        t = _q(pm, w + TURN_MANAGER)
        if t < 0x10000:
            return None
        r = _q(pm, t + CURRENT)
        return r if r >= 0x10000 else None
    except Exception:
        return None


def whose_turn(pm, model: int) -> list[int] | None:
    """Faction objects whose turn it is (one, outside simultaneous multiplayer). None when unreadable."""
    r = turn_record(pm, model)
    if r is None:
        return None
    try:
        b = pm.read_bytes(r, 0x40)
    except Exception:
        return None
    mode = b[MODE]
    if mode == 0:
        f = struct.unpack_from("<Q", b, FACTION)[0]
        return [f] if f >= 0x10000 else []
    if mode == 1:
        n = struct.unpack_from("<I", b, LIST_COUNT)[0]
        arr = struct.unpack_from("<Q", b, LIST_ARRAY)[0]
        if not 0 <= n <= MAX_LIST or (n and arr < 0x10000):
            return None
        try:
            raw = pm.read_bytes(arr, 8 * n) if n else b""
        except Exception:
            return None
        return list(struct.unpack(f"<{n}Q", raw))
    return None


def is_factions_turn(pm, model: int, faction: int) -> bool | None:
    """True when the campaign is running `faction`'s turn now, False when another faction's, None when unreadable."""
    w = whose_turn(pm, model)
    if w is None:
        return None
    return faction in w


def players_turn(s) -> tuple[bool | None, str]:
    """Is the campaign running the player's faction's turn now? (MemorySensor s; the player's faction is the one
    world.find_player_faction finds, matched by name so no faction pointer has to be cached across saves.)
    -> (True, ""), (False, "<faction key> is moving"), or (None, why) when it cannot be read."""
    from .world import World, local_faction, player_faction_key
    model = s.model
    if model is None:
        return None, "no campaign loaded"
    who = whose_turn(s.pm, model)
    if who is None:
        return None, "whose turn it is cannot be read"
    w = World(s)
    lf = local_faction(w)                      # this PC's faction, any faction (world.local_faction, 2026-10-19)
    want = w.faction_name(lf) if lf else player_faction_key(w)
    if want is None:
        return None, "the player's faction cannot be read"
    names = [w.faction_name(f) or hex(f) for f in who]
    if want in names:
        return True, ""
    return False, f"{names[0] if names else 'nobody'} is moving"


ENDED_COUNT, ENDED_ARRAY = 0x10, 0x18   # record -> factions that have ended this turn (multiplayer)


def ended_factions(pm, model: int) -> list[int] | None:
    """Faction objects that pressed End Turn in the current turn record (simultaneous multiplayer turns: the
    factions whose turn runs stay listed at R+4/R+8 until everyone has ended). u32 R+0x10 count, [R+0x18] array of
    faction pointers. Found 2026-10-19 by diffing memory as the player's ready tick came on (R+0x10 0 -> 1, +0x14
    capacity 0 -> 1, +0x18 the array), then checked against the ticks for a whole turn: Clan Scruten listed the
    moment the player ended, Clan Skryre when the friend did, the list gone with the record when the AI started.
    Only meaningful in a simultaneous record (MODE 1): with one faction at a time, End Turn passes the turn on at
    once, and the list is stale (single player 2026-10-19, turn 2: mode 0, the list still held Clan Scruten from
    turn 1, and the assistant waited for 'the other players' forever). [] there. None when unreadable."""
    r = turn_record(pm, model)
    if r is None:
        return None
    try:
        if pm.read_bytes(r + MODE, 1)[0] != 1:
            return []
        n = struct.unpack("<I", pm.read_bytes(r + ENDED_COUNT, 4))[0]
        if n == 0:
            return []
        if n > MAX_LIST:
            return None
        arr = _q(pm, r + ENDED_ARRAY)
        out = list(struct.unpack(f"<{n}Q", pm.read_bytes(arr, 8 * n)))
        # a list that is not a set of this turn's factions is stale, not read (multiplayer 2026-10-19, turn 29: 8
        # entries at the turn's start, The Tormentors twice and three non-factions, Clan Scruten among them, and the
        # assistant waited for 'the other players' while nobody had ended): unreadable, the ready ticks decide
        if len(set(out)) != len(out) or not set(out) <= set(whose_turn(pm, model) or ()):
            return None
        return out
    except Exception:
        return None


def local_ended(s) -> bool | None:
    """The local player has pressed End Turn this turn (memory: their faction is in ended_factions). None when it
    cannot be read."""
    from .world import World, local_faction
    model = s.model
    if model is None:
        return None
    w = World(s)
    F = local_faction(w)
    e = ended_factions(s.pm, model)
    if F is None or e is None:
        return None
    return F in e


def waiting_for(s) -> list[str] | None:
    """Factions whose turn still runs and that have not ended (multiplayer: the other players being waited for),
    as faction keys. None when it cannot be read."""
    from .world import World
    model = s.model
    who, e = whose_turn(s.pm, model), ended_factions(s.pm, model)
    if who is None or e is None:
        return None
    w = World(s)
    return [w.faction_name(f) or hex(f) for f in who if f not in e]
