"""Memory first (player rule 2026-10-19, CLAUDE.md): game state and verification come from memory; the UI tree is for
click targets, confirming a click, and what exists only in the UI. Every function that reads UI state or text is
listed here with why. A new one fails this test until it is either moved to memory or listed with its reason:

  click     confirms a click took, a tab or card is selected, or finds the target (the card a name belongs to)
  ui-only   the value exists only in the UI (which popup is open, a notice's text, the multiplayer pending-action
            message, the End Turn button's "you may end the turn" state, the notification settings)
  fallback  memory decides; the UI is read only when memory cannot be, or to report that the game disagreed
"""
import ast
import pathlib
import re

ALLOWED = {
    "assist/army_builder.py::card_selected": "click",
    "assist/army_builder.py::card_unit_name": "click",            # matches a card to a unit found in memory
    "assist/army_builder.py::recruit_engineer": "fallback",       # cap and provinces from memory; the panel confirms
    "assist/army_builder.py::select_settlement": "click",
    "assist/build.py::_greyed": "fallback",                       # memory (locks, main level, dev points, cost) first
    "assist/build.py::_why_greyed": "fallback",
    "assist/build.py::_press": "click",
    "assist/build.py::look": "click",
    "assist/build.py::ui_construct": "fallback",
    "assist/build.py::ui_open_province": "click",
    "assist/build.py::ui_upgrade": "fallback",
    "assist/heroes.py::_take_card": "click",
    "assist/heroes.py::province_row": "click",
    "assist/heroes.py::row_selected": "click",
    "assist/masterplans.py::_confirm_trigger": "click",
    "assist/masterplans.py::_select_underling": "click",
    "assist/masterplans.py::_txt": "click",                       # confirms the targeted settlement
    "assist/masterplans.py::buy_secrets": "click",
    "assist/masterplans.py::_check_tab": "fallback",              # memory decides the offer; the open tab is compared
    "assist/masterplans.py::close_panel": "click",
    "assist/masterplans.py::open_main": "click",
    "assist/new_army.py::create": "fallback",                     # pool, engineer, province, money from memory
    "assist/new_army.py::warpseer_card": "click",
    "assist/notifications.py::_texts": "ui-only",
    "assist/notifications.py::_toggles": "ui-only",
    "assist/notifications.py::showing": "ui-only",
    "assist/popups.py::_shows": "ui-only",
    "assist/popups.py::_sig": "ui-only",
    "assist/popups.py::log_open": "ui-only",
    "assist/popups.py::significant": "ui-only",
    "assist/popups.py::title": "ui-only",
    "assist/rites.py::cast_rite": "fallback",                     # cooldown from memory; cost and lock: being moved
    "assist/rites.py::pick_commandment": "click",
    "assist/runner.py::allowed": "ui-only",                       # End Turn button: the game's "may end now"
    "assist/runner.py::ended": "fallback",                        # memory: the turn record's ended list
    "assist/runner.py::mp_ready": "fallback",
    "assist/runner.py::mp_waiting": "fallback",                   # memory's ended list goes stale on a cancel: the button decides

    "assist/runner.py::phase": "ui-only",
    "assist/runner.py::press_end_turn": "ui-only",
    "assist/skills.py::_lords_row": "click",
    "assist/skills.py::_selected": "click",
    "assist/skills.py::_walk": "fallback",                        # memory_state first, the card logged against it (_spend's walk)
    "assist/workshop.py::run": "fallback",                        # level from memory; the card confirms
    "tools/ui.py::other_players_pending": "ui-only",
}

PAT = re.compile(r"ui\.state\(|ui\.text\(|_why_greyed\(|_greyed\(|card_text\(")
ROOT = pathlib.Path(__file__).resolve().parent.parent


def _ui_reads() -> set[str]:
    out = set()
    for p in sorted((ROOT / "assist").glob("*.py")) + [ROOT / "tools" / "ui.py"]:
        src = p.read_text(encoding="utf-8")
        lines = src.splitlines()
        funcs = [(n.lineno, n.end_lineno, n.name) for n in ast.walk(ast.parse(src))
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        rel = p.relative_to(ROOT).as_posix()
        for i, line in enumerate(lines, 1):
            if PAT.search(line) and not line.strip().startswith("#") and "def " not in line:
                fn = min((f for f in funcs if f[0] <= i <= f[1]), key=lambda f: f[1] - f[0],
                         default=(0, 0, "<module>"))[2]
                out.add(f"{rel}::{fn}")
    return out


def test_every_ui_read_is_accounted_for():
    new = sorted(_ui_reads() - set(ALLOWED))
    assert not new, ("UI state or text read where memory should decide (CLAUDE.md, memory first). Move it to memory, "
                     "or list it in tests/test_memory_first.py with its reason: " + ", ".join(new))


def test_categories():
    assert set(ALLOWED.values()) <= {"click", "ui-only", "fallback"}
