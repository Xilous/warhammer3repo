"""The widget's plain words (assist/widget_data.py; redesign approved by the player 2026-10-24).

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist import widget_data as W

RC = "wh3_dlc29_skv_mon_stormfiend_ratling_cannons"
MC = "wh3_dlc29_skv_art_warp_doom_magma_cannon"
WT = "wh2_main_skv_inf_warpfire_thrower"
ENG = "wh2_main_skv_warlock_engineer"


def test_steps_plain_with_state():
    rows = W.steps(["turn 67", "tech: researching Murder Dissenters | verified",
                    "buildings: ERROR row is off screen | verification redid: 5 built; then verified",
                    "rites: Thirteenth Scheme waits: the rites' global cooldown | verified"])
    assert [(r["name"], r["state"]) for r in rows] == [("Tech", "done"), ("Buildings", "failed"), ("Rites", "wait")]
    assert rows[0]["text"] == "Researching Murder Dissenters"


def test_needs_from_a_decision_and_a_failure():
    n = W.needs("paused", "DECISION NEEDED (turn 67)", "the other factions' turns are held until you answer: "
                "waiting for you: an AI diplomacy offer (diplomacy_dropdown)\nautomations run when it is closed",
                ["popup_x"], [{"name": "Buildings", "text": "a row was off screen"}])
    assert n[0]["title"] == "An AI diplomacy offer is open" and "other factions wait" in n[0]["text"]
    assert n[1]["ignore"] == "popup_x" and n[2]["title"] == "Buildings failed"
    assert W.needs("your turn", "YOUR TURN 67", "") == []


def test_bar_line_order():
    need = [{"title": "An AI diplomacy offer is open", "text": "The other factions wait."}]
    prog = [{"name": "Thanquol", "now": "Marching to Zhufbar."}]
    assert W.bar_line("automating", "", need, prog).startswith("Hands off")
    assert W.bar_line("paused", "", need, prog).startswith("An AI diplomacy offer")
    assert W.bar_line("your turn", "", [], prog, "Next build: X in 1 turn(s).") == \
        "Thanquol: Marching to Zhufbar. Next build: X in 1 turn(s)."


def test_next_build():
    assert W.next_build(["buildings: 2 built | saving for Wurtbad: Warp-Turbine Plant (in 1 turn(s)), 15 gold now"]) \
        == "Next build: Wurtbad: Warp-Turbine Plant in 1 turn(s)."


def test_army_card_composition(monkeypatch):
    monkeypatch.setattr("assist.army.load_automation", lambda: {"army_builder": {"template": {
        "lord": [], "heroes": {ENG: 1}, "units": {RC: 12, MC: 6}}}, "armies": {}})
    monkeypatch.setattr("assist.army.enabled_armies", lambda *a, **k: {})
    monkeypatch.setattr("assist.army.tick_for", lambda a, t: (a.cqi == 1, ""))
    monkeypatch.setattr(W, "_where", lambda a: "Kemperbad (Wissenland)")
    monkeypatch.setattr(W, "unit_label", lambda k: {RC: "Ratling Cannons", MC: "Magma-Cannons", WT: "Warpfire"}.get(k, k))
    units = [NS(key="wh3_dlc29_skv_cha_thanquol")] + [NS(key=RC)] * 8 + [NS(key=MC)] * 6 + [NS(key=WT)] * 2
    army = NS(cqi=1, general_name="Thanquol", units=units, queued=[RC, RC], region="r")
    d = NS(missing={RC: 2}, disband=[WT, WT], heroes_missing={}, matches=False, lord_ok=True)
    card = W.army_cards([(army, d, (True, ""))])[0]
    assert card["size"] == "17 + 2 queued / 20" and card["ticked"]
    got = {u["unit"]: (u["count"], u["state"]) for u in card["units"]}
    assert got["Ratling Cannons"] == ("8 / 12  (+2 queued)", "short")
    assert got["Magma-Cannons"] == ("6 / 6", "ok")
    assert got["Warlock Engineer"] == ("1 / 1", "ok")
    assert got["Warpfire (not in the playbook)"] == ("2", "extra")
    assert card["status"].startswith("Missing 2 Ratling Cannons.")
