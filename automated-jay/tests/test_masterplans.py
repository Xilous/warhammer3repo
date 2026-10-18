"""Checks the Steal-Take completion rule and the Masterplans data it reads.

    python -X utf8 -m pytest tests -q      (or: python -X utf8 tests/test_masterplans.py)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist import masterplans as M

CFG = {"gold_per_warpstone": 10, "q_by_alarm": [0.0, 0.0, 0.15, 0.99], "max_alarm_pay": 0.25, "at_max_alarm": "complete"}
BAG = [("wh3_dlc29_economic_green_basic_treasury_gdp_small_1", 44.0),
       ("wh3_dlc29_economic_green_basic_warpstone_gdp_small_1", 44.0),
       ("wh3_dlc29_economic_green_basic_warpstone_gdp_large_1", 5.0),
       ("wh3_dlc29_economic_green_basic_treasury_gdp_large_1", 5.0)]
INCOME_LINE = "10% of the region's income will be added to the Masterplan's reward (+16)"   # Mount Gunbad, turn 18


def board(**kw):
    b = {"risk": 60.0, "alarm": 0, "gold": 32.0, "warpstone": 0.0, "draws": 2, "bag": BAG, "drawn": 2,
         "effects": [INCOME_LINE], "can_complete": True}
    b.update(kw)
    return b


def test_income_from_a_drawn_card():
    assert M.region_income([INCOME_LINE]) == 160


def test_card_values_from_game_data():
    v = M.card_values()
    assert v["wh3_dlc29_economic_green_basic_treasury_gdp_small_1"]["gold_pct"] == 10
    assert v["wh3_dlc29_economic_green_basic_warpstone_gdp_large_1"]["warpstone_pct"] == 20
    assert v["wh3_dlc29_economic_green_skryre_warpstone_1"]["warpstone"] == 150        # Clan Skryre Drillers


def test_expected_gain():
    # 2 draws x (0.44 x 1.6 + 0.44 x 8 + 0.05 x 32 + 0.05 x 16) Warpstone, income 160, 10 gold = 1 Warpstone
    assert abs(M.expected_gain(board(), CFG) - 13.248) < 0.01


def test_low_alarm_always_waits():
    for a in (0, 1):
        assert M.decide(board(alarm=a, risk=100, warpstone=5000), CFG)[0] == "wait"


def test_alarm_3_completes_on_a_big_pot():
    assert M.decide(board(alarm=3, risk=40, warpstone=400), CFG)[0] == "complete"


def test_alarm_3_waits_on_a_small_pot_and_low_risk():
    assert M.decide(board(alarm=3, risk=10, warpstone=5), CFG)[0] == "wait"


def test_alarm_2_waits_unless_the_pot_dwarfs_the_gain():
    assert M.decide(board(alarm=2, risk=60, warpstone=40), CFG)[0] == "wait"
    assert M.decide(board(alarm=2, risk=95, warpstone=2000), CFG)[0] == "complete"


def test_max_alarm_and_not_ready():
    assert M.decide(board(alarm=4), CFG)[0] == "complete"
    assert M.decide(board(alarm=4), dict(CFG, at_max_alarm="abandon"))[0] == "abandon"
    assert M.decide(board(can_complete=False, alarm=3, risk=100, warpstone=999), CFG)[0] == "wait"


def test_shop_order_is_known_to_the_game():
    cfg = json.load(open(M.STRATEGY, encoding="utf-8"))
    chains, tabs = M.shop_chains(), M.shop_tabs()
    for e in cfg["shop"]["order"]:
        assert e["chain"] in chains and e["chain"] in tabs, e["chain"]
        assert 1 <= e["levels"] <= len(chains[e["chain"]]), e["chain"]
    keys = {e["chain"] for e in cfg["shop"]["order"]}
    assert not any("verminlord" in k or "final_battle" in k for k in keys)   # Great-Smart and final battle: out of scope



def test_near_provinces():
    prov = {"a1": "A", "a2": "A", "b1": "B", "c1": "C", "d1": "D"}
    nbrs = {"a1": ["a2", "b1"], "a2": ["a1", "c1"], "b1": ["a1", "d1"], "c1": ["a2"]}
    # we hold a1 only: province A is ours (a2 too), B and C border it, D borders only B
    assert M.near_provinces(prov, nbrs, {"a1"}) == {"A", "B", "C"}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
