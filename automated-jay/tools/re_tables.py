"""Dump a live Lua binding table: consecutive {name*, func*, 0, 0x1_00000000} entries (0x20 bytes each).

  python -X utf8 -m tools.re_tables 0x143d14750 0x143d19950
For each seed address, walks backwards and forwards while entries keep the pattern, printing
name -> function address. Tables found 2026-10-16: region interface around 0x143d14750,
faction interface around 0x143d19950.
"""
from __future__ import annotations
import sys

from bot.sensor.memory import MemorySensor
from tools.re_regions import read_str


def entry(pm, a: int):
    try:
        name_p = pm.read_ulonglong(a)
        func = pm.read_ulonglong(a + 8)
        z = pm.read_ulonglong(a + 16)
    except Exception:
        return None
    if not (0x140000000 <= name_p < 0x150000000 and 0x140000000 <= func < 0x150000000 and z == 0):
        return None
    s = read_str(pm, name_p, 64)
    return (s, func) if s else None


def walk(pm, seed: int) -> list[tuple[int, str, int]]:
    start = seed
    while entry(pm, start - 0x20):
        start -= 0x20
    out = []
    a = start
    while True:
        e = entry(pm, a)
        if not e:
            break
        out.append((a, e[0], e[1]))
        a += 0x20
    return out


def main() -> int:
    m = MemorySensor()
    for s in sys.argv[1:]:
        rows = walk(m.pm, int(s, 16))
        print(f"== table containing {s}: {len(rows)} entries from {hex(rows[0][0]) if rows else '?'}")
        for a, name, func in rows:
            print(f"   {name:45s} {func:#x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
