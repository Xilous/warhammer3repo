"""Expected campaign_variables float[1068] in in-memory index order.

Index order = descriptor order (re/cv_globals.json, sorted by address).
Values = the game's DB defaults (tww/db/campaign_variables_tables.json).
A run of these floats is the anchor that locates the campaign model in memory.
"""
from __future__ import annotations
import json
import struct
from functools import lru_cache

from .. import config


@lru_cache(maxsize=1)
def expected_floats() -> tuple[tuple[str, float], ...]:
    globs = json.load(open(config.RE_DIR / "cv_globals.json"))
    names = [globs[k] for k in sorted(globs, key=lambda h: int(h, 16))]
    rows = json.load(open(config.DB_DIR / "campaign_variables_tables.json"))
    byname = {r["variable_key"]: float(r["value"]) for r in rows}
    missing = [n for n in names if n not in byname]
    if missing:
        raise RuntimeError(f"{len(missing)} campaign variables missing from DB dump, e.g. {missing[:3]}")
    assert len(names) == config.CV_COUNT, len(names)
    return tuple((n, byname[n]) for n in names)


def needle(start: int = 0, count: int = 48) -> bytes:
    """Packed float32 bytes for indices [start, start+count): the scan pattern."""
    vals = [v for _, v in expected_floats()[start:start + count]]
    return struct.pack(f"<{len(vals)}f", *vals)


def match_score(blob: bytes) -> tuple[int, list[str]]:
    """How many of the 1068 floats at `blob` match the DB defaults; returns (matches, mismatched names)."""
    exp = expected_floats()
    got = struct.unpack_from(f"<{config.CV_COUNT}f", blob)
    bad = [n for (n, e), g in zip(exp, got) if abs(e - g) > 1e-6 * max(1.0, abs(e))]
    return config.CV_COUNT - len(bad), bad
