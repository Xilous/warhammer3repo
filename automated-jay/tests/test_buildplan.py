"""Checks the settlement planner against the player's rules and the game's own data.

    python -X utf8 -m pytest tests -q      (or: python -X utf8 tests/test_buildplan.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist import gamedata as gd
from assist.buildplan import Building as B, Settlement, Province, plan_province, strategy, chain_for, final_layout, final_slot_count

MAJOR, MINOR, PORT = "wh2_main_skv_settlement_major", "wh2_main_skv_settlement_minor", "wh2_main_skv_port"
SB = "wh2_main_special_settlement_skavenblight"


def names(plan):
    return [t.name for t in plan.layout]


def test_strategy_chains_exist_and_are_skaven():
    for e in strategy()["priority"]:
        for kind in ("capital", "minor"):
            c = chain_for(e, kind)
            if c:
                assert c in gd.chains(), c
                assert c in gd.skaven_chains(), c


def test_tier_caps_from_game_data():
    assert gd.main_max_index(MAJOR) == 5 and gd.main_max_index(MINOR) == 3
    assert gd.slots_at(MAJOR, 5) == 7 and gd.slots_at(MINOR, 3) == 3 and gd.slots_at(SB, 5) == 12


def test_minor_settlement_caps_at_tier_3_and_skips_reactor():
    p = plan_province(Province("p", [Settlement("m", False, B(MINOR, 3), None, [None, None, None])]))[0]
    assert names(p) == ["Breeding Pit", "Scrap Heap", "Overseer's Lookout"]


def test_capital_layout_in_priority_order_without_landmark():
    p = plan_province(Province("p", [Settlement("c", True, B(MAJOR, 5), None, [None] * 7)]))[0]
    assert names(p) == ["Warpstone Reactor", "Breeding Pit", "Scrap Heap", "Temple of the Horned Rat",
                        "Clan Armoury", "Equipment Warpforge", "Chained Sentry Beasts"]


def test_port_capital_with_landmark_runs_out_before_warpforge():
    p = plan_province(Province("p", [Settlement("c", True, B(MAJOR, 5), B(PORT, 3), [None] * 6,
                                                ["wh2_main_special_hellpit_pits"])]))[0]
    assert names(p)[-1] == "Clan Armoury" and "Equipment Warpforge" not in names(p)


def test_one_armoury_per_province_goes_to_capital_first():
    plans = plan_province(Province("p", [
        Settlement("m", False, B(MINOR, 3), None, [None] * 3),
        Settlement("c", True, B(MAJOR, 5), None, [None] * 7),
    ]))
    by = {pl.settlement.name: names(pl) for pl in plans}
    assert "Clan Armoury" in by["c"] and "Clan Armoury" not in by["m"]


def test_existing_armoury_in_minor_is_kept_and_not_duplicated():
    plans = plan_province(Province("p", [
        Settlement("c", True, B(MAJOR, 5), None, [None] * 7),
        Settlement("m", False, B(MINOR, 1), None, [B("wh2_main_skv_clanrats", 0)]),
    ]))
    by = {pl.settlement.name: names(pl) for pl in plans}
    assert "Clan Armoury" not in by["c"]


def test_main_building_upgrade_comes_first():
    p = plan_province(Province("p", [Settlement("c", True, B(MAJOR, 2), None, [None, None])]))[0]
    assert p.actions[0].kind == "upgrade_main"


def test_nothing_built_above_current_tier():
    p = plan_province(Province("p", [Settlement("c", True, B(MAJOR, 2), None, [None, None])]))[0]
    for a in p.actions:
        if a.kind in ("construct", "upgrade"):
            assert "Arcane Generators" not in a.detail


def test_off_plan_building_is_replaced_by_the_planned_one():
    # player rule 2026-10-17 (automation.json buildings.off_list_buildings "replace"): an off-list building in a
    # managed province is demolished for the planned building, no OK asked
    p = plan_province(Province("p", [Settlement("m", False, B(MINOR, 3), None,
                                                [B("wh2_main_skv_farm", 2), B("wh2_main_skv_industry", 2),
                                                 B("wh2_main_skv_assassins", 0)])]))[0]
    rep = [a for a in p.actions if a.kind == "replace"]
    assert rep and rep[0].detail.startswith("demolish Hidden Lair, build")


def test_thanquol_landmarks():
    from bot.sensor import world
    keep = world.PLAYER["key"]
    try:
        world.PLAYER["key"] = "wh3_dlc29_skv_clan_scruten"
        assert gd.landmarks_for_region("wh3_main_combi_region_zhufbar") == ["wh3_dlc29_skv_special_morskittar_engine"]
        assert "wh3_dlc29_special_thanquol_scruten_hq" in gd.landmarks_for_region("wh3_main_combi_region_karag_dromar")
        world.PLAYER["key"] = "wh2_main_skv_clan_skryre"          # the engine is Clan Scruten's only
        assert gd.landmarks_for_region("wh3_main_combi_region_zhufbar") == []
    finally:
        world.PLAYER["key"] = keep


def test_skavenblight_landmark_names():
    lm = gd.landmarks_for_region("wh3_main_combi_region_skavenblight")
    got = {gd.level_name(gd.chains()[c][-1].key) for c in lm}
    assert {"Warpstone Tractor Beam", "Council Chamber of the Thirteen", "The Shattered Tower"} <= got


if __name__ == "__main__":
    fails = 0
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            try:
                f()
                print("ok  ", k)
            except AssertionError as ex:
                fails += 1
                print("FAIL", k, ex)
    sys.exit(1 if fails else 0)


def test_standing_landmark_keeps_its_slot_and_is_upgraded():
    # Thanquol's Karag Dromar (2026-10-17): a minor settlement whose three secondary slots the list would fill before
    # "Landmarks"; the Grey Seer Lair already standing there stays in the plan and is upgraded
    from bot.sensor import world
    keep = world.PLAYER["key"]
    try:
        world.PLAYER["key"] = "wh3_dlc29_skv_clan_scruten"
        hq = "wh3_dlc29_special_thanquol_scruten_hq"
        s = Settlement("Karag Dromar", False, B(MINOR, 1), None, [B(hq, 0), None, None],
                       gd.landmarks_for_region("wh3_main_combi_region_karag_dromar"))
        layout = final_layout(s, lambda c, st: True)
        assert hq in [t.chain for t in layout]
        assert len(layout) == final_slot_count(s)
    finally:
        world.PLAYER["key"] = keep
