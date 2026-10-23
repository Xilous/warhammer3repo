"""The standing answer to AI offers (assist/popups.py, setting "ai_offers"): which offers count as gifts.

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist.popups import is_gift


def test_gold_for_a_pact_is_a_gift():
    # turn 64 (2026-10-22): Gorbad Ironclaw, 600 gold and a Non-Aggression Pact for a Non-Aggression Pact
    assert is_gift({"nonaggression_pact"}, {"payment", "nonaggression_pact"})
    assert is_gift(set(), {"payment"})
    assert is_gift({"trade_agreement"}, {"trade_agreement"})


def test_anything_binding_or_costly_is_left_to_the_player():
    assert not is_gift({"payment"}, {"nonaggression_pact"})                 # they want gold
    assert not is_gift({"military_alliance"}, {"payment"})
    assert not is_gift({"nonaggression_pact"}, {"payment", "military_access"})
    assert not is_gift({"nonaggression_pact"}, set())                       # they give nothing
    assert not is_gift({"join_war"}, {"payment"})
