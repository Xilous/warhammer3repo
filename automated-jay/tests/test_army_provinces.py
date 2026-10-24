"""One army per recruiting province (player, 2026-10-24: local recruitment slots and queue are per province).

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist import army_builder as A


def test_plan_provinces(monkeypatch):
    regions = {"zhufbar": "black_water", "karak_hirn": "peak_pass", "grom": "peak_pass"}
    monkeypatch.setattr(A, "region_provinces", lambda: (regions, {}))
    monkeypatch.setattr(A, "eligible", lambda w, F, need: {"black_water": set(), "peak_pass": set()})
    monkeypatch.setattr(A, "load_automation", lambda: {"army_builder": {"template": {"units": ["x"]}}})
    monkeypatch.setattr(A, "delta", lambda a, _h: NS(missing={"x": 1} if a.needs else {}))
    w = NS(faction_regions=lambda F: list(regions), region_key=lambda r: r)
    # closest free province for a marching army: the first not skipped, in the order given
    monkeypatch.setattr(A, "closest_target",
                        lambda w, F, a, elig, skip=frozenset(): next(((None, p, 1) for p in a.near if p not in skip), None))
    tichit = NS(cqi=1, general_name="Tichit", region="zhufbar", needs=True, near=["black_water"])
    thanquol = NS(cqi=2, general_name="Thanquol", region="zhufbar", needs=True, near=["black_water", "peak_pass"])
    full = NS(cqi=3, general_name="Full", region="karak_hirn", needs=False, near=[])
    plan = A.plan_provinces(w, 0, [tichit, thanquol, full])
    assert plan == {"black_water": "Tichit", "peak_pass": "Thanquol"}     # the second one goes elsewhere
    new = NS(cqi=4, general_name="New", region="zhufbar", needs=True, near=[])
    plan = A.plan_provinces(w, 0, [tichit, new], new)
    assert plan["black_water"] == "New"                                  # the army raised this pass keeps its province
