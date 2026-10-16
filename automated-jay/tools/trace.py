"""Forward pointer search from the campaign model to a value visible on screen.

  python -m tools.trace 10901              # int32 and float32, up to 2 pointer hops
  python -m tools.trace 10901 --depth 3

Walks pointers out of the model window (and out of each object they hit), reads a
fixed-size block at each target, and reports every path whose block contains the value:
  model+0x1a0 -> +0x38 -> +0x2c4 = 10901 (i32)
Fast: only touches objects actually reachable from the model.
"""
from __future__ import annotations
import argparse
import struct
import sys

import pymem

from bot.sensor.memory import MemorySensor

MODEL_WINDOW = 0x8000
OBJ_WINDOW = 0x1000
HEAP_LO, HEAP_HI = 0x10000, 0x7FF0_0000_0000


def ptrs(buf: bytes) -> list[tuple[int, int]]:
    n = len(buf) // 8
    return [(i * 8, v) for i, v in enumerate(struct.unpack_from(f"<{n}Q", buf))
            if HEAP_LO <= v < HEAP_HI and v % 8 == 0 and not (0x140000000 <= v < 0x14F000000)]


def find(buf: bytes, value: int) -> list[tuple[int, str]]:
    out = []
    for fmt, tag in (("<i", "i32"), ("<f", "f32")):
        needle = struct.pack(fmt, value if tag == "i32" else float(value))
        i = buf.find(needle)
        while i != -1:
            if i % 4 == 0:
                out.append((i, tag))
            i = buf.find(needle, i + 1)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("value", type=int)
    p.add_argument("--depth", type=int, default=2)
    a = p.parse_args()

    s = MemorySensor()
    if s.model is None:
        sys.exit("model not located")
    pm = s.pm
    seen: set[int] = set()
    frontier = [(s.model, MODEL_WINDOW, "model")]
    found = 0
    for depth in range(a.depth + 1):
        nxt = []
        for addr, size, path in frontier:
            try:
                buf = pm.read_bytes(addr, size)
            except pymem.exception.MemoryReadError:
                continue
            for off, tag in find(buf, a.value):
                print(f"  {path}+{off:#x} = {a.value} ({tag})")
                found += 1
            if depth < a.depth:
                for off, v in ptrs(buf):
                    if v not in seen:
                        seen.add(v)
                        nxt.append((v, OBJ_WINDOW, f"{path}+{off:#x} ->"))
        print(f"depth {depth}: scanned {len(frontier)} blocks, {found} hits so far", file=sys.stderr)
        frontier = nxt
        if len(frontier) > 200_000:
            print("frontier too large, stopping", file=sys.stderr)
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
