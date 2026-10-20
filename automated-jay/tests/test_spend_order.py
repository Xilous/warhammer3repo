"""The building step's spending order across provinces (player decision 2026-10-20): main building upgrades, the
Reactor line, landmarks, the recruit buildings (capital closest to tier 5 first), then the settlement list's order.

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist import build, gamedata as gd
from assist.buildplan import Action, Building as B, Settlement

MAJOR = "wh2_main_skv_settlement_major"
LANDMARK = "wh2_main_special_hellpit_pits"


def owned(tier, province="p", landmarks=()):
    return NS(model=Settlement("c", True, B(MAJOR, tier), None, [], list(landmarks)), province=province)


def first(chain):
    return gd.chains()[chain][0].key


def act(kind, item, key, cost=1000):
    return Action("c", kind, item, "", 3, cost, 1, key)


def test_value_order():
    o = owned(5, landmarks=[LANDMARK])
    todo = [
        (o, act("construct", "Spy Nests", first("wh2_main_foreign_slot_discovery_skv"))),
        (o, act("construct", "Breeding Pit", first("wh2_main_skv_farm"), 250)),
        (o, act("construct", "Warp-Turbine Plant", first("wh2_main_skv_engineers"))),
        (o, act("construct", "Landmarks", first(LANDMARK), 10000)),
        (o, act("construct", "Warpstone Reactor", first("wh2_main_skv_energy"), 1500)),
        (o, act("upgrade_main", "Main building", first(MAJOR), 12000)),
        (o, act("construct", "Temple of the Horned Rat", first("wh2_main_skv_order"))),
    ]
    got = [a.item for o_, a in sorted(todo, key=lambda t: build.spend_rank(*t))]
    assert got == ["Main building", "Warpstone Reactor", "Landmarks", "Warp-Turbine Plant",
                   "Temple of the Horned Rat", "Breeding Pit", "Spy Nests"]


def test_recruit_buildings_closest_capital_first():
    far, near = owned(3, "a"), owned(5, "b")
    todo = [(far, act("construct", "Equipment Warpforge", first("wh3_dlc29_skv_stormfiends"))),
            (near, act("upgrade", "Warp-Turbine Plant", gd.chains()["wh2_main_skv_engineers"][-1].key)),
            (near, act("construct", "Equipment Warpforge", first("wh3_dlc29_skv_stormfiends")))]
    got = [(o.province, a.item) for o, a in sorted(todo, key=lambda t: build.spend_rank(*t))]
    assert got == [("b", "Equipment Warpforge"), ("b", "Warp-Turbine Plant"), ("a", "Equipment Warpforge")]
