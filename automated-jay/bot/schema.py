"""The state the brain is allowed to see.

This file is the fairness contract. Every field here must be something a human
player could read off the screen at that moment. Nothing is added here without
answering: "where on screen would I see this?"
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import json


@dataclass
class State:
    # Visible top bar
    turn: int | None = None          # top-right turn counter
    treasury: int | None = None      # top bar gold
    income: int | None = None        # top bar gold, projected per-turn change in brackets

    # Bookkeeping, not game information
    source: str = "none"             # which sensor produced this
    ok: bool = False                 # sensor had a valid read

    extras: dict = field(default_factory=dict)   # sensor-specific debug, never used by rules

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)
