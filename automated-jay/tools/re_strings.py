"""RE helper: where does a key string live, and what points at it?

  python -X utf8 -m tools.re_strings wh3_main_combi_region_tobaro
Prints each heap copy of the exact string (NUL-terminated), then every 8-byte field pointing at
that copy (depth 1), then fields pointing at those holders' starts (depth 2, objects that own
a record pointer), with nearby printable strings for context.
"""
from __future__ import annotations
import struct
import sys

import numpy as np

from bot.sensor import memscan
from bot.sensor.memory import MemorySensor
from tools.re_regions import strings_in


def pointers_to(pm, targets: list[int], limit: int = 2000) -> dict[int, list[int]]:
    """target -> heap addresses of 8-byte aligned fields whose value equals target (numpy scan)."""
    tarr = np.array(sorted(set(targets)), dtype=np.uint64)
    out: dict[int, list[int]] = {t: [] for t in targets}
    total = 0
    for r in memscan.regions(pm.process_handle):
        if r.type != memscan.MEM_PRIVATE:
            continue
        for addr, buf in memscan.read_region(pm, r):
            n = len(buf) // 8
            if n == 0:
                continue
            vals = np.frombuffer(buf, dtype=np.uint64, count=n)
            idx = np.nonzero(np.isin(vals, tarr))[0]
            for i in idx:
                out[int(vals[i])].append(addr + int(i) * 8)
                total += 1
            if total > limit:
                return out
    return out


def main() -> int:
    key = sys.argv[1]
    m = MemorySensor()
    pm = m.pm
    hits = memscan.scan_bytes(pm, key.encode() + b"\0", private_only=False, limit=40)
    hits = [h for h in hits if pm.read_bytes(h - 1, 1)[0] == 0 or not chr(pm.read_bytes(h - 1, 1)[0]).isalnum()]
    print(f"{len(hits)} copies of {key!r}: {[hex(h) for h in hits[:12]]}")
    refs = pointers_to(pm, hits)
    for h, rs in refs.items():
        if not rs:
            continue
        print(f"copy {hex(h)}: {len(rs)} pointers")
        for r in rs[:8]:
            ctx = strings_in(pm, r - 0x40, 0x80)
            print(f"   field {hex(r)}  ctx: " + "; ".join(f"{o - 0x40:+#x} {s[:40]}" for o, s in ctx[:5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
