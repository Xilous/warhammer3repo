"""The building step's spending order across provinces (player decisions 2026-10-20, 2026-10-21): main building and
port upgrades, then every other building by how soon it pays for itself (income growth first).

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


def test_main_first_then_fastest_payback():
    """Player decisions 2026-10-21: income growth decides the order. Main building (and port) upgrades first (they
    unlock the slots every income building needs), then every other building by how soon it pays for itself; what
    adds no gold (this landmark) comes last and is still built."""
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
    ranked = sorted(todo, key=lambda t: build.spend_rank(*t))
    got = [a.item for o_, a in ranked]
    assert got[0] == "Main building" and got[-1] == "Landmarks"
    turns = [build.spend_rank(*t)[1] for t in ranked[1:]]
    assert turns == sorted(turns)
    assert got[1] == "Breeding Pit"                              # 250 gold for 80 a turn: about 4 turns


def test_recruit_buildings_compete_on_payback():
    o = owned(5)
    cheap = (o, act("construct", "Breeding Pit", first("wh2_main_skv_farm"), 250))
    forge = (o, act("construct", "Equipment Warpforge", first("wh3_dlc29_skv_stormfiends"), 4000))
    assert [a.item for _o, a in sorted([forge, cheap], key=lambda t: build.spend_rank(*t))] ==         ["Breeding Pit", "Equipment Warpforge"]


# ---- saving that never idles gold (player decision 2026-10-20, after the 10-turn simulation)
def plan(gold, net, items):
    """items: (label, rank, cost) in spending order -> (bought, held, saved labels, reserve)."""
    b, bought, held = build.Budget(gold, net), [], []
    for label, rank, cost in items:
        if cost > b.spare():
            if cost <= b.gold:
                held.append(label)
            else:
                b.save(cost, rank if isinstance(rank, tuple) else (rank,), label)
            continue
        b.spend(cost)
        bought.append(label)
    return bought, held, [l for _c, _k, l in b.saved], b.reserve()


# ranks as spend_rank makes them: (0,) main upgrade, (1, payback turns) the rest; slow payback (> 20) is never saved for
SLOW = (1, 60.0)
TURN_25 = [("main", (0,), 10000), ("warpforge", (1, 15.0), 8000), ("turbine", (1, 16.0), 8000),
           ("temple GP", SLOW, 1000), ("temple CD", SLOW, 1500), ("temple Z", SLOW, 2000), ("pit GP", SLOW, 500),
           ("pit KD", SLOW, 1000), ("pit CD", SLOW, 1000), ("scrap KD", SLOW, 250), ("scrap Z", SLOW, 1000),
           ("sentry", SLOW, 4000)]


def test_turn_25_spends_the_spare_gold_and_keeps_the_saved_item_on_time():
    bought, held, saved, reserve = plan(3108, 3779, TURN_25)
    assert saved == ["main"]                      # the Warpforge is not reachable within 2 turns after it
    assert bought == ["pit GP"]                   # 666 spare: the landmark still comes in 2 turns
    assert "temple GP" in held and "scrap KD" in held
    assert 3108 - 500 + 2 * 3779 >= 10000 and reserve == 10000 - 2 * 3779


def test_nothing_saved_buys_everything_affordable():
    bought, held, saved, _r = plan(5000, 1000, [("a", SLOW, 2000), ("b", SLOW, 2000), ("c", SLOW, 2000)])
    assert bought == ["a", "b"] and not held and not saved


def test_far_item_is_not_saved_for():
    bought, _h, saved, reserve = plan(1000, 500, [("main", (0,), 10000), ("pit", SLOW, 500)])
    assert saved == [] and bought == ["pit"] and reserve == 0


def test_second_saved_item_counts_the_first():
    # a: 6000 - 4000 -> next turn; b: 6000 + 9000 - 4000 = 11000 -> 2 turns of 6000; spare = 4000 + 12000 - 15000
    bought, held, saved, reserve = plan(4000, 6000, [("a", (0,), 6000), ("b", (1, 12.0), 9000), ("pit", SLOW, 800),
                                                     ("temple", SLOW, 500)])
    assert saved == ["a", "b"] and bought == ["pit"] and held == ["temple"] and reserve == 3000


def test_slow_payback_is_never_saved_for():
    _b, _h, saved, _r = plan(100, 5000, [("fast", (1, 8.0), 4000), ("slow", SLOW, 4000)])
    assert saved == ["fast"]


def test_replacing_an_off_list_building_comes_right_after_main_upgrades():
    o = owned(5)
    rep = (o, act("replace", "Breeding Pit", first("wh2_main_skv_farm"), 250))
    pit = (o, act("construct", "Scrap Heap", first("wh2_main_skv_industry"), 250))
    main = (o, act("upgrade_main", "Main building", first(MAJOR), 12000))
    got = [a.kind for _o, a in sorted([pit, rep, main], key=lambda t: build.spend_rank(*t))]
    assert got == ["upgrade_main", "replace", "construct"]
