"""Diplomacy for gold (player decisions 2026-10-21): which peace and join-war offers the plan makes, from memory
facts.

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist import diplomacy as d
from bot.sensor.diplomacy import Faction, Rel

PEACE, WAR, MET = Rel(1, 4), Rel(0, 4), 4


def fac(key, major=False, human=False, rebel=False, regions=2, treasury=1000, strength=900, dead=False, **rels):
    return Faction(key, 0, major, human, rebel, regions, treasury, strength, dict(rels), dead)


def world(*others, me_rels=None):
    me = fac("me", major=True, human=True, strength=1000)
    me.rels = {f.key: PEACE for f in others}
    me.rels.update(me_rels or {})
    return me, {f.key: f for f in others}


def plan(me, others, border=()):
    deals, skipped = d.candidates(me, others, set(border))
    return [(x.kind, x.target, x.payer) for x in deals], {(k, m): why for k, m, why in skipped}


def test_join_war_against_a_minor_at_war_with_a_major():
    me, others = world(fac("big", major=True, treasury=5000), fac("small", big=WAR))
    deals, _ = plan(me, others)
    assert deals == [("join_war", "small", "big")]


def test_richest_payer_first():
    me, others = world(fac("a", major=True, treasury=1000), fac("b", major=True, treasury=4000),
                       fac("small", a=WAR, b=WAR))
    deals, _ = plan(me, others)
    assert [p for _k, _m, p in deals] == ["b", "a"]


def test_payers_must_be_met_ai_majors_at_peace_with_me():
    me, others = world(fac("unmet", major=True), fac("human", major=True, human=True), fac("enemy", major=True),
                       fac("minor_payer"), fac("small", unmet=WAR, human=WAR, enemy=WAR, minor_payer=WAR),
                       me_rels={"unmet": Rel(1, 0), "enemy": WAR})
    deals, _ = plan(me, others)
    assert [x for x in deals if x[0] == "join_war"] == []


def test_never_against_treaty_partners_borders_or_other_humans_friends():
    trade, nap, ally = Rel(1, MET | 1), Rel(1, MET | 8), Rel(2, MET)
    me, others = world(fac("big", major=True), fac("friend", major=True, human=True),
                       fac("t", big=WAR), fac("n", big=WAR), fac("a", big=WAR), fac("b", big=WAR),
                       fac("h", big=WAR, friend=Rel(3, 0)),
                       me_rels={"t": trade, "n": nap, "a": ally})
    deals, skipped = plan(me, others, border=["b"])
    assert deals == []
    assert skipped[("join_war", "t")] == skipped[("join_war", "n")] == skipped[("join_war", "a")] == \
        "a treaty with you"
    assert skipped[("join_war", "b")] == "borders your territory"
    assert skipped[("join_war", "h")].startswith("a treaty with")


def test_peace_with_minors_at_war_with_me_not_bordering():
    me, others = world(fac("far"), fac("near"), fac("big", major=True), fac("rebels", rebel=True),
                       fac("friend", major=True, human=True),
                       me_rels={"far": WAR, "near": WAR, "big": WAR, "rebels": WAR, "friend": WAR})
    deals, skipped = plan(me, others, border=["near"])
    assert deals == [("peace", "big", "big"), ("peace", "far", "far")]      # majors too; rebels, humans never
    assert skipped[("peace", "near")] == "borders your territory"


def test_wiped_out_factions_are_dropped():
    me, others = world(fac("big", major=True), fac("gone", dead=True, regions=0, big=WAR),
                       fac("gone_enemy", dead=True, regions=0), fac("horde", regions=0),
                       me_rels={"gone_enemy": WAR, "horde": WAR})
    deals, skipped = plan(me, others)
    assert deals == [("peace", "horde", "horde")]                     # alive without land: still offered peace
    assert not [k for k in skipped if k[1].startswith("gone")]


def test_no_tribute():
    me, others = world(fac("weak", strength=100))
    deals, _ = plan(me, others)
    assert deals == []


def test_join_war_against_weak_majors_only():
    me, others = world(fac("payer", major=True, strength=2000), fac("weak_major", major=True, strength=500, payer=WAR),
                       fac("big_major", major=True, strength=800, payer=WAR))
    deals, _ = plan(me, others)
    assert [x for x in deals if x[0] == "join_war"] == [("join_war", "weak_major", "payer")]


def test_order_peace_then_join_war():
    me, others = world(fac("big", major=True, strength=3000), fac("a", strength=100, big=WAR), fac("z"),
                       me_rels={"z": WAR})
    deals, _ = plan(me, others)
    assert [k for k, _t, _p in deals] == ["peace", "join_war"]


def test_unmet_and_landless_minors_left_out():
    me, others = world(fac("big", major=True), fac("unmet", big=WAR), fac("horde", regions=0, big=WAR),
                       me_rels={"unmet": Rel(1, 0)})
    deals, _ = plan(me, others)
    assert deals == []


def test_one_deal_per_minor_a_turn(monkeypatch, tmp_path):
    me, others = world(fac("big", major=True, strength=2000), fac("small", big=WAR), fac("other", big=WAR))

    class S:
        model = 1

        def read(self):
            return type("St", (), {"turn": 5})()
    w = type("W", (), {"s": S()})()
    monkeypatch.setattr(d, "TRIED_FILE", tmp_path / "t.json")
    monkeypatch.setattr(d, "SETTINGS", tmp_path / "s.json")
    monkeypatch.setattr(d.dip, "read", lambda _w, _F: (me, others, set()))
    d._record(w, d.Deal("peace", "small", "small", 0), "Small: peace: +300 gold")
    deals, skipped = d.plan(w, 1)
    assert [(x.kind, x.target) for x in deals] == [("join_war", "other")]
    assert ("join_war", "small", "a deal with it was made this turn") in skipped
    d.set_on("join_war", "other", False)
    deals, skipped = d.plan(w, 1)
    assert deals == [] and ("join_war", "other", "turned off") in skipped
    d.set_on("join_war", "other", True)
    assert d.load_off()["join_war"] == set()
