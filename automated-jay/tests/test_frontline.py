"""The no-build rule per settlement (player decision 2026-10-20): an owned settlement next to a region held by a
faction at war with us is blocked; the rest of its province is built as usual.

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist import build


def test_only_the_blocked_settlement_waits(monkeypatch):
    plans = [NS(settlement=NS(name="cap"), actions=[NS(kind="construct", item="Temple")]),
             NS(settlement=NS(name="minor"), actions=[NS(kind="upgrade", item="Pit")])]
    monkeypatch.setattr(build, "plan_province", lambda prov: plans)
    monkeypatch.setattr(build, "spend_rank", lambda o, a: (4, 0, 0))
    cap = NS(region="cap", model="m1", slot_states=[])
    minor = NS(region="minor", model="m2", slot_states=[])
    todo, skipped = build._actions({"p": [cap, minor]}, {"minor": "next to enemy-held x (y)"})
    assert [(o.region, a.item) for o, a, _b in todo] == [("cap", "Temple")]
    assert skipped == [("minor", "next to enemy-held x (y)")]
