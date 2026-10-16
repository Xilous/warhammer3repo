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
import time

from bot import config
from bot.focus import game_focus
from bot.sensor.ui import UI
from tools.ui import click_at

IGNORE_FILE = config.ROOT / "strategy" / "popup_ignore.json"

NORMAL = {
    "ai_turns",            # AI turn progress bar (only during end turn)
    "ai_attack_targets_parent", "3d_ui_parent", "mission_indicator_parent", "endgame_scenarios_holder",
    "hud_campaign", "menu_bar", "panel_manager", "under_advisor_docker", "tooltip_default", "black_fade",
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
    root = ui.find_root()
    if root is None:
        raise RuntimeError("game UI not found in memory")
    skip = NORMAL | ignored()
    out = []
    for c in ui.children(root):
        try:
            if ui.pm.read_bytes(c + 0x353, 1)[0] == 0:
                continue
        except Exception:
            continue
        cid = ui.id(c) or "?"
        if cid not in skip and not cid.startswith("tooltip"):        # hover tooltips are never popups
            out.append((c, cid))
    return out


def needs_choice(ui: UI, c: int) -> bool:
    """An 'events' popup can be a plain notice or a choice (dilemma). Choices have dilemma layouts or
    choice buttons: those are always left to the player."""
    for _b, ids in ui.walk(c):
        n = ids[-1]
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


def dismiss_events(ui: UI | None = None) -> list[str]:
    """Close event notices (they can stack: keep closing until none is left). Returns the ids closed."""
    ui = ui or UI()
    closed = []
    for _ in range(12):
        n = len(closed)
        closed += _dismiss_once(ui)
        if len(closed) == n:
            break
    return closed


def _dismiss_once(ui: UI) -> list[str]:
    closed = []
    for c, cid in scan(ui):
        if not is_event(cid) or needs_choice(ui, c):
            continue
        btn = None
        for b, ids in ui.walk(c):
            if ids[-1] in CLOSE_BUTTONS:
                btn = b
                break
        if btn is None:
            continue
        with game_focus():
            click_at(*ui.comp(btn).center)
            time.sleep(0.8)
        closed.append(cid)
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
