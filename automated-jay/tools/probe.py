"""Find the campaign model in the running game and a static pointer to it.

  python -m tools.probe            # scan, report, write anchors.json (keeps existing field offsets)

Steps:
  1. attach to Warhammer3.exe
  2. heap-scan for the first 48 campaign_variables defaults (float32, index order)
  3. for each hit, score the full 1068-float array and derive candidate object bases
     (hit - 0x5be8 = campaign model, hit - 0x18cd4 = autoresolver engine)
  4. scan the exe's data sections for 8-byte pointers into [base - 0x4000, base]
     -> patch-stable static anchors (module offset), written to anchors.json
"""
from __future__ import annotations
import json
import sys
import time

from bot import config
from bot.sensor import memscan, cvtable


def main() -> int:
    t0 = time.time()
    pm, base, size = memscan.attach(config.PROCESS_NAME)
    print(f"attached pid={pm.process_id} base={hex(base)} size={hex(size)}")

    nd = cvtable.needle(0, 48)
    hits = memscan.scan_bytes(pm, nd, private_only=True, limit=16)
    print(f"needle hits: {len(hits)}  ({time.time()-t0:.1f}s)")
    if not hits:
        print("no campaign_variables array found: is a campaign loaded?")
        return 1

    cands = []
    for h in hits:
        blob = pm.read_bytes(h, config.CV_COUNT * 4)
        ok, bad = cvtable.match_score(blob)
        print(f"  array @ {hex(h)}  match {ok}/{config.CV_COUNT}  mismatched: {bad[:6]}")
        for label, off in (("model", config.CV_OFFSET_MODEL), ("engine", config.CV_OFFSET_ENGINE)):
            cands.append((label, h - off, h, ok))

    anchors = {}
    if config.ANCHORS_FILE.exists():
        anchors = json.load(open(config.ANCHORS_FILE))
    anchors.setdefault("fields", {})
    anchors["build_note"] = "9.0; offsets from re/NOTES.md"
    anchors["candidates"] = []

    for label, obj, arr, ok in cands:
        ptrs = memscan.scan_pointers_in_module(pm, base, size, obj - 0x4000, obj)
        exact = [(a, v) for a, v in ptrs if v == obj]
        near = [(a, v) for a, v in ptrs if v != obj]
        print(f"{label} candidate base {hex(obj)} (array {hex(arr)}): "
              f"{len(exact)} exact static ptrs, {len(near)} pointing just below")
        for a, v in exact[:8]:
            print(f"    exact  module+{hex(a-base)}  -> {hex(v)}")
        for a, v in near[:8]:
            print(f"    near   module+{hex(a-base)}  -> {hex(v)}  (obj-{hex(obj-v)})")
        anchors["candidates"].append({
            "label": label, "object": hex(obj), "array": hex(arr), "match": ok,
            "static_exact": [hex(a - base) for a, v in exact],
            "static_near": [[hex(a - base), hex(obj - v)] for a, v in near[:16]],
        })
        if label == "model" and exact and "model_static_ptr_offset" not in anchors:
            anchors["model_static_ptr_offset"] = exact[0][0] - base
            anchors["model_last_heap"] = obj

    json.dump(anchors, open(config.ANCHORS_FILE, "w"), indent=2)
    print(f"wrote {config.ANCHORS_FILE}  ({time.time()-t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
