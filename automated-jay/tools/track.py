"""Narrow down a field across game states, like a Cheat Engine 'next scan', by pointer path.

  python -m tools.track new turn 4      # every path (depth<=2 from the model) holding int32 4
  # end a turn in-game
  python -m tools.track next turn 5     # keep only paths that now hold 5
  python -m tools.track show turn       # list survivors with current values

Paths are stored as offset lists and re-resolved each time, so objects that move are followed.
"""
from __future__ import annotations
import argparse
import json
import struct
import sys

import pymem

from bot import config
from bot.sensor.memory import MemorySensor
from tools.trace import MODEL_WINDOW, OBJ_WINDOW, ptrs


def resolve(pm, model: int, path: list[int]) -> int | None:
    addr = model
    try:
        for off in path[:-1]:
            addr = pm.read_ulonglong(addr + off)
            if addr < 0x10000:
                return None
        return pm.read_int(addr + path[-1])
    except pymem.exception.MemoryReadError:
        return None


def collect(pm, model: int, value: int, depth: int) -> list[list[int]]:
    needle = struct.pack("<i", value)
    out: list[list[int]] = []
    seen: set[int] = set()
    frontier = [(model, MODEL_WINDOW, [])]
    for d in range(depth + 1):
        nxt = []
        for addr, size, path in frontier:
            try:
                buf = pm.read_bytes(addr, size)
            except pymem.exception.MemoryReadError:
                continue
            i = buf.find(needle)
            while i != -1:
                if i % 4 == 0:
                    out.append(path + [i])
                i = buf.find(needle, i + 1)
            if d < depth:
                for off, v in ptrs(buf):
                    if v not in seen:
                        seen.add(v)
                        nxt.append((v, OBJ_WINDOW, path + [off]))
        frontier = nxt
    return out


def fmt(path: list[int]) -> str:
    return "model" + "".join(f" -> +{o:#x}" for o in path[:-1]) + f" @ +{path[-1]:#x}"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["new", "next", "show"])
    p.add_argument("tag")
    p.add_argument("value", type=int, nargs="?")
    p.add_argument("--depth", type=int, default=2)
    a = p.parse_args()

    store = config.RUNS_DIR / f"track_{a.tag}.json"
    s = MemorySensor()
    if s.model is None:
        sys.exit("model not located")

    if a.cmd == "new":
        paths = collect(s.pm, s.model, a.value, a.depth)
    else:
        paths = json.load(open(store))
        if a.cmd == "next":
            paths = [p_ for p_ in paths if resolve(s.pm, s.model, p_) == a.value]
    json.dump(paths, open(store, "w"))
    print(f"{len(paths)} candidate paths")
    for p_ in paths[:40]:
        print(f"  {fmt(p_)} = {resolve(s.pm, s.model, p_)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
