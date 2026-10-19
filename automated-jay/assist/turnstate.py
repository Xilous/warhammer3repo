"""The assistant's state for the turn it is in, in one record (player request 2026-10-19: "a lack of state management
in the automations for multiplayer": Build & End Turn pressed while another player's battle froze the game was
dropped, not queued).

Two things are tracked, separately:

1. The game's phase, observed (phase() in assist/runner.py, memory first):
     free        the player's turn, and the game takes actions now
     held        the player's turn in memory, but the game holds actions for now: another player's battle or
                 decision (multiplayer), a cinematic, a full-screen panel, End Turn greyed out, a notice
     ended       the player pressed End Turn (multiplayer: waiting for the other players)
     not_mine    another faction's turn (the AI, or the other players in a hot-seat order)
     none        no campaign loaded
2. What the assistant owes this turn, recorded per campaign and turn and saved (runs/turn_state.json), so that a
   request is never lost while the game is held and a restart of the assistant picks up where it was:
     start_done      the turn-start pass ran
     end_requested   the player asked for Build & End Turn (queued while the phase is not free)
     run_requested   the player asked for Run now (queued likewise)
     end_done        the turn was ended by the assistant
   A record belongs to (campaign, turn): any other turn starts a fresh one, which drops what the old turn owed.
"""
from __future__ import annotations
import json
import time
from dataclasses import asdict, dataclass, field

from bot import config

PATH = config.RUNS_DIR / "turn_state.json"
FREE, HELD, ENDED, NOT_MINE, NONE = "free", "held", "ended", "not_mine", "none"


@dataclass
class TurnState:
    campaign: str = ""                 # the campaign model pointer and the player's faction (hex:key)
    turn: int | None = None
    start_done: bool = False
    end_requested: bool = False
    run_requested: bool = False
    end_done: bool = False
    since: float = field(default_factory=time.time)

    def owes(self) -> list[str]:
        """The queued requests, in the order they are carried out (Build & End Turn includes the turn-start steps
        when they have not run)."""
        out = []
        if self.end_requested and not self.end_done:
            out.append("end")
        elif self.run_requested:
            out.append("run")
        return out


def campaign_id(model, faction_key: str | None) -> str:
    return f"{model:#x}:{faction_key or '?'}" if model else ""


def load() -> TurnState:
    try:
        d = json.loads(PATH.read_text(encoding="utf-8"))
        return TurnState(**{k: v for k, v in d.items() if k in TurnState.__dataclass_fields__})
    except (OSError, ValueError, TypeError):
        return TurnState()


def save(st: TurnState) -> None:
    from tools.fileio import replace
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(st), indent=1), encoding="utf-8")
        replace(tmp, PATH)
    except OSError:
        pass


def for_turn(st: TurnState, campaign: str, turn: int | None) -> TurnState:
    """The record for this campaign and turn: st itself, or a fresh one (saved) when either changed."""
    if st.campaign == campaign and st.turn == turn:
        return st
    st = TurnState(campaign=campaign, turn=turn)
    save(st)
    return st
