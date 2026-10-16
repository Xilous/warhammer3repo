"""RE helpers for campaign model objects that reference DB records.

DB record strings use a small string object: {vtable 0x1433ce678, u32 len, u32 len, char* text}.
A DB record starts with such a string object for its key, so "record start" = address of that vtable.

  python -X utf8 -m tools.re_model record wh2_main_skv_clan_skryre      # record start + referrers
  python -X utf8 -m tools.re_model link <region_key> <faction_key>       # objects near the region's
                                                                         # referrers that point at an
                                                                         # object referring to the faction
"""
from __future__ import annotations
import struct
import sys

import numpy as np

from bot.sensor import memscan
from bot.sensor.memory import MemorySensor
from tools.re_strings import pointers_to

STRING_VTABLE = 0x1433CE678


def record_start(pm, key: str) -> int | None:
    hits = memscan.scan_bytes(pm, key.encode() + b"\0", private_only=False, limit=60)
    refs = pointers_to(pm, hits)
    for copy, fields in refs.items():
        for f in fields:
            try:
                vt = pm.read_ulonglong(f - 0x10)
                ln = struct.unpack("<II", pm.read_bytes(f - 0x8, 8))
            except Exception:
                continue
            if vt == STRING_VTABLE and ln[0] == len(key):
                return f - 0x10
    return None


def referrers(pm, addr: int) -> list[int]:
    return pointers_to(pm, [addr]).get(addr, [])


def qwords(pm, base: int, size: int) -> np.ndarray:
    return np.frombuffer(pm.read_bytes(base, size), dtype=np.uint64)


def main() -> int:
    m = MemorySensor()
    pm = m.pm
    if sys.argv[1] == "record":
        rec = record_start(pm, sys.argv[2])
        print("record", hex(rec) if rec else None)
        if rec:
            rs = referrers(pm, rec)
            print(len(rs), "referrers:", [hex(r) for r in rs[:40]])
        return 0
    if sys.argv[1] == "link":
        reg = record_start(pm, sys.argv[2])
        fac = record_start(pm, sys.argv[3])
        print("region record", hex(reg), "faction record", hex(fac))
        fac_objs = referrers(pm, fac)
        print(len(fac_objs), "fields refer to the faction record")
        # candidate faction objects: assume the record pointer sits within the first 0x400 of the object
        fac_obj_ranges = [(f - 0x400, f) for f in fac_objs]
        for r in referrers(pm, reg):
            try:
                q = qwords(pm, r - 0x400, 0x800)
            except Exception:
                continue
            for i, v in enumerate(q):
                v = int(v)
                for lo, hi in fac_obj_ranges:
                    if lo <= v <= hi:
                        print(f"region ref {hex(r)}: field at {i * 8 - 0x400:+#x} -> {hex(v)} "
                              f"(faction-record field {hex(hi)}, offset {hi - v:#x} into that object)")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
