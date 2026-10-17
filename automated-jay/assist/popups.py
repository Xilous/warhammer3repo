"""Turn-start popups, from the UI tree.

Every popup is a visible child of the UI root that is not part of the normal campaign HUD.
  - event notices (ids containing "event") are closed with their own accept/close button: safe, they only
    report something that already happened;
  - anything that asks for a decision (AI diplomacy offers, pre-battle screens, dilemmas, message boxes,
    and any popup not recognised yet) is left for the player: the assistant waits and says what is open.
An unrecognised panel is shown by its id. When it is harmless, the player clicks "Ignore <id>" in the app once:
the id goes into strategy/popup_ignore.json and never blocks a pass again.
"""
from __future__ import annotations
import json

from bot import config
from bot.focus import game_focus
from bot.sensor.ui import UI
from tools import wait
from tools.ui import click

IGNORE_FILE = config.STRATEGY_DIR / "popup_ignore.json"

NORMAL = {
    "ai_turns",            # AI turn progress bar (only during end turn)
    "ai_attack_targets_parent", "3d_ui_parent", "mission_indicator_parent", "endgame_scenarios_holder",
    "hud_campaign", "menu_bar", "panel_manager", "under_advisor_docker", "tooltip_default", "black_fade",
    "tutorial_halo_group",  # tutorial highlight around a HUD element: never a decision (seen 2026-10-16)
    "advice_interface", "help_panel", "saving_icon", "qa_console", "campaign_space_bar_options",
    "targeting_interface_dimming", "character_map_path_icons", "units_panel", "resources_bar",
    # panels the assistant itself opens
    "settlement_panel", "character_details_panel", "technology_panel", "units_recruitment",
    "recruitment_docker", "diplomacy_dropdown_hidden",
}
DECISION_HINTS = {
    "diplomacy_dropdown": "an AI diplomacy offer",
    "popup_pre_battle": "a battle",
    "popup_battle_results": "battle results",
    "dilemma": "a dilemma",
    "popup_message_box": "a confirmation box",
    "esc_menu": "the game menu",
}
CLOSE_BUTTONS = ("button_accept", "button_tick", "button_close", "button_ok", "button_dismiss")
MAX_NOTICES = 24              # notices closed per check at most (they stack at turn start)
CLOSE_TIMEOUT = 2.0           # s: a clicked notice must be gone (or show the next stacked notice) by then
NEXT_NOTICE_MS = 150          # after the last notice closed: no root panel appearing for this long = none is coming


def ignored() -> set[str]:
    """Root-child ids the player marked as harmless (strategy/popup_ignore.json: {"ignore": [ids]})."""
    try:
        return set(json.loads(IGNORE_FILE.read_text(encoding="utf-8")).get("ignore", []))
    except (OSError, ValueError, AttributeError):
        return set()


def add_ignored(cid: str) -> None:
    ids = sorted(ignored() | {cid})
    data = {"_doc": "Root-level panels the assistant treats as part of the normal HUD (added with the app's "
                    "'Ignore' button). Remove an id to make it block the turn-start pass again.",
            "ignore": ids}
    tmp = IGNORE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(IGNORE_FILE)


def scan(ui: UI | None = None) -> list[tuple[int, str]]:
    ui = ui or UI()
    if ui.find_root() is None:
        raise RuntimeError("game UI not found in memory")
    skip = NORMAL | ignored()
    return [(c, cid) for c, cid in ui.root_children()
            if cid not in skip and not cid.startswith("tooltip")]          # hover tooltips are never popups


def needs_choice(ui: UI, c: int) -> bool:
    """An 'events' popup can be a plain notice or a choice (dilemma). Choices have dilemma layouts or
    choice buttons: those are always left to the player."""
    for _b, n, _r in ui.nodes(c):
        if "dilemma" in n or n == "choice_button" or "ChoiceDetailRecord" in n:
            return True
    return False


def known(cid: str) -> bool:
    return any(k in cid for k in DECISION_HINTS)


def describe(cid: str) -> str:
    for k, v in DECISION_HINTS.items():
        if k in cid:
            return f"{v} ({cid})"
    return f"unknown panel '{cid}'"


def is_event(cid: str) -> bool:
    return "event" in cid and not any(k in cid for k in DECISION_HINTS)


def _close_button(ui: UI, c: int) -> int | None:
    for b, n, _r in ui.nodes(c):
        if n in CLOSE_BUTTONS:
            return b
    return None


def _closable(ui: UI) -> list[tuple[int, str, int]]:
    out = []
    for c, cid in scan(ui):
        if not is_event(cid) or needs_choice(ui, c):
            continue
        btn = _close_button(ui, c)
        if btn is not None:
            out.append((c, cid, btn))
    return out


def _shows(ui: UI, c: int) -> tuple:
    """The texts a notice shows: the same panel can be re-used for the next stacked notice."""
    return tuple(t for b, _n, _r in ui.nodes(c) if (t := ui.text(b)))


def dismiss_events(ui: UI | None = None) -> list[str]:
    """Close event notices, one at a time (they can stack), all inside one game_focus. Each click is followed by a
    wait until that notice is gone or shows the next stacked one; after the last, a short wait that no further panel
    is sliding in. Returns the ids closed. A notice that does not close raises WaitTimeout (the pass is skipped)."""
    ui = ui or UI()
    closed: list[str] = []
    # the player's standing answer to one dilemma (assist/rites.py): the Dominating Scheme's Verminlord choice
    from . import rites
    ev = ui.root_child("events")
    if ev and any(ids[-1].endswith(rites.VERMINLORD_DILEMMA + rites.WARPSEER_CHOICE) for _c, ids in ui.walk(ev)):
        with game_focus():
            if rites.answer_verminlord_dilemma(ui, timeout=0.5):
                closed.append("Verminlord choice: Warpseer")
    focus = None
    try:
        for _ in range(MAX_NOTICES):
            todo = _closable(ui)
            if not todo and closed:
                wait.root_children_stable(ui, ms=NEXT_NOTICE_MS, timeout=3, must=False)
                todo = _closable(ui)
            if not todo:
                break
            if focus is None:
                focus = game_focus()
                focus.__enter__()
            c, cid, btn = todo[0]
            before = _shows(ui, c)
            click(ui, btn)
            wait.wait_until(lambda: not ui.effective_visible(btn) or _shows(ui, c) != before, CLOSE_TIMEOUT,
                            f"{cid} notice closed")
            closed.append(cid)
    finally:
        if focus is not None:
            focus.__exit__(None, None, None)
    return closed


def open_decisions(ui: UI | None = None) -> list[tuple[str, str, bool]]:
    """(id, description, ignorable) for each open popup that needs the player. Only unknown panels can be
    ignored: diplomacy offers, battles, dilemmas and message boxes always wait for the player."""
    ui = ui or UI()
    out = []
    for c, cid in scan(ui):
        if not is_event(cid):
            out.append((cid, describe(cid), not known(cid)))
        elif needs_choice(ui, c):
            out.append((cid, f"a dilemma (choice event, {cid})", False))
    return out


def decisions(ui: UI | None = None) -> list[str]:
    """Human-readable list of open popups that need the player."""
    return [d for _cid, d, _ig in open_decisions(ui)]
