"""Army ticks belong to one campaign (2026-10-20): Thanquol has the same cqi and character id in every new campaign, so
a tick also stores the turn and the general's rank, and a campaign behind either is another one.

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist.army import tick_for
from bot.sensor.world import Army

TICK = {111: {"cqi": 111, "name": "Thanquol", "general_id": 213, "turn": 40, "rank": 18}}


def thanquol(turn, rank):
    return Army(111, "wh2_dlc12_skv_thanquol", "Thanquol", "r", [], general_id=213, turn=turn, rank=rank)


def test_same_campaign_later_turn_counts():
    assert tick_for(thanquol(41, 19), TICK)[0]


def test_new_campaign_earlier_turn_is_ignored():
    ok, why = tick_for(thanquol(23, 12), TICK)
    assert not ok and "another campaign" in why


def test_new_campaign_past_the_turn_but_lower_rank_is_ignored():
    assert not tick_for(thanquol(45, 10), TICK)[0]


def test_tick_without_turn_is_ignored():
    old = {111: {"cqi": 111, "name": "Thanquol", "general_id": 213}}
    ok, why = tick_for(thanquol(41, 19), old)
    assert not ok and "tick it again" in why


def test_unknown_turn_and_rank_do_not_drop_a_tick():
    assert tick_for(thanquol(0, 0), TICK)[0]
