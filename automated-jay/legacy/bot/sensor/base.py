from __future__ import annotations
from typing import Protocol
from ..schema import State


class Sensor(Protocol):
    name: str

    def read(self) -> State:
        """Return the current player-visible state. Never raises for a bad read; sets ok=False."""
        ...
