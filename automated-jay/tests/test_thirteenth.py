"""The Thirteenth Scheme rule (player rule 2026-10-24): cast while another Skaven clan we know of is alive, never when
the Dominating Scheme comes off cooldown within the 5-turn global cooldown a cast starts.

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist import rites as R

DOM = "wh3_main_ritual_skv_ascendancy_verminlord"


def test_thirteenth_waits(monkeypatch):
    monkeypatch.setattr(R, "skaven_known", lambda w, F: ["wh2_main_skv_clan_skryre"])
    assert R.thirteenth_waits(None, 0, {DOM: 15}) is None
    assert R.thirteenth_waits(None, 0, {DOM: 5}) is None
    assert "global cooldown" in R.thirteenth_waits(None, 0, {DOM: 4})
    assert "global cooldown" in R.thirteenth_waits(None, 0, {DOM: 0})
    monkeypatch.setattr(R, "skaven_known", lambda w, F: [])
    assert "no other Skaven clan" in R.thirteenth_waits(None, 0, {DOM: 15})
