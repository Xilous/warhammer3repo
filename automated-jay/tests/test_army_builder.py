"""The army step's memory check takes the run's own reasons for units it left (gold, capacity) as "not possible".

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist import army_builder as A


def test_gold_reasons_are_not_possible():
    # turn 49, 2026-10-22: the first run's lines, then the verification run's, which replaced them
    for line in ("Tichit: Stormfiends (Ratling Cannons): 810 gold each, 798 in the treasury",
                 "Tichit: 5 Stormfiends (Ratling Cannons) left for later turns",
                 "Tichit: no gold to recruit this turn (798 to spend, 1350 needed)"):
        assert any(r in line for r in A.NOT_POSSIBLE), line
    assert not any(r in "Tichit: queued 1 Stormfiends (Ratling Cannons)" for r in A.NOT_POSSIBLE)


def test_affordable_counts_replacements_in_template_order():
    from assist.army_builder import affordable
    prices = {"sf": 1350, "mc": 1750}
    missing = {"sf": 3, "mc": 2}
    assert affordable(735, missing, prices) == 0
    assert affordable(3435, missing, prices) == 2          # 2 Stormfiends, 735 left: not a third
    assert affordable(4050 + 1750, missing, prices) == 4
    assert affordable(10 ** 6, missing, prices) == 5
