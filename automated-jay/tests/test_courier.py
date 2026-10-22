"""The army courier (player decisions 2026-10-21, assist/courier.py): the faction leader's army recruits the playbook
armies' losses and carries them to the front. decide() is pure: one action a turn.

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist.courier import Need, decide

RAT, MAG = "rat", "mag"
yes = lambda want: True
no = lambda want: False


def plan(cargo=None, queued=0, room=19, here=False, needs=(), afford=yes, near="hub", can=(RAT, MAG)):
    return decide(dict(cargo or {}), queued, room, here, list(needs), afford, near, set(can))


def test_waits_for_its_recruits():
    assert plan(queued=3, here=True, needs=[Need(1, "A", {RAT: 3}, 4)]).action == "wait"


def test_parks_in_a_recruiting_province_when_nothing_is_needed():
    assert plan().action == "park" and plan().region == "hub"
    assert plan(here=True).action == "idle"


def test_recruits_what_the_target_still_needs_beyond_its_cargo():
    p = plan(cargo={RAT: 1}, here=True, needs=[Need(1, "A", {RAT: 3, MAG: 2}, 4)])
    assert p.action == "recruit" and p.want == {RAT: 2, MAG: 2}


def test_recruit_capped_by_room_in_template_order():
    p = plan(here=True, room=3, needs=[Need(1, "A", {RAT: 2, MAG: 2}, 4)])
    assert p.want == {RAT: 2, MAG: 1}


def test_delivers_when_it_carries_what_is_needed():
    p = plan(cargo={RAT: 3}, needs=[Need(1, "A", {RAT: 3}, 4)])
    assert p.action == "deliver" and p.target.cqi == 1


def test_no_gold_delivers_what_it_has():
    assert plan(cargo={RAT: 1}, here=True, afford=no, needs=[Need(1, "A", {RAT: 3}, 4)]).action == "deliver"
    assert plan(here=True, afford=no, needs=[Need(1, "A", {RAT: 3}, 4)]).action == "idle"


def test_empty_courier_away_marches_to_recruit():
    p = plan(needs=[Need(1, "A", {RAT: 3}, 4)])
    assert p.action == "march" and p.region == "hub"
    assert plan(near=None, needs=[Need(1, "A", {RAT: 3}, 4)]).action == "idle"


def test_nearest_army_first_then_most_missing():
    p = plan(cargo={RAT: 5}, needs=[Need(1, "far", {RAT: 5}, 9), Need(2, "near", {RAT: 1}, 2),
                                    Need(3, "near2", {RAT: 4}, 2)])
    assert p.target.name == "near2"
