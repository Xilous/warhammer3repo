"""Find Lua binding tables in the exe: 8-byte data fields pointing at a method-name string, and the
code pointers stored next to them.

  python -X utf8 -m tools.re_bindings owning_faction adjacent_region_list at_war_with
Uses the on-disk copy of the exe (C:\\Users\\jaymi\\tools\\wh3bin\\Warhammer3.exe, same build).
"""
from __future__ import annotations
import re
import struct
import sys

import numpy as np
import pefile

EXE = r"C:\Users\jaymi\tools\wh3bin\Warhammer3.exe"
BASE = 0x140000000


def main() -> int:
    pe = pefile.PE(EXE, fast_load=True)
    d = open(EXE, "rb").read()
    secs = [(s.Name.rstrip(b"\0").decode(), s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData,
             s.Characteristics) for s in pe.sections]

    def off2va(off):
        for n, v, vs, ro, rs, ch in secs:
            if ro <= off < ro + rs:
                return BASE + v + (off - ro)

    def va2off(va):
        rva = va - BASE
        for n, v, vs, ro, rs, ch in secs:
            if v <= rva < v + max(vs, rs):
                return ro + (rva - v)

    code = [(BASE + v, BASE + v + max(vs, rs)) for n, v, vs, ro, rs, ch in secs if ch & 0x20000000]
    is_code = lambda a: any(lo <= a < hi for lo, hi in code)

    for name in sys.argv[1:]:
        addrs = [off2va(m.start()) for m in re.finditer(re.escape(name.encode()) + rb"\0", d) if d[m.start() - 1] == 0]
        print(f"== {name}: strings at {[hex(a) for a in addrs]}")
        for a in addrs:
            needle = struct.pack("<Q", a)
            for m in re.finditer(re.escape(needle), d):
                if m.start() % 8:
                    continue
                va = off2va(m.start())
                around = [struct.unpack_from("<Q", d, m.start() + k)[0] for k in range(-16, 32, 8)]
                ptrs = [f"{k:+d}:{v:#x}{'(code)' if is_code(v) else ''}" for k, v in zip(range(-16, 32, 8), around)]
                print(f"   ref at {va:#x}  " + "  ".join(ptrs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
