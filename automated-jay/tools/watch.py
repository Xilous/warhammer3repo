"""Poor man's Cheat Engine, anchored to the campaign model.

  python -m tools.watch snap A          # snapshot a window around the model as runs/snap_A.bin
  python -m tools.watch snap B          # ... after ending a turn / spending gold
  python -m tools.watch diff A B        # int32 fields that changed, with the model-relative offset
  python -m tools.watch diff A B --eq 7 # ...and whose new value equals 7 (e.g. the turn you see on screen)
  python -m tools.watch find 12345      # int32 fields currently equal to 12345 (e.g. the treasury on screen)

Once an offset is confirmed, put it in anchors.json under "fields": {"turn": <off>, "treasury": <off>}.
Only offsets for things visible on screen belong there.
"""
from __future__ import annotations
import argparse
import json
import struct
import sys

from bot import config
from bot.sensor.memory import MemorySensor

WINDOW_BEFORE = 0x1000
WINDOW_AFTER = 0x20000


def model_window(sensor: MemorySensor) -> tuple[int, bytes]:
    if sensor.model is None:
        sys.exit("campaign model not located; run tools.probe first or load a campaign")
    start = sensor.model - WINDOW_BEFORE
    return start, sensor.pm.read_bytes(start, WINDOW_BEFORE + WINDOW_AFTER)


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snap"); s.add_argument("tag")
    d = sub.add_parser("diff"); d.add_argument("a"); d.add_argument("b"); d.add_argument("--eq", type=int)
    f = sub.add_parser("find"); f.add_argument("value", type=int)
    a = p.parse_args()

    config.RUNS_DIR.mkdir(exist_ok=True)
    sensor = MemorySensor()
    print(f"model @ {hex(sensor.model) if sensor.model else None}")

    if a.cmd == "snap":
        start, buf = model_window(sensor)
        (config.RUNS_DIR / f"snap_{a.tag}.bin").write_bytes(buf)
        json.dump({"start": start, "model": sensor.model}, open(config.RUNS_DIR / f"snap_{a.tag}.json", "w"))
        print(f"snapshot {a.tag}: {len(buf)} bytes from {hex(start)}")
        return 0

    if a.cmd == "find":
        start, buf = model_window(sensor)
        n = len(buf) // 4
        for i, v in enumerate(struct.unpack_from(f"<{n}i", buf)):
            if v == a.value:
                print(f"  model{start + i*4 - sensor.model:+#x}  = {v}")
        return 0

    A = (config.RUNS_DIR / f"snap_{a.a}.bin").read_bytes()
    B = (config.RUNS_DIR / f"snap_{a.b}.bin").read_bytes()
    meta = json.load(open(config.RUNS_DIR / f"snap_{a.a}.json"))
    model = meta["model"]; start = meta["start"]
    n = min(len(A), len(B)) // 4
    ia = struct.unpack_from(f"<{n}i", A); ib = struct.unpack_from(f"<{n}i", B)
    shown = 0
    for i in range(n):
        if ia[i] != ib[i] and (a.eq is None or ib[i] == a.eq):
            print(f"  model{start + i*4 - model:+#x}  {ia[i]} -> {ib[i]}")
            shown += 1
            if shown >= 200:
                print("  ... (truncated)"); break
    print(f"{shown} changed int32 fields")
    return 0


if __name__ == "__main__":
    sys.exit(main())
