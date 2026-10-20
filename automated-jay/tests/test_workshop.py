"""Ikit's Forbidden Workshop: the planned Warp-Turbine line counts for workshop level 2 (2026-10-20), so no temporary
Construction Cavern is built while a managed settlement plans the chain, and a planned Cavern is never held back.

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist import workshop as W

CAVERN = "wh2_main_skv_engineers_1"


class FakeWorld:
    def faction_name(self, F):
        return W.SKRYRE


def slot(building=None, constructing=False):
    return NS(building=building, constructing=constructing, type="secondary", active=True, level=1)


def settlement(region, province, slots, capital):
    return NS(region=region, province=province, slot_states=[slot("main")] + slots, capital=capital)


def run(monkeypatch, tmp_path, models, planned, state=None, turn=10):
    monkeypatch.setattr(W, "STATE", tmp_path / "workshop.json")
    monkeypatch.setattr(W, "workshop_level", lambda w, F: 1)
    if state is not None:
        W._save(state)
    return W.plan(FakeWorld(), 1, models, {}, turn, planned=planned)


def test_no_temporary_cavern_while_planned(monkeypatch, tmp_path):
    cap = settlement("cap", "p1", [slot(), slot()], True)
    minor = settlement("min", "p1", [slot()], False)
    protected, target, note = run(monkeypatch, tmp_path, {"p1": [cap, minor]}, planned=lambda o: o.capital)
    assert target is None and note is None and not protected


def test_temporary_cavern_still_built_when_not_planned(monkeypatch, tmp_path):
    minor = settlement("min", "p1", [slot()], False)
    _p, target, _n = run(monkeypatch, tmp_path, {"p1": [minor]}, planned=lambda o: False)
    assert target is not None and target[0] is minor


def test_chosen_but_unstarted_slot_is_dropped(monkeypatch, tmp_path):
    cap = settlement("cap", "p1", [slot()], True)
    minor = settlement("min", "p1", [slot("wh2_main_skv_farm_2")], False)
    state = {"cavern": {"at": "min:1", "turn": 9, "faction": None}}
    _p, target, _n = run(monkeypatch, tmp_path, {"p1": [cap, minor]}, planned=lambda o: o.capital, state=state)
    assert target is None and "cavern" not in W._load()


def test_planned_cavern_is_not_held_back_but_counts(monkeypatch, tmp_path):
    cap = settlement("cap", "p1", [slot(CAVERN)], True)
    models = {"p1": [cap]}
    protected, target, _n = run(monkeypatch, tmp_path, models, planned=lambda o: o.capital, turn=10)
    assert not protected and target is None                     # free to upgrade to Warp-Forge at once
    run(monkeypatch, tmp_path, models, planned=lambda o: o.capital, turn=11)
    assert W._load().get("met") is True


def test_temporary_cavern_is_still_held_back(monkeypatch, tmp_path):
    minor = settlement("min", "p1", [slot(CAVERN)], False)
    protected, _t, _n = run(monkeypatch, tmp_path, {"p1": [minor]}, planned=lambda o: False)
    assert ("min", 1) in protected
