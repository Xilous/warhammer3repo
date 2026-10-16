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
from tools.ui import click, move_to, wheel

DEFAULT_SAVE = "ENDGAME SKAVEN"
LOAD_TIMEOUT = 240.0
MENU_ATTEMPTS = 12


def _click(ui: UI, c) -> None:
    click(ui, c)


def _save_list(ui: UI) -> int:
    """load_game_panel/.../savegames/listview (the HUD's event feed has a listview too: scope to the panel)."""
    lv = ui.first("listview", under="load_game_panel")
    if lv is None:
        raise RuntimeError("the save list is not shown")
    return lv


def _rows(ui: UI) -> list[tuple[int, str]]:
    lb = ui.first("list_box", under=_save_list(ui))
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
    clip_c = ui.first("list_clip", under=_save_list(ui))
    if clip_c is None:
        return False
    for _ in range(40):
        clip, k = ui.comp(clip_c), ui.comp(row)
        if wait._inside(k, clip):
            return True
        wheel(*clip.center, 1 if k.y < clip.y else -1)
        wait.stable(lambda: ui.comp(row).y, n=3, eps=0.5, timeout=2.0, what="save list scrolled and still", ui=ui)
    return False


def open_load_panel(ui: UI) -> None:
    ids = wait.root_children(ui)
    if "dialogue_box" in ids and "load_game_panel" in ids:        # a confirmation left from an earlier attempt
        _click(ui, wait.appears(ui, "button_cancel", under="dialogue_box").ptr)
        wait.gone(ui, "dialogue_box")
        ids = wait.root_children(ui)
    if "load_game_panel" in ids:
        return
    for _attempt in range(MENU_ATTEMPTS):
        if not ui.root_child("esc_menu"):
            _click(ui, wait.appears(ui, "button_menu", under="menu_bar").ptr)
        b = wait.appears(ui, "button_load", under="esc_menu", timeout=5)
        if _live(ui, b.ptr):
            _click(ui, b.ptr)
            wait.appears(ui, "load_game_panel", timeout=5)
            wait.wait_until(lambda: ui.first("playthrough0", under="load_game_panel"), 5, "playthroughs listed")
            return
        # this opening of the menu has a dead Load button: close the menu and open it again
        _click(ui, wait.appears(ui, "button_resume", under="esc_menu").ptr)
        wait.gone(ui, "esc_menu", timeout=3)
        wait.root_children_stable(ui, ms=200)
    raise RuntimeError(f"the game menu's Load button did not respond in {MENU_ATTEMPTS} openings")


def _live(ui: UI, ptr: int) -> bool:
    """The game registers the cursor over the button (its hover state). Some openings of the esc menu (about a third
    in rapid tests, 2026-10-16) have a Load button that never reacts to the cursor nor to clicks, for the whole
    opening, while Save and Resume work: those openings are detected here and the menu is reopened."""
    p = ui.hover_probe(ptr)
    if p is None:
        return True
    move_to(*ui.comp(ptr).center)
    return wait.frames_until(lambda: ui.state_ptr(p[0]) in p[1], 20)


def pick_save(ui: UI, save: str) -> int:
    """The row of `save`: in the selected playthrough's list, else selecting each playthrough in turn (the save list
    is filled a moment after a playthrough is selected)."""
    _rows_settled(ui)
    row = _find_row(ui, save)
    if row is None:
        lst = ui.first("list_box", under="playthrough_list")
        pts = [p for p in (ui.children(lst) if lst else []) if (ui.id(p) or "").startswith("playthrough")]
        for p in pts:
            _click(ui, p)
            wait.wait_until(lambda: (ui.state(p) or "").startswith("selected"), 2, "playthrough selected")
            _rows_settled(ui)
            row = _find_row(ui, save)
            if row is not None:
                break
    if row is None:
        raise RuntimeError(f"save {save!r} not found in any playthrough")
    if not _scroll_into_view(ui, row):
        raise RuntimeError(f"save {save!r} could not be scrolled into view")
    return row


def _row_text(ui: UI, row: int, cid: str) -> str:
    c = ui.child(row, cid)
    return (ui.text(c) or "") if c else ""


def _rows_settled(ui: UI, ms: float = 300) -> list[tuple[int, str]]:
    """The save rows once the list has stopped changing: it is filled after the panel opens and can be rebuilt once
    more (its row components are then re-used for other saves)."""
    st = {"v": None, "t": 0.0}

    def probe():
        v = tuple(_rows(ui))
        now = time.perf_counter()
        if v != st["v"]:
            st["v"], st["t"] = v, now
            return None
        return list(v) if v and (now - st["t"]) * 1000 >= ms else None
    return wait.wait_until(probe, 10, f"save list unchanged for {ms:.0f} ms")


def _select_row(ui: UI, save: str) -> int:
    """Click the save's row until the game shows it (and only it) selected; returns the row."""
    for _ in range(3):
        row = pick_save(ui, save)
        _click(ui, row)
        ok = wait.wait_until(lambda: (ui.state(row) or "").startswith("selected"), 1.0, f"{save!r} row selected",
                             must=False)
        sel = [n for r, n in _rows_settled(ui) if (ui.state(r) or "").startswith("selected")]
        if ok and sel == [save]:
            return row
    raise RuntimeError(f"the row of {save!r} could not be selected")


def load(save: str, m: MemorySensor, ui: UI) -> float:
    """Load `save` from the campaign map (or the game menu). Returns seconds until the campaign was ready."""
    before = m.read().extras.get("model")
    t0 = time.perf_counter()
    with game_focus():
        open_load_panel(ui)
        row = _select_row(ui, save)
        turn = _row_text(ui, row, "turn")
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
    got = m.read().turn
    if turn.isdigit() and got != int(turn):
        raise RuntimeError(f"loaded turn {got}, but {save!r} is turn {turn}: a different save was loaded")
    return time.perf_counter() - t0


LOADING_PANELS = ("campaign",)       # the loading screen stays a root panel while the campaign HUD already exists


def wait_ready(m: MemorySensor, ui: UI, old_model) -> None:
    from assist.runner import players_turn

    # the old campaign goes away first (a reload can put the new model at the same address), then a new one appears
    if not wait.wait_until(lambda: not m.read().ok, 30, "old campaign unloaded", poll=0.02, must=False):
        print("WARNING: the campaign model never went away during the load", flush=True)
    wait.wait_until(lambda: m.read().ok, LOAD_TIMEOUT, "campaign model of the loaded save", poll=0.05)
    # Measured 2026-10-16: the HUD tree is built, then the game freezes ~12 s, then the loading screen ('campaign')
    # shows again for ~4 s over the live HUD. Ready = all of these at once.
    end = time.perf_counter() + LOAD_TIMEOUT
    while True:
        wait.wait_until(lambda: players_turn(ui)[0], LOAD_TIMEOUT, "End Turn shown and enabled", poll=0.02)
        wait.ui_live(ui, ms=1000, timeout=LOAD_TIMEOUT)      # the tree exists seconds before the game renders again
        wait.wait_until(lambda: not any(i in LOADING_PANELS for i in wait.root_children(ui)), LOAD_TIMEOUT,
                        "loading screen gone", poll=0.02)
        ids = wait.root_children_stable(ui, ms=500, timeout=30)
        if not any(i in LOADING_PANELS for i in ids) and players_turn(ui)[0]:
            return
        if time.perf_counter() > end:
            raise wait.WaitTimeout("the campaign never became ready after the load")


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
