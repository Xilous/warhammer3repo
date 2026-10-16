"""Validate region/faction offsets decoded from the Lua bindings, starting from a region record.

  python -X utf8 -m tools.re_region_probe wh3_main_combi_region_tobaro
"""
from __future__ import annotations
import struct
import sys

from bot.sensor.memory import MemorySensor
from tools.re_model import record_start, referrers
from tools.re_regions import read_str

R_NAME, R_OWNER, R_SETTLEMENT, R_ADJ_N, R_ADJ, R_PROVINCE = 0x80, 0x120, 0x128, 0x8C, 0x90, 0x3A8
F_REGIONS_N, F_REGIONS, F_WARS, F_DIPLO, F_HUMAN = 0xF3C, 0xF40, 0xDB8, 0xD88, 0x1BC4


def rec_key(pm, rec: int) -> str | None:
    """A DB record starts with a string object {vtable, u32 len, u32 len, char*}."""
    try:
        return read_str(pm, pm.read_ulonglong(rec + 0x10), 120)
    except Exception:
        return None


def region_key(pm, r: int) -> str | None:
    try:
        return rec_key(pm, pm.read_ulonglong(r + R_NAME))
    except Exception:
        return None


def neighbours(pm, r: int) -> list[int]:
    n = struct.unpack("<I", pm.read_bytes(r + R_ADJ_N, 4))[0]
    if not 0 < n < 40:
        return []
    arr = pm.read_ulonglong(r + R_ADJ)
    return list(struct.unpack(f"<{n}Q", pm.read_bytes(arr, 8 * n)))


def owner(pm, r: int) -> int | None:
    o = pm.read_ulonglong(r + R_OWNER)
    return pm.read_ulonglong(o + 0x10) if o else None


def main() -> int:
    key = sys.argv[1]
    m = MemorySensor()
    pm = m.pm
    rec = record_start(pm, key)
    print("record", hex(rec))
    for ref in referrers(pm, rec):
        r = ref - R_NAME
        try:
            nb = neighbours(pm, r)
        except Exception:
            continue
        names = [region_key(pm, x) for x in nb]
        if nb and all(names):
            print(f"REGION OBJECT {hex(r)}: neighbours {names}")
            f = owner(pm, r)
            print(f"   owner faction object {hex(f) if f else None}")
            if f:
                n = struct.unpack("<I", pm.read_bytes(f + F_REGIONS_N, 4))[0]
                arr = pm.read_ulonglong(f + F_REGIONS)
                regs = [pm.read_ulonglong(pm.read_ulonglong(arr + 8 * i)) for i in range(min(n, 50))]
                print(f"   faction regions ({n}): {[region_key(pm, x) for x in regs]}")
                print(f"   is_human byte {pm.read_bytes(f + F_HUMAN, 1)[0]}  diplo {hex(pm.read_ulonglong(f + F_DIPLO))}")
                wl = pm.read_ulonglong(f + F_WARS)
                if wl:
                    cnt = struct.unpack("<I", pm.read_bytes(wl + 4, 4))[0]
                    base = pm.read_ulonglong(wl + 8)
                    print(f"   war list entries {cnt}")
                    for i in range(min(cnt, 40)):
                        e = base + 0x78 * i
                        other = pm.read_ulonglong(e + 0x28)
                        flag = struct.unpack("<i", pm.read_bytes(pm.read_ulonglong(e + 0x30) + 0x20, 4))[0]
                        # other faction's first region name as a hint
                        on = struct.unpack("<I", pm.read_bytes(other + F_REGIONS_N, 4))[0]
                        hint = None
                        if 0 < on < 500:
                            oa = pm.read_ulonglong(other + F_REGIONS)
                            hint = region_key(pm, pm.read_ulonglong(pm.read_ulonglong(oa)))
                        print(f"      #{i} other {hex(other)} flag {flag} regions {on} e.g. {hint}")
            for x, nm in zip(nb, names):
                o = owner(pm, x)
                print(f"   neighbour {nm}: owner {hex(o) if o else None}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
