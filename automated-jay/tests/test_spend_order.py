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


# ---- saving that never idles gold (player decision 2026-10-20, after the 10-turn simulation)
def plan(gold, net, items):
    """items: (label, rank, cost) in spending order -> (bought, held, saved labels, reserve)."""
    b, bought, held = build.Budget(gold, net), [], []
    for label, rank, cost in items:
        if cost > b.spare():
            if cost <= b.gold:
                held.append(label)
            else:
                b.save(cost, (rank,), label)
            continue
        b.spend(cost)
        bought.append(label)
    return bought, held, [l for _c, _k, l in b.saved], b.reserve()


TURN_25 = [("landmark", 2, 10000), ("warpforge", 3, 8000), ("turbine", 3, 8000), ("temple GP", 4, 1000),
           ("temple CD", 4, 1500), ("temple Z", 4, 2000), ("pit GP", 4, 500), ("pit KD", 4, 1000),
           ("pit CD", 4, 1000), ("scrap KD", 4, 250), ("scrap Z", 4, 1000), ("sentry", 4, 4000)]


def test_turn_25_spends_the_spare_gold_and_keeps_the_landmark_on_time():
    bought, held, saved, reserve = plan(3108, 3779, TURN_25)
    assert saved == ["landmark"]                  # the Warpforge is not reachable within 2 turns after it
    assert bought == ["pit GP"]                   # 666 spare: the landmark still comes in 2 turns
    assert "temple GP" in held and "scrap KD" in held
    assert 3108 - 500 + 2 * 3779 >= 10000 and reserve == 10000 - 2 * 3779


def test_nothing_saved_buys_everything_affordable():
    bought, held, saved, _r = plan(5000, 1000, [("a", 4, 2000), ("b", 4, 2000), ("c", 4, 2000)])
    assert bought == ["a", "b"] and not held and not saved


def test_far_item_is_not_saved_for():
    bought, _h, saved, reserve = plan(1000, 500, [("landmark", 2, 10000), ("pit", 4, 500)])
    assert saved == [] and bought == ["pit"] and reserve == 0


def test_second_saved_item_counts_the_first():
    # a: 6000 - 4000 -> next turn; b: 6000 + 9000 - 4000 = 11000 -> 2 turns of 6000; spare = 4000 + 12000 - 15000
    bought, held, saved, reserve = plan(4000, 6000, [("a", 1, 6000), ("b", 3, 9000), ("pit", 4, 800),
                                                     ("temple", 4, 500)])
    assert saved == ["a", "b"] and bought == ["pit"] and held == ["temple"] and reserve == 3000
