"""The widget's settings (player rule 2026-10-21: every setting adjustable in the expanded widget): each one exists in
its strategy file with the type the widget edits, a click changes the file, and the step switches keep run order.

    python -X utf8 -m pytest tests -q
"""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist import settings as S
from bot import config

STRATEGY = Path(__file__).resolve().parents[1] / "strategy"


def test_every_setting_is_in_its_file():
    for s in S.SETTINGS:
        o = json.load(open(STRATEGY / s.file, encoding="utf-8"))
        for k in s.path:
            assert k in o, f"{s.file}: {'/'.join(s.path)} missing"
            o = o[k]
        if s.kind == "bool":
            assert isinstance(o, bool), s.label
        elif s.kind == "choice":
            assert o in s.choices, s.label
        else:
            assert isinstance(o, (int, float)) and not isinstance(o, bool), s.label


@pytest.fixture
def tmp_strategy(tmp_path, monkeypatch):
    d = tmp_path / "strategy"
    shutil.copytree(STRATEGY, d)
    monkeypatch.setattr(config, "STRATEGY_DIR", d)
    from assist import runner
    monkeypatch.setattr(runner, "AUTOMATION", d / "automation.json")
    return d


def test_clicks_change_the_file(tmp_strategy):
    pace = next(s for s in S.SETTINGS if s.path == ("pace_ms",))
    v = S.get(pace)
    assert S.nudge(pace, +1) == v + pace.step
    assert json.load(open(tmp_strategy / "automation.json", encoding="utf-8"))["pace_ms"] == v + pace.step
    keep = next(s for s in S.SETTINGS if s.path == ("shop", "keep_warpstone"))
    for _ in range(200):
        S.nudge(keep, +1)
    assert S.get(keep) == keep.hi
    flag = next(s for s in S.SETTINGS if s.path == ("auto_end_turn",))
    before = S.get(flag)
    S.nudge(flag, +1)
    assert S.get(flag) is (not before)
    pan = next(s for s in S.SETTINGS if s.path == ("camera_pan",))
    seen = {S.nudge(pan, +1) for _ in range(3)}
    assert seen == set(pan.choices)


def test_other_keys_are_kept(tmp_strategy):
    before = json.load(open(tmp_strategy / "masterplans.json", encoding="utf-8"))
    S.nudge(next(s for s in S.SETTINGS if s.path == ("shop", "keep_warpstone")), +1)
    after = json.load(open(tmp_strategy / "masterplans.json", encoding="utf-8"))
    assert after["shop"]["order"] == before["shop"]["order"]
    assert after["_doc"] == before["_doc"] if "_doc" in before else True


def test_step_switches_keep_run_order(tmp_strategy):
    from assist import runner
    S.set_step("turn_start", "tech", False)
    assert "tech" not in runner.schedule()["turn_start"]
    S.set_step("turn_start", "tech", True)
    assert runner.schedule()["turn_start"] == ["rites", "workshop", "tech", "skills"]
    S.set_step("turn_start", "buildings", True)
    start = runner.schedule()["turn_start"]
    assert start.index("skills") < start.index("buildings")
