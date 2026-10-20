import struct

from bot.sensor import turn as T

MODEL, W, TM, R, ARR = 0x100000, 0x200000, 0x300000, 0x400000, 0x500000
FACTION = 0x7DD8B360


class FakePM:
    """Just enough memory for turn_record and the ended list: model -> world -> turn manager -> record R."""

    def __init__(self, mode: int):
        rec = bytearray(0x40)
        struct.pack_into("<IQ", rec, T.LIST_COUNT, 1, ARR)
        struct.pack_into("<I", rec, T.ENDED_COUNT, 1)
        struct.pack_into("<Q", rec, T.ENDED_ARRAY, ARR)
        struct.pack_into("<Q", rec, T.FACTION, FACTION)
        rec[T.MODE] = mode
        self.mem = {MODEL + T.WORLD: struct.pack("<Q", W), W + T.TURN_MANAGER: struct.pack("<Q", TM),
                    TM + T.CURRENT: struct.pack("<Q", R), R: bytes(rec), ARR: struct.pack("<Q", FACTION)}

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
