"""The expanded widget's THIS TURN list shows only what failed and why (player request 2026-10-21).

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist.railpanel import failures


def test_successes_and_planned_waits_are_hidden():
    lines = ["turn 4",
             "rites: Dominating Scheme waits: no complete province yet | verified",
             "tech: researching Harsh Production Quotas | verified",
             "buildings: Karag Dromar: Breeding Pit -> Nest-Nursery | blocked: Oakenhammer | problems: "
             "karag_dromar: Main building needs 2 development points (the province has 0); karag_dromar: "
             "Landmarks needs 5000 gold | verified",
             "army: courier Thanquol: no playbook army is missing units | verified"]
    assert failures(lines) == []


def test_failures_with_their_reasons():
    lines = ["turn 7",
             "tech: nothing queued | verified | MISSED (memory check): no research running, 3 techs left (next: X)",
             "skills: ERROR boom",
             "buildings: done | problems: zhufbar: Scrap Heap not started (the cursor did not register); zhufbar: "
             "Temple needs 900 gold | verified",
             "masterplans: x | verified | not done, with a reason: Essen: should be completed (not possible: notes); "
             "Reekjaw: free, no Steal-Take started (not possible: notes)"]
    got = failures(lines)
    assert "tech — MISSED (memory check): no research running, 3 techs left (next: X)" in got
    assert "skills — ERROR boom" in got
    assert "buildings — zhufbar: Scrap Heap not started (the cursor did not register)" in got
    assert not [g for g in got if "needs 900 gold" in g]
    assert "masterplans — Essen: should be completed (not possible: notes)" in got
    assert len(got) == 5
