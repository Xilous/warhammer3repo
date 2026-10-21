"""The End Turn button's QUEUED comes from the runner's state, not from the wording of a status (2026-10-20)."""
from types import SimpleNamespace

from assist.rail import TurnRail


def rail():
    r = SimpleNamespace(view={}, press_seq=0, pending_press=0, end_wait=False, draw=lambda: None)
    r._derive = lambda: TurnRail._derive(r)
    return r


def press(r):
    r.press_seq += 1
    r.pending_press = r.press_seq
    r._derive()


def test_press_shows_queued_until_the_runner_acks_it():
    r = rail()
    press(r)
    assert r.end_wait
    TurnRail.set_view(r, {"ver": 1, "owed": False, "ack": 0})     # an older state: the press is not handled yet
    assert r.end_wait
    TurnRail.set_view(r, {"ver": 2, "owed": False, "ack": 1})     # handled, nothing owed (refused or done)
    assert not r.end_wait


def test_queued_follows_what_the_runner_owes():
    r = rail()
    press(r)
    TurnRail.set_view(r, {"ver": 1, "owed": True, "ack": 1})      # handled and queued: the spinner stays
    assert r.end_wait
    TurnRail.set_view(r, {"ver": 2, "owed": False, "ack": 1})     # the turn ended / the request went
    assert not r.end_wait


def test_status_wording_no_longer_sets_queued():
    r = rail()
    r.state = r.headline = r.sub = ""
    TurnRail.set_status(r, "waiting", "END TURN QUEUED (turn 3)", "queued")
    assert not r.end_wait                                         # only the runner's state does
