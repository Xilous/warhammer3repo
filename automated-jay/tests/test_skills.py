"""Skill orders from the DB alone (no game): the rank a skill opens at, the skill locks, and the generic_lord template
resolved onto a lord's own tree.

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist import skills as S

MENTOR = "wh3_main_skill_all_mentor_lord"


def test_unlocked_at_rank_counts_from_zero():
    # live 2026-10-22: Mentor (unlocked_at_rank 29 / 39 / 49) read "Available at rank 30" on a rank-29 Thanquol
    assert S._rank_locked(29, MENTOR)
    assert not S._rank_locked(30, MENTOR)
    assert S._rank_locked(39, MENTOR, 2) and not S._rank_locked(40, MENTOR, 2)
    assert not S._rank_locked(1, "wh_main_skill_all_lord_campaign_route_marcher")
    assert not S._rank_locked(None, MENTOR)


def test_skill_locks_loaded():
    locks = S._locks()
    # Corruptive and Dictatorial lock each other on every Skaven lord's campaign row
    assert ("wh2_main_skill_skv_campaign_corruptive", 1) in locks["wh2_dlc12_skill_node_skv_ikit_claw_campaign_chain_04"]
    assert ("wh2_main_skill_skv_campaign_dictatorial", 1) in locks["wh2_dlc12_skill_node_skv_ikit_claw_campaign_chain_05"]


def test_generic_lord_takes_the_template_rows():
    o = S.character_orders("generic_lord:wh2_main_skv_warlord")
    assert o["node_set"] == "wh2_main_skill_node_set_skv_warlord"
    names = [i["skill"] for i in o["order"]]
    assert names[:4] == ["Route Marcher", "Inspiring Presence", "Blastmaster", "Engineering Skill"]
    plan = S.attempt_list("generic_lord:wh2_main_skv_warlord")
    keys = [sk for _n, _r, sk in plan]
    # mounts first, in the rank they open (player decision 2026-10-23: taken as they unlock), then asap
    assert keys[:2] == ["wh2_main_skill_skv_warlord_mount_bonebreaker", "wh2_dlc16_skill_skv_warlord_mount_2"]
    assert keys[2] == MENTOR
    assert len(keys) == len(set(keys)) + 2                    # only Lightning Strike and Ancient Cunning come twice


def test_generic_lord_matches_by_name_where_keys_differ():
    o = S.character_orders("generic_lord:wh3_dlc29_skv_schemer_warlord")
    ip = next(i for i in o["order"] if i["skill"] == "Inspiring Presence")
    assert ip["node"]                                         # the schemer's own Inspiring Presence node


def test_template_order_bottom_rows_match_generic():
    # the generic template is a copy of the templates' army and campaign rows (player request 2026-10-22)
    o = S.orders()
    gen = [(i["skill"], i["ranks"]) for i in o["generic_lord"]["order"]]
    ikit = [(i["skill"], i["ranks"]) for i in o["characters"]["ikit_claw"]["order"]]
    assert gen == ikit
