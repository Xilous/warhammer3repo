"""Benchmark: load a named save through the game's own menus, wait until the campaign is ready (by condition), run
one full turn-start pass (Runner.automate) on that turn and print per-step times and the total.

    python -X utf8 -m tools.bench                       # the save "ENDGAME SKAVEN" (turn 90: identical work each load)
    python -X utf8 -m tools.bench "SAVE NAME" [--runs N] [--no-pass]

Loading: Menu button (menu_bar/button_menu) -> esc_menu/button_load -> load_game_panel: the save rows are
listview/list_clip/list_box/save_game, the shown name is the `name` child's text (UI.text). The playthrough list on
the left filters the rows: the bench tries the selected playthrough first, then each other one. Row click ->
button_confirm_load. Ready = a new campaign model in memory, the turn readable, End Turn shown and enabled
(runner.players_turn), and no root panel appearing or disappearing for 500 ms.

Never saves anything. Every pass is written to runs/timing-YYYYMMDD.jsonl with label "bench".
"""
from __future__ import annotations
import sys
import time

from bot.focus import game_focus, return_to_terminal
from bot.sensor.memory import MemorySensor
from bot.sensor.ui import UI
from tools import timing, wait
from tools.ui import click_at, wheel

DEFAULT_SAVE = "ENDGAME SKAVEN"
LOAD_TIMEOUT = 240.0


def _click(ui: UI, c: int) -> None:
    click_at(*ui.comp(c).center)


def _rows(ui: UI) -> list[tuple[int, str]]:
    lb = ui.first("list_box", under="listview")
    if lb is None:
        return []
    out = []
    for r in ui.children(lb):
        if not ui.visible(r) or ui.id(r) != "save_game":
            continue
        name = next((ch for ch in ui.children(r) if ui.id(ch) == "name"), None)
        out.append((r, (ui.text(name) or "") if name else ""))
    return out


def _find_row(ui: UI, save: str) -> int | None:
    return next((r for r, n in _rows(ui) if n == save), None)


def _scroll_into_view(ui: UI, row: int) -> bool:
    clip_c = ui.first("list_clip", under="listview")
    if clip_c is None:
        return False
    for _ in range(40):
        clip, k = ui.comp(clip_c), ui.comp(row)
        if wait._inside(k, clip):
            return True
        before = k.y
        wheel(*clip.center, 1 if k.y < clip.y else -1)
        wait.value_changes(lambda: ui.comp(row).y, before, timeout=1.0, what="save list scrolled")
    return False


def open_load_panel(ui: UI) -> None:
    ids = wait.root_children(ui)
    if "dialogue_box" in ids and "load_game_panel" in ids:        # a confirmation left from an earlier attempt
        _click(ui, wait.appears(ui, "button_cancel", under="dialogue_box").ptr)
        wait.gone(ui, "dialogue_box")
        ids = wait.root_children(ui)
    if "load_game_panel" in ids:
        return
    if "esc_menu" not in ids:
        _click(ui, wait.appears(ui, "button_menu", under="menu_bar").ptr)
        wait.appears(ui, "button_load", under="esc_menu", timeout=5)
    _click(ui, wait.appears(ui, "button_load", under="esc_menu").ptr)
    wait.appears(ui, "load_game_panel", timeout=5)
    wait.wait_until(lambda: _rows(ui), 5, "save rows listed")


def pick_save(ui: UI, save: str) -> int:
    """The row of `save`, selecting each playthrough in turn until it is listed."""
    row = _find_row(ui, save)
    if row is None:
        lst = ui.first("list_box", under="playthrough_list")
        pts = [p for p in (ui.children(lst) if lst else []) if (ui.id(p) or "").startswith("playthrough")]
        for p in pts:
            before = [n for _r, n in _rows(ui)]
            _click(ui, p)
            wait.wait_until(lambda: [n for _r, n in _rows(ui)] != before or _find_row(ui, save), 2,
                            "save rows re-listed", must=False)
            row = _find_row(ui, save)
            if row is not None:
                break
    if row is None:
        raise RuntimeError(f"save {save!r} not found in any playthrough")
    if not _scroll_into_view(ui, row):
        raise RuntimeError(f"save {save!r} could not be scrolled into view")
    return row


def load(save: str, m: MemorySensor, ui: UI) -> float:
    """Load `save` from the campaign map (or the game menu). Returns seconds until the campaign was ready."""
    before = m.read().extras.get("model")
    t0 = time.perf_counter()
    with game_focus():
        open_load_panel(ui)
        row = pick_save(ui, save)
        _click(ui, row)
        btn = wait.appears(ui, "button_confirm_load", under="load_game_panel")
        wait.wait_until(lambda: not (ui.state(btn.ptr) or "").startswith(("inactive", "disabled")), 2,
                        "Load button enabled")
        _click(ui, btn.ptr)
        # a "progress will be lost" box may ask first
        started = lambda: "load_game_panel" not in wait.root_children(ui)
        if not wait.wait_until(lambda: started() or ui.first("button_tick", under="dialogue_box"), 3,
                               "load started or a confirmation box") is True:
            _click(ui, ui.first("button_tick", under="dialogue_box"))
            wait.wait_until(started, 3, "load started")
    return_to_terminal()
    wait_ready(m, ui, before)
    return time.perf_counter() - t0


def wait_ready(m: MemorySensor, ui: UI, old_model) -> None:
    from assist.runner import players_turn

    def loaded():
        s = m.read()
        return s.ok and s.extras.get("model") != old_model and s.turn
    wait.wait_until(loaded, LOAD_TIMEOUT, "campaign model of the loaded save", poll=0.05)
    wait.wait_until(lambda: players_turn(ui)[0], LOAD_TIMEOUT, "End Turn shown and enabled", poll=0.02)
    wait.root_children_stable(ui, ms=500, timeout=30)


def bench(save: str, runs: int = 1, do_pass: bool = True) -> list[dict]:
    from assist.runner import Runner
    m = MemorySensor()
    ui = UI(m)
    out = []
    for i in range(runs):
        secs = load(save, m, ui)
        s = m.read()
        print(f"[{i + 1}/{runs}] loaded {save!r}: turn {s.turn}, treasury {s.treasury}, ready after {secs:.1f} s",
              flush=True)
        if not do_pass:
            continue
        r = Runner()
        r.last_turn = s.turn
        t = time.perf_counter()
        lines = r.automate(s.turn, label="bench")
        total = time.perf_counter() - t
        rec = timing.LAST
        print(f"[{i + 1}/{runs}] pass: {total:.2f} s", flush=True)
        for line in lines:
            print("    " + line, flush=True)
        if rec:
            print(timing.summary([rec]), flush=True)
            out.append(rec)
    return out


def main() -> int:
    args = sys.argv[1:]
    runs = int(args[args.index("--runs") + 1]) if "--runs" in args else 1
    pos = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] != "--runs")]
    save = pos[0] if pos else DEFAULT_SAVE
    try:
        bench(save, runs, do_pass="--no-pass" not in args)
    finally:
        return_to_terminal()
    return 0


if __name__ == "__main__":
    sys.exit(main())
