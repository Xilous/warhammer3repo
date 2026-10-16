"""Find the campaign camera in memory by panning it with the keyboard and watching which floats move.

  python -X utf8 -m tools.re_camera X Y          # X, Y = a world point currently near the screen centre

Candidates: float3 (a, h, c) on the heap with a ~ X, c ~ Y (the eye/target layout the game's
get_camera_position reads: x at +0, y at +8). The camera is panned east with D, then back with A;
survivors are the floats that moved east and came back.
"""
from __future__ import annotations
import sys
import time

import numpy as np
import pydirectinput

from bot.focus import game_focus
from bot.sensor import memscan
from bot.sensor.memory import MemorySensor

WIN = 60.0


def snapshot_candidates(pm, X: float, Y: float) -> list[int]:
    out = []
    for r in memscan.regions(pm.process_handle):
        if r.type != memscan.MEM_PRIVATE or r.size > 1 << 28:
            continue
        for addr, buf in memscan.read_region(pm, r):
            n = len(buf) // 4
            if n < 3:
                continue
            f = np.frombuffer(buf, dtype=np.float32, count=n)
            with np.errstate(invalid="ignore"):
                m = (np.abs(f[:-2] - X) < WIN) & (np.abs(f[2:] - Y) < WIN) & (f[1:-1] > -50) & (f[1:-1] < 2000)
            for i in np.nonzero(m)[0]:
                out.append(addr + int(i) * 4)
            if len(out) > 400_000:
                return out
    return out


def read3(pm, addrs: list[int]) -> np.ndarray:
    vals = np.full((len(addrs), 3), np.nan, dtype=np.float32)
    for k, a in enumerate(addrs):
        try:
            vals[k] = np.frombuffer(pm.read_bytes(a, 12), dtype=np.float32)
        except Exception:
            pass
    return vals


def hold(key: str, secs: float) -> None:
    pydirectinput.keyDown(key)
    time.sleep(secs)
    pydirectinput.keyUp(key)
    time.sleep(0.8)


def main() -> int:
    X, Y = float(sys.argv[1]), float(sys.argv[2])
    m = MemorySensor()
    pm = m.pm
    t0 = time.time()
    cands = snapshot_candidates(pm, X, Y)
    print(f"{len(cands)} candidates ({time.time() - t0:.0f}s)")
    v0 = read3(pm, cands)
    with game_focus():
        hold("d", 0.6)
    v1 = read3(pm, cands)
    with game_focus():
        hold("a", 0.6)
    v2 = read3(pm, cands)
    dx1 = v1[:, 0] - v0[:, 0]
    dx2 = v2[:, 0] - v1[:, 0]
    dy1 = v1[:, 2] - v0[:, 2]
    keep = np.nonzero((np.abs(dx1) > 1.0) & (np.abs(dx2) > 1.0) & (np.sign(dx1) != np.sign(dx2)) & (np.abs(dy1) < np.abs(dx1)))[0]
    print(f"{len(keep)} moved east and back")
    # group by (value before, move): the camera eye and target move by exactly the same amount
    groups: dict = {}
    for k in keep:
        if not (0 < v0[k][1] < 2000 and abs(v0[k][1]) > 1e-3):
            continue
        key = (round(float(dx1[k]), 2), round(float(v0[k][0]), 2), round(float(v0[k][1]), 2), round(float(v0[k][2]), 2))
        groups.setdefault(key, []).append(cands[k])
    for key, addrs in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:25]:
        print(f"  dx {key[0]:+.2f}  value ({key[1]}, {key[2]}, {key[3]})  x{len(addrs)}  e.g. {[hex(a) for a in addrs[:4]]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
