"""The brain: deterministic rules over State. This is where the player's strategy lives.

Rules are checked in order; the first that applies returns an Action. If none
applies, the loop pauses and asks the human, and the answer becomes a new rule.
PoC rulebook: one rule, end the turn.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

from ..schema import State


@dataclass(frozen=True)
class Action:
    kind: str                 # "end_turn" | "ask" | "noop"
    reason: str


Rule = Callable[[State], Action | None]


def rule_end_turn(s: State) -> Action | None:
    if s.ok:
        return Action("end_turn", "nothing else to do this turn")
    return None


RULES: list[Rule] = [rule_end_turn]


def decide(s: State) -> Action:
    for r in RULES:
        a = r(s)
        if a is not None:
            return a
    return Action("ask", "no rule covers this state")
