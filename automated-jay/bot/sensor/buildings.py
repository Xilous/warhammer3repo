"""Building records and construction costs from memory (player rule 2026-10-19: what a building costs is read from the
game, not the DB price: in a single-player save a Breeding Pit listed at 250 cost 325).

Decoded on 9.0.4, 2026-10-19:
  chain record (vtable 0x1433CE750, one per building chain, found by scanning the DB region that holds them):
      key string object [+8]; levels: u32 +0x84 count, [+0x88] array of level records (in no particular order)
  level record: key string object [+8]; chain record [+0x18]; base cost u32 +0x208 (= building_levels create_cost)
  cost (the construction cost evaluator FUN_1429ccf20, reached from the UI context ConstructInSettlementCost):
      round(base * (1 + (e1 + e2 + e3) / 100)), from the faction's effect table at F+0x1A8 (bot/sensor/world.py
      _effect_value has the layout):
        e1  scope 6, effect 0x5C, no record          every building
        e2  scope 0xD, the chain's id u32 chain+0xC8, record = chain
        e3  scope 0x0E entries naming the level record or its chain (summed)
  Checked live: every base equals the DB price; in the multiplayer campaign of 2026-10-19 no cost effect exists, so
  the cost is the base (what the game charged).
"""
from __future__ import annotations
import struct

import numpy as np

from . import memscan

CHAIN_VTABLE = 0x1433CE750
_CHAINS: dict = {}               # model -> {chain key: chain record}


def _key(w, rec: int) -> str | None:
    from .world import string_object
    try:
        return string_object(w.pm, w.q(rec + 8)) or string_object(w.pm, rec + 8)
    except Exception:
        return None


def chains(w, hint: int | None = None) -> dict[str, int]:
    """{chain key: chain record} for every building chain (scanned once per campaign: about half a second).
    hint: any chain record (a slot's building's [level+0x18]) to find the region by; otherwise the slots are used."""
    m = w.s.model
    if m in _CHAINS:
        return _CHAINS[m]
    if hint is None:
        hint = _any_chain(w)
    out: dict[str, int] = {}
    if hint:
        for r in memscan.regions(w.pm.process_handle):
            if not (r.base <= hint < r.base + r.size):
                continue
            for addr, buf in memscan.read_region(w.pm, r):
                vals = np.frombuffer(buf, dtype=np.uint64, count=len(buf) // 8)
                for i in np.nonzero(vals == CHAIN_VTABLE)[0]:
                    a = addr + int(i) * 8
                    k = _key(w, a)
                    if k:
                        out[k] = a
    _CHAINS.clear()
    _CHAINS[m] = out
    return out


def _any_chain(w) -> int | None:
    from .world import find_player_faction
    F = find_player_faction(w)
    for r in (w.faction_regions(F) if F else []):
        try:
            L = w.q(r + 0x148) + 0x10
            arr = w.q(L + 8)
            for i in range(w.u32(L + 4)):
                sb = w.q(w.q(arr + 8 * i) + 0x190)
                B = w.q(sb + 0x20) if sb else 0
                if B:
                    return w.q(w.q(B + 0x30) + 0x18)
        except Exception:
            continue
    return None


def level_record(w, level_key: str) -> int | None:
    chain = level_key.rsplit("_", 1)[0]
    ch = chains(w).get(chain)
    if not ch:
        return None
    n, arr = w.u32(ch + 0x84), w.q(ch + 0x88)
    for i in range(min(n, 32)):
        rec = w.q(arr + 8 * i)
        if _key(w, rec) == level_key:
            return rec
    return None


def _entries(w, F: int) -> list[tuple[int, int, float]]:
    E = F + 0x1A8
    n, arr = w.u32(E + 4), w.q(E + 8)
    if not 0 < n < 100000:
        return []
    raw = w.pm.read_bytes(arr, 0x20 * n)
    return [(struct.unpack_from("<Q", raw, 0x20 * i)[0], struct.unpack_from("<Q", raw, 0x20 * i + 0x10)[0],
             struct.unpack_from("<f", raw, 0x20 * i + 0x18)[0]) for i in range(n)]


def construction_cost(w, F: int, level_key: str) -> int | None:
    """What the game charges F to build this level now, from memory; None when the record cannot be found."""
    rec = level_record(w, level_key)
    if not rec:
        return None
    try:
        base = w.u32(rec + 0x208)
        ch = w.q(rec + 0x18)
        ents = _entries(w, F)
        k1 = ((6 << 16) | 0x5C) << 40
        k2 = ((0xD << 16) | 0) << 40 | w.u32(ch + 0xC8)
        e1 = sum(v for k, r, v in ents if k == k1 and r == 0)
        e2 = sum(v for k, r, v in ents if k == k2 and r == ch)
        e3 = sum(v for k, r, v in ents if (k >> 56) == 0x0E and r in (rec, ch))
        c = base * (1 + (e1 + e2 + e3) / 100)
        return max(0, int(c + 0.5))
    except Exception:
        return None


RESTRICTIONS = 0x6D10            # model -> the building restrictions manager R (the cm:add_*restricted_building* bindings)


def _rec_keys(w, arr: int, n: int, stride: int, at: int) -> set[str]:
    out = set()
    for i in range(min(n, 4000)):
        try:
            rec = w.q(arr + stride * i + at)
            k = _key(w, rec) if rec else None
            if k:
                out.add(k)
        except Exception:
            continue
    return out


def restricted(w, F: int) -> set[str]:
    """Building level and chain keys the game's scripts have locked for faction F (story and event locks: the
    Morskittar Engine before Thanquol's mission 5, wh_campaign_setup.lua add_event_restricted_building_record_for_
    faction), from memory. Decoded 2026-10-19 (9.0.4) from the bindings:
      add_restricted_building_level_record (FUN_14278f62c): every faction, list at R+0x98 (count +4, [+8] level records)
      add_event_restricted_building_record[_for_faction] (FUN_14278cb10 -> FUN_14278cac4 -> FUN_1427c7df8): R+0x340,
          entries of 0x58 bytes sorted by faction id u32 +0x50 (0 = every faction), each a list (count +0x24,
          [+0x28]) of 0x38-byte records, the level record at +0x30
      add_event_restricted_building_chain_record[_for_faction] (FUN_14278c8ac -> FUN_14278c7bc -> FUN_1427c800c):
          R+0x350, entries of 0x28 bytes sorted by faction id u32 +0x20, each a list (count +4, [+8]) of 0x38-byte
          records, the chain record at +0x30
    Checked live 2026-10-19 (multiplayer, Thanquol): the Morskittar Engine levels 1-5 and the endgame foreign-slot
    buildings listed, the story lock the building popup used to show only as a missing card."""
    out: set[str] = set()
    try:
        R = w.q(w.s.model + RESTRICTIONS)
        if not R:
            return out
        out |= _rec_keys(w, w.q(R + 0x98 + 8), w.u32(R + 0x98 + 4), 8, 0)
        fid = w.u32(F + 8)
        n, arr = w.u32(R + 0x340 + 4), w.q(R + 0x340 + 8)
        for i in range(min(n, 2000)):
            e = arr + 0x58 * i
            if w.u32(e + 0x50) in (0, fid):
                out |= _rec_keys(w, w.q(e + 0x28), w.u32(e + 0x24), 0x38, 0x30)
        n, arr = w.u32(R + 0x350 + 4), w.q(R + 0x350 + 8)
        for i in range(min(n, 2000)):
            e = arr + 0x28 * i
            if w.u32(e + 0x20) in (0, fid):
                out |= _rec_keys(w, w.q(e + 8), w.u32(e + 4), 0x38, 0x30)
    except Exception:
        pass
    return out
