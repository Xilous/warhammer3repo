"""The new-army budget counts the upkeep a ticked army will still add, its queued units included.

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist import new_army as N
from bot.sensor.world import Army, Unit

STORMVERMIN = "wh2_main_skv_inf_stormvermin_1"
CANNONS = "wh3_dlc29_skv_mon_stormfiend_ratling_cannons"


def ikit(queued):
    units = [Unit("wh2_dlc12_skv_cha_ikit_claw_0", 1, 1)] + [Unit(STORMVERMIN, 90, 90)] * 6
    return Army(55, "wh2_dlc12_skv_ikit_claw", "Ikit Claw", "r", units, general_id=100, queued=queued)


def pending(monkeypatch, army):
    monkeypatch.setattr(N, "armies", lambda w, F: [army])
    monkeypatch.setattr(N, "enabled_armies", lambda: {55: {"cqi": 55, "name": "Ikit Claw", "general_id": 100}})
    monkeypatch.setattr(N, "load_automation", lambda: {"army_builder": {"template": {
        "lord": ["wh2_dlc12_skv_ikit_claw"], "heroes": {"wh2_main_skv_warlock_engineer": 1},
        "units": {STORMVERMIN: 6, CANNONS: 12}}}})
    import assist.army as A
    monkeypatch.setattr(A, "load_automation", N.load_automation)
    return N.pending_upkeep(None, None)


def test_queued_refill_still_counts(monkeypatch):
    up = N.upkeep_of()
    want = 12 * up[CANNONS] + up[N.ENGINEER_UNIT]
    assert pending(monkeypatch, ikit([])) == want
    assert pending(monkeypatch, ikit([CANNONS] * 12)) == want       # queued: no upkeep paid yet, still to come
