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


def test_complication_pool_from_game_data():
    # the settlement level's pool gives the same Alarm odds the older rule used (q_by_alarm) ...
    for lvl, q2 in ((0, 0.086), (4, 0.152)):
        cs = M.complications(lvl, [], 1260.0, 10)
        assert abs(sum(p for p, _a, _l in cs) - 1) < 1e-9
        assert abs(sum(p for p, a, _l in cs if 2 + a >= 4) - q2) < 0.001
        assert abs(sum(p for p, a, _l in cs if 3 + a >= 4) - 0.99) < 0.001
    # ... and the loot a Complication takes: 50% of the region's income in Warpstone at worst, 2,000-4,000 gold
    cs = M.complications(4, [], 1260.0, 10)
    assert min(l for _p, _a, l in cs) < -620
    assert sum(p * l for p, _a, l in cs) < -50
    # a card drawn already comes no more
    gone = M.complications(4, ["wh3_dlc29_economy_red_alarm_warpstone_3"], 1260.0, 10)
    assert len(gone) == len(cs) - 1
    assert M.complications(4, [], None, 10) == []        # a share of income cannot be valued without the income


FINDOL_BAG = [("wh3_dlc29_economic_green_basic_treasury_gdp_small_5", 25.8), ("wh3_dlc29_economic_green_basic_treasury_gdp_large_5", 3.2),
              ("wh3_dlc29_economic_green_skryre_warpstone_3", 19.4), ("wh3_dlc29_economic_green_skryre_treasury_3", 19.4),
              ("wh3_dlc29_economic_green_basic_warpstone_gdp_small_5", 25.8), ("wh3_dlc29_economic_green_basic_warpstone_gdp_large_5", 6.4)]


def test_stay_or_exit_counts_the_loot_a_complication_takes():
    # Steal-Take at Thanquol's Halls of Findol, turn 77 (memory, runs/masterplans.jsonl): Alarm 2, Risk 100%, loot
    # 1,461 Warpstone; staying adds ~225, but the Complication that comes takes ~88 and maxes Alarm 15% of the time.
    # The older rule (Alarm only) waited here.
    b = board(alarm=2, risk=100, gold=3927.0, warpstone=1068.0, draws=1, bag=FINDOL_BAG, income=1122.0, level=4,
              drawn_cards=[])
    assert M.decide({k: v for k, v in b.items() if k != "level"}, CFG)[0] == "wait"          # the older rule
    assert M.decide(b, CFG)[0] == "complete"
    assert M.decide(dict(b, risk=60), CFG)[0] == "wait"                    # a Complication less likely: stay
    assert M.decide(dict(b, alarm=3), CFG)[0] == "complete"
    assert M.decide(dict(b, alarm=1), CFG)[0] == "wait"                     # one Complication cannot max Alarm


def test_shop_order_is_known_to_the_game():
    cfg = json.load(open(M.STRATEGY, encoding="utf-8"))
    chains, tabs = M.shop_chains(), M.shop_tabs()
    for e in cfg["shop"]["order"]:
        assert e["chain"] in chains and e["chain"] in tabs, e["chain"]
        assert 1 <= e["levels"] <= len(chains[e["chain"]]), e["chain"]
    keys = {e["chain"] for e in cfg["shop"]["order"]}
    assert not any("verminlord" in k or "final_battle" in k for k in keys)   # Great-Smart and final battle: out of scope



def test_income_from_memory_wins_over_card_text():
    assert abs(M.expected_gain(board(income=160.0, effects=[]), CFG) - 13.248) < 0.01


def test_alarm_max_from_memory():
    assert M.decide(board(alarm=3, alarm_max=3), CFG)[0] == "complete"


def test_shop_plan_strict_order_and_locks():
    objs = M.shop_objects()
    racks = "wh3_dlc29_shop_military_green_skryre_warpfire_throwers"          # Warlock Master's tab, 300
    assert objs[racks][0]["cost"] == 300
    cfg = {"keep_warpstone": 50, "order": [{"chain": racks, "levels": 1, "_what": "Racks"}]}
    warlock = {"wh3_dlc29_skv_schemer_warlock_master"}
    assert M.shop_plan(cfg, 1000, set(), set())[0] == []                       # Underling locked: skipped
    buys, _why = M.shop_plan(cfg, 1000, set(), warlock)
    assert [(c, lv, cost) for c, lv, cost, _n in buys] == [(racks, 0, 300)]
    assert M.shop_plan(cfg, 340, set(), warlock)[1].startswith("saving for Racks")   # 340 - 300 < 50
    assert M.shop_plan(cfg, 1000, {objs[racks][0]["token"]}, warlock)[0] == []         # owned already


def test_targets_ranked_by_income():
    """2026-10-22: Varenka Hills (200/turn) was taken over Karaz-a-Karak (900/turn); the score is the region's income,
    owners not at war first, and only our own provinces are skipped (a bordering one is a target)."""
    import struct
    from types import SimpleNamespace as NS
    import bot.sensor.world as world
    regs = {"kak": 1, "varenka": 2, "foe": 3, "mine": 4, "home": 5}
    gdp = {1: 900, 2: 200, 3: 2000, 4: 500, 5: 700}
    owner = {1: 10, 2: 11, 3: 12, 4: 99, 5: 13}
    w = NS(wars=lambda F: [12], region_owner=lambda r: owner[r], explored=lambda F, r: True,
           slots=lambda r: [NS(building="b", level=1)], pm=NS(read_bytes=lambda a, n: struct.pack("<i", gdp[a - 0x10C])))
    saved = (M._region_objects, M._own_provinces, world.region_provinces)
    M._region_objects, M._own_provinces = (lambda w, F: regs), (lambda w, F: {"P_HOME"})
    world.region_provinces = lambda: ({"home": "P_HOME", "mine": "P_HOME"},)
    try:
        sc = M.target_scores(w, 99, NS(plans=[], region_cooldowns={}), {})
    finally:
        M._region_objects, M._own_provinces, world.region_provinces = saved
    assert sorted(sc, key=lambda k: -sc[k]) == ["kak", "varenka", "foe"]      # foe: richest, but at war
    assert sc["kak"] - sc["varenka"] == 700


def test_shop_tab_counts_lines_not_levels():
    """2026-10-22, turn 38: Grey Seer tab with Warlord Clan's Tunnel II and Superior Rats is 2 purchases (lines), so
    Rictus Miners' Holes (needs 3) is locked; buying a new line's first level opens it."""
    tunnel, rats = "wh3_dlc29_military_mod_pool_clanrats_grey_seer_3", "wh3_dlc29_military_action_skill_grey_seer_draw_units_2"
    rictus = "wh3_dlc29_shop_economic_green_rictus_warpstone"
    pusbags = "wh3_dlc29_shop_military_green_basic_pusbags"
    seer = {"wh3_dlc29_skv_schemer_grey_seer"}
    cfg = {"keep_warpstone": 0, "order": [{"chain": rictus, "levels": 1}]}
    assert M.shop_plan(cfg, 5000, {tunnel, rats}, seer)[0] == []
    cfg["order"].insert(0, {"chain": pusbags, "levels": 1})
    assert [b[0] for b in M.shop_plan(cfg, 5000, {tunnel, rats}, seer)[0]] == [pusbags, rictus]


def _offer(chain, tab, listed=True, level=0, unlocked=True, blocked=False):
    from bot.sensor.masterplans import ShopLine
    lv = M.shop_objects()[chain]
    return ShopLine(chain, tab, listed, lv[level]["key"] if listed else None, lv[level]["needed"], unlocked, blocked)


def test_shop_follows_the_memory_offer():
    """2026-10-22, turn 53: Warp-Grinders (a DLC unit not owned) was not offered in the Warlock tab; with the offer read
    from memory it is skipped and the next line bought, and the game's own unlocked answer is used."""
    grinders, drillers = "wh3_dlc29_shop_military_green_warp_grinders_dlc", "wh3_dlc29_shop_economic_green_skryre_warpstone"
    tab = "wh3_dlc29_skv_shop_warlock"
    warlock = {"wh3_dlc29_skv_schemer_warlock_master"}
    owned = {"wh3_dlc29_military_mod_pool_skryre_warpfire_throwers_1"}
    cfg = {"keep_warpstone": 0, "order": [{"chain": grinders, "levels": 1}, {"chain": drillers, "levels": 3}]}
    assert [b[0] for b in M.shop_plan(cfg, 5000, owned, warlock)[0]] == [grinders, drillers, drillers, drillers]
    offered = ({grinders: _offer(grinders, tab, listed=False, blocked=True), drillers: _offer(drillers, tab)}, {tab: 1})
    assert [(b[0], b[1]) for b in M.shop_plan(cfg, 5000, owned, warlock, offered)[0]] == \
        [(drillers, 0), (drillers, 1), (drillers, 2)]
    # the level on offer is the game's (Veteran Drillers next), and its lock is the game's answer
    offered = ({drillers: _offer(drillers, tab, level=1)}, {tab: 1})
    assert [b[1] for b in M.shop_plan(cfg, 5000, owned, warlock, offered)[0]] == [1, 2]
    offered = ({drillers: _offer(drillers, tab, level=1, unlocked=False)}, {tab: 1})
    assert M.shop_plan(cfg, 5000, owned, warlock, offered)[0] == []


def test_shop_line_bought_earlier_in_the_pass_opens_a_lock():
    """Grey Seer tab at 4 lines: Pox-Cauldron Offering (needs 5) is locked now, opened by Testing Grounds (a new line)
    bought before it in the same pass."""
    pusbags, poxes = "wh3_dlc29_shop_military_green_basic_pusbags", "wh3_dlc29_shop_military_action_skill_spawn_cauldron_poxes"
    tab, seer = "wh3_dlc29_skv_shop_grey_seer", {"wh3_dlc29_skv_schemer_grey_seer"}
    cfg = {"keep_warpstone": 0, "order": [{"chain": poxes, "levels": 1}, {"chain": pusbags, "levels": 1},
                                          {"chain": poxes, "levels": 1}]}
    offered = ({pusbags: _offer(pusbags, tab), poxes: _offer(poxes, tab, unlocked=False)}, {tab: 4})
    assert [b[0] for b in M.shop_plan(cfg, 5000, set(), seer, offered)[0]] == [pusbags, poxes]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
