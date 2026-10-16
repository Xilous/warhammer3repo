"""RE helper: find the player's faction object and the region objects that point to it.

  python -X utf8 -m tools.re_regions faction       # faction object + string pointers inside it
  python -X utf8 -m tools.re_regions owners        # heap objects holding a pointer to the faction,
                                                   # with nearby strings (looking for region keys)
"""
from __future__ import annotations
import struct
import sys

import pymem

from bot.sensor import memscan
from bot.sensor.memory import MemorySensor


def read_str(pm, addr: int, n: int = 96) -> str | None:
    try:
        b = pm.read_bytes(addr, n)
    except Exception:
        return None
    end = b.find(b"\0")
    if end <= 3:
        return None
    s = b[:end]
    if all(32 <= c < 127 for c in s):
        return s.decode()
    return None


def strings_in(pm, base: int, size: int) -> list[tuple[int, str]]:
    """(offset, text) for every 8-byte field that points at a printable C string, or at a pointer to one."""
    out = []
    try:
        buf = pm.read_bytes(base, size)
    except Exception:
        return out
    for i in range(0, size - 7, 8):
        v = struct.unpack_from("<Q", buf, i)[0]
        if not (0x10000 < v < 0x7FF000000000):
            continue
        s = read_str(pm, v)
        if s:
            out.append((i, s))
            continue
        try:
            v2 = pm.read_ulonglong(v)
        except Exception:
            continue
        if 0x10000 < v2 < 0x7FF000000000:
            s2 = read_str(pm, v2)
            if s2:
                out.append((i, "*" + s2))
    return out


def main() -> int:
    m = MemorySensor()
    pm = m.pm
    a = pm.read_ulonglong(m.model + 0x7F0)
    fac = pm.read_ulonglong(a + 0x20)
    print(f"model {hex(m.model)}  [+0x7f0]={hex(a)}  faction? {hex(fac)}  treasury {pm.read_int(fac + 0x270)}")
    if sys.argv[1:] == ["faction"]:
        for off, s in strings_in(pm, fac, 0x1000):
            print(f"  fac+{off:#x}: {s[:90]}")
        for off, s in strings_in(pm, a, 0x200):
            print(f"  A+{off:#x}: {s[:90]}")
        return 0
    if sys.argv[1:] == ["owners"]:
        needle = struct.pack("<Q", fac)
        hits = memscan.scan_bytes(pm, needle, private_only=True, limit=4000)
        print(f"{len(hits)} heap fields point at the faction")
        shown = 0
        for h in hits:
            near = strings_in(pm, h - 0x200, 0x400)
            regs = [(o - 0x200, s) for o, s in near if "region" in s]
            if regs:
                print(f"  hit {hex(h)}: " + "; ".join(f"{o:+#x} {s[:60]}" for o, s in regs[:4]))
                shown += 1
                if shown > 60:
                    break
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
