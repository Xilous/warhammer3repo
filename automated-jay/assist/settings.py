"""Every setting the player can change, editable in the expanded widget (player rule 2026-10-21: "all forms of config
should be adjustable in the expanded view of the widget, so that it can be changed easily between turns").

Each setting names its strategy file and key path; the widget draws one row per setting (a click toggles a switch or
cycles a choice, - and + step a number) and writes the file at once. Every step reads its file fresh at each pass, so
a change applies from the next pass on. Ordered lists the player edits by hand (the build priority, skill orders, the
Secrets shop order, the army template) are not here: they are shown, not edited, in the widget.

A new setting read by code goes in SETTINGS (tests/test_settings.py checks each one exists in its file).
"""
from __future__ import annotations
import json
from dataclasses import dataclass

from bot import config


@dataclass(frozen=True)
class Setting:
    file: str                      # strategy file name
    path: tuple[str, ...]          # key path inside it
    label: str
    group: str
    kind: str = "bool"             # bool, int, float, choice
    default: object = None
    step: float = 1
    lo: float | None = None
    hi: float | None = None
    choices: tuple = ()
    unit: str = ""
    fmt: str = "{}"


SETTINGS: list[Setting] = [
    # turn and pacing (assist/runner.py, tools/ui.py, assist/heroes.py)
    Setting("automation.json", ("auto_end_turn",), "End every turn by itself", "Turn", default=False),
    Setting("automation.json", ("close_notices_during_turn",), "Close event notices during your turn", "Turn",
            default=True),
    Setting("automation.json", ("thirteenth_scheme",), "Cast the Thirteenth Scheme", "Turn", default=True),
    Setting("automation.json", ("leave_lords_list",), "Open Lords & Heroes after the turn start", "Turn",
            default=True),
    Setting("automation.json", ("pace_ms",), "Pause after every click", "Turn", "int", 120, 20, 0, 1000, unit=" ms"),
    Setting("automation.json", ("settle_frames",), "Quiet frames after each action", "Turn", "int", 3, 1, 0, 30,
            unit=" frames"),
    Setting("automation.json", ("camera_pan",), "Camera panning", "Turn", "choice", "auto",
            choices=("auto", "edge", "keys")),
    Setting("automation.json", ("ai_offers",), "AI diplomacy offers", "Turn", "choice", "ask",
            choices=("ask", "accept_gifts")),
    # buildings (assist/build.py)
    Setting("automation.json", ("buildings", "never_build_in_provinces_adjacent_to_enemy_at_war"),
            "Leave frontline settlements to you", "Buildings", default=False),
    Setting("automation.json", ("buildings", "repair_damaged"), "Repair damaged buildings", "Buildings", default=True),
    Setting("automation.json", ("buildings", "army_buildings_first"), "Army buildings first (when affordable)",
            "Buildings", "choice", "first", choices=("first", "all", "off")),
    Setting("automation.json", ("buildings", "off_list_buildings"), "Buildings not on the list", "Buildings",
            "choice", "replace", choices=("replace", "ask")),
    # army (assist/new_army.py)
    Setting("automation.json", ("army_builder", "auto_create"), "Raise new armies by itself", "Army", default=False),
    Setting("automation.json", ("army_builder", "income_reserve"), "Income kept after a new army", "Army", "int", 0,
            50, 0, 5000, unit=" /turn"),
    # skills (assist/skills.py)
    Setting("skills.json", ("generic_lord", "mounts"), "Lords without a template: mounts", "Skills", "choice",
            "take_as_unlocked", choices=("take_as_unlocked", "skip")),
    # Masterplans (assist/masterplans.py, Thanquol)
    Setting("masterplans.json", ("steal_take", "enabled"), "Steal-Takes", "Masterplans", default=True),
    Setting("masterplans.json", ("steal_take", "prefer_not_at_war"), "Steal from factions not at war with you first",
            "Masterplans", default=True),
    Setting("masterplans.json", ("steal_take", "skip_own_provinces"), "Skip settlements in your provinces",
            "Masterplans", default=True),
    Setting("masterplans.json", ("steal_take", "at_max_alarm"), "At maximum Alarm", "Masterplans", "choice",
            "complete", choices=("complete", "abandon")),
    Setting("masterplans.json", ("steal_take", "max_pan"), "Look for targets this far off screen", "Masterplans",
            "int", 120, 20, 0, 600, unit=" map units"),
    Setting("masterplans.json", ("steal_take", "gold_per_warpstone"), "Gold worth one Warpstone", "Masterplans",
            "int", 1, 1, 1, 100),
    Setting("masterplans.json", ("shop", "enabled"), "Buy Clan Scruten Secrets", "Masterplans", default=True),
    Setting("masterplans.json", ("shop", "keep_warpstone"), "Warpstone kept for a Kill-Stab", "Masterplans", "int",
            50, 10, 0, 1000),
]


def _path(file: str):
    return config.STRATEGY_DIR / file


def _load(file: str) -> dict:
    try:
        return json.load(open(_path(file), encoding="utf-8"))
    except Exception:
        return {}


def get(s: Setting):
    o = _load(s.file)
    for k in s.path:
        if not isinstance(o, dict) or k not in o:
            return s.default
        o = o[k]
    return o


def _write(file: str, data: dict) -> None:
    p = _path(file)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)


def put(s: Setting, value) -> None:
    data = _load(s.file)
    o = data
    for k in s.path[:-1]:
        o = o.setdefault(k, {})
    o[s.path[-1]] = value
    _write(s.file, data)


def nudge(s: Setting, direction: int):
    """The widget's click: a switch flips, a choice moves to the next, a number moves one step (within its limits).
    -> the new value (written)."""
    v = get(s)
    if s.kind == "bool":
        v = not bool(v)
    elif s.kind == "choice":
        i = s.choices.index(v) if v in s.choices else -1
        v = s.choices[(i + (1 if direction >= 0 else -1)) % len(s.choices)]
    else:
        v = (v if isinstance(v, (int, float)) else s.default) + direction * s.step
        if s.lo is not None:
            v = max(s.lo, v)
        if s.hi is not None:
            v = min(s.hi, v)
        v = int(round(v)) if s.kind == "int" else round(v, 4)
    put(s, v)
    return v


def shown(s: Setting) -> str:
    v = get(s)
    if s.kind == "bool":
        return "on" if v else "off"
    try:
        return s.fmt.format(v) + s.unit
    except (ValueError, TypeError):
        return f"{v}{s.unit}"


# ------------------------------------------------------------------ which steps run when (automation.json schedule)
PHASES = (("turn_start", "turn start"), ("end_turn", "Build & End Turn"))


def step_order() -> list[str]:
    from .runner import DEFAULT_SCHEDULE, STEP_FNS
    order = []
    for ph, _ in PHASES:
        for n in DEFAULT_SCHEDULE[ph]:
            if n not in order:
                order.append(n)
    return order + [n for n in STEP_FNS if n not in order]


def step_on(phase: str, name: str) -> bool:
    from .runner import schedule
    return name in schedule()[phase]


def set_step(phase: str, name: str, on: bool) -> None:
    """A step in or out of a phase, the list kept in the order the steps run (step_order)."""
    from .runner import schedule
    data = _load("automation.json")
    sch = data.setdefault("schedule", {k: list(v) for k, v in schedule().items()})
    cur = set(sch.get(phase) or [])
    (cur.add if on else cur.discard)(name)
    sch[phase] = [n for n in step_order() if n in cur]
    _write("automation.json", data)
