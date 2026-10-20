import struct

from bot.sensor import turn as T

MODEL, W, TM, R, ARR, TURN_ARR = 0x100000, 0x200000, 0x300000, 0x400000, 0x500000, 0x600000
FACTION, FRIEND = 0x7DD8B360, 0x7DD8C000


class FakePM:
    """Just enough memory for turn_record and the ended list: model -> world -> turn manager -> record R.
    The turn runs for `turn` (simultaneous: both players); `ended` have pressed End Turn."""

    def __init__(self, mode: int, turn=(FACTION, FRIEND), ended=(FACTION,)):
        rec = bytearray(0x40)
        struct.pack_into("<IQ", rec, T.LIST_COUNT, len(turn), TURN_ARR)
        struct.pack_into("<I", rec, T.ENDED_COUNT, len(ended))
        struct.pack_into("<Q", rec, T.ENDED_ARRAY, ARR)
        struct.pack_into("<Q", rec, T.FACTION, FACTION)
        rec[T.MODE] = mode
        self.mem = {MODEL + T.WORLD: struct.pack("<Q", W), W + T.TURN_MANAGER: struct.pack("<Q", TM),
                    TM + T.CURRENT: struct.pack("<Q", R), R: bytes(rec),
                    ARR: struct.pack(f"<{len(ended)}Q", *ended), TURN_ARR: struct.pack(f"<{len(turn)}Q", *turn)}

    def read_bytes(self, a: int, n: int) -> bytes:
        for base, data in self.mem.items():
            if base <= a and a + n <= base + len(data):
                return data[a - base:a - base + n]
        raise OSError(hex(a))


def test_ended_list_read_in_simultaneous_turns():
    assert T.ended_factions(FakePM(mode=1), MODEL) == [FACTION]


def test_ended_list_ignored_when_one_faction_moves_at_a_time():
    # single player 2026-10-19: mode 0, the list still held the player's faction from the turn before
    assert T.ended_factions(FakePM(mode=0), MODEL) == []


def test_everyone_ended_is_last_turns_list():
    # multiplayer 2026-10-20, turn 3: both players still listed from turn 2, nobody's ready tick on
    assert T.ended_factions(FakePM(mode=1, ended=(FACTION, FRIEND)), MODEL) is None
