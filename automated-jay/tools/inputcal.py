"""Calibrate the input primitives against the game: how little delay does it need to register input?

Every trial is verified in the UI tree or in memory, never by eye. Harmless targets only: the tabs of the top-right
bar (Lords & Heroes / Regions: the clicked tab's state becomes "selected"), the technology panel hotkey, Lords &
Heroes rows (a double-click centres the camera), and focus switches.

    python -X utf8 -m tools.inputcal hover [N]                 # frames / ms from cursor arrival to the hover state
    python -X utf8 -m tools.inputcal click N HOVER HOLD        # N tab clicks; HOVER = frames before the button goes
                                                               # down, or "state" (wait for the hover state); HOLD =
                                                               # frames between down and up
    python -X utf8 -m tools.inputcal key N HOLD                # N presses of the tech hotkey (opens / closes the panel)
    python -X utf8 -m tools.inputcal dclick N GAP HOLD         # N double-clicks on Lords & Heroes rows (camera moves)
    python -X utf8 -m tools.inputcal focus N FRAMES            # raise the game from the terminal, click after FRAMES

A frame is one UI update (tools/wait.py next_frame: the root's ms stamp at +0x334 changing, about 330/s here).
"""
from __future__ import annotations
import statistics
import sys
import time

import pydirectinput
import win32api
import win32con

from bot.focus import game_focus, return_to_terminal
from bot.sensor.memory import MemorySensor
from bot.sensor.ui import UI
from tools import wait

pydirectinput.PAUSE = 0
NEUTRAL = (1400, 700)            # open map, nothing clickable that matters (only hovered)
TABS = ("tab_regions", "tab_units")


def _frames_until(pred, max_frames: int = 200, ui=None) -> tuple[int, float] | None:
    """(frames, ms) until pred() holds, counting UI frames; None when it never does."""
    ui = ui
    t0 = time.perf_counter()
    r = ui.find_root()
    rb = ui.rb
    last = rb(r + 0x334, 4)
    frames = 0
    while frames <= max_frames:
        if pred():
            return frames, (time.perf_counter() - t0) * 1000
        cur = rb(r + 0x334, 4)
        if cur != last:
            frames += 1
            last = cur
        else:
            time.sleep(0.0003)
    return None


def _park(ui) -> None:
    win32api.SetCursorPos(NEUTRAL)
    wait.next_frame(3, ui)


def hover(ui: UI, n: int = 30) -> None:
    tabs = [ui.first(t) for t in TABS]
    res = []
    with game_focus():
        for i in range(n):
            t = tabs[i % 2]
            _park(ui)
            before = ui.state_ptr(t)
            win32api.SetCursorPos(ui.comp(t).center)
            r = _frames_until(lambda: ui.state_ptr(t) != before, ui=ui)
            res.append(r)
        _park(ui)
    return_to_terminal()
    ok = [r for r in res if r]
    print(f"hover: {len(ok)}/{n} registered; frames {sorted(f for f, _ in ok)}")
    if ok:
        ms = [m for _, m in ok]
        print(f"  ms: median {statistics.median(ms):.1f}, max {max(ms):.1f}")


def _click_raw(ui, t: int, hover_frames, hold: int, right: bool = False) -> None:
    down, up = ((win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP) if right
                else (win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP))
    before = ui.state_ptr(t)
    win32api.SetCursorPos(ui.comp(t).center)
    if hover_frames == "state":
        _frames_until(lambda: ui.state_ptr(t) != before, max_frames=12, ui=ui)
    elif hover_frames:
        wait.next_frame(int(hover_frames), ui)
    win32api.mouse_event(down, 0, 0, 0, 0)
    if hold:
        wait.next_frame(hold, ui)
    win32api.mouse_event(up, 0, 0, 0, 0)


def click(ui: UI, n: int, hover_frames, hold: int) -> None:
    tabs = {name: ui.first(name) for name in TABS}
    sel = lambda name: (ui.state(tabs[name]) or "").startswith("selected")
    fails, lat = 0, []
    with game_focus():
        cur = next((nm for nm in TABS if sel(nm)), TABS[1])
        for i in range(n):
            target = TABS[0] if cur == TABS[1] else TABS[1]
            _park(ui)
            t0 = time.perf_counter()
            _click_raw(ui, tabs[target], hover_frames, hold)
            r = _frames_until(lambda: sel(target), max_frames=60, ui=ui)
            if r is None:
                fails += 1
                print(f"  trial {i}: click on {target} NOT registered", flush=True)
                _park(ui)
                _click_raw(ui, tabs[target], 6, 2)           # put the state back with a slow click
                if wait.wait_until(lambda: sel(target), 1.0, "recovery click", must=False):
                    cur = target
                continue
            lat.append((time.perf_counter() - t0) * 1000)
            cur = target
        _park(ui)
    return_to_terminal()
    print(f"click hover={hover_frames} hold={hold}: {n - fails}/{n} ok; click-to-selected median "
          f"{statistics.median(lat) if lat else 0:.1f} ms, max {max(lat) if lat else 0:.1f} ms")


def key_test(ui: UI, n: int, hold: int, k: str = "8") -> None:
    """The tech hotkey opens the technology panel (it does not close it): each trial closes the panel with its OK
    button first (not counted), waits until the root panels are settled, then presses the key."""
    is_open = lambda: ui.root_child("technology_panel") is not None
    fails = 0
    lat = []
    with game_focus():
        _park(ui)
        for i in range(n):
            if is_open():
                b = ui.first("button_ok", under="technology_panel")
                _click_raw(ui, b, "state", 1)
                wait.wait_until(lambda: not is_open(), 3, "technology panel closed")
                _park(ui)
            wait.root_children_stable(ui, ms=100, timeout=3)
            t0 = time.perf_counter()
            pydirectinput.keyDown(k, _pause=False)
            if hold:
                wait.next_frame(hold, ui)
            pydirectinput.keyUp(k, _pause=False)
            r = _frames_until(is_open, max_frames=300, ui=ui)
            if r is None:
                fails += 1
                print(f"  trial {i}: key {k} NOT registered", flush=True)
                continue
            lat.append((time.perf_counter() - t0) * 1000)
        if is_open():
            _click_raw(ui, ui.first("button_ok", under="technology_panel"), "state", 1)
            wait.wait_until(lambda: not is_open(), 3, "technology panel closed", must=False)
        _park(ui)
    return_to_terminal()
    print(f"key {k} hold={hold}: {n - fails}/{n} ok; key to panel median {statistics.median(lat) if lat else 0:.1f} ms")


def dclick(ui: UI, n: int, gap: int, hold: int) -> None:
    from bot.sensor.camera import read_camera
    from bot.sensor.world import World, characters, find_player_faction
    m = ui.s
    tab = ui.first("tab_units")
    if not (ui.state(tab) or "").startswith("selected"):
        with game_focus():
            _click_raw(ui, tab, "state", 1)
            wait.wait_until(lambda: (ui.state(tab) or "").startswith("selected"), 1, "Lords & Heroes tab")
            wait.wait_until(lambda: any(i.startswith("character_row_") for _c, i, _r in ui.nodes()), 2,
                            "Lords & Heroes rows")
    w = World(m)
    F = find_player_faction(w)
    chars = {w.u32(c.ptr + 0x110): c for c in characters(w, F)}
    rows = []
    for c, i, _r in ui.nodes():
        if i.startswith("character_row_") and ui.in_clip(c):
            cid = int(i.rsplit("_", 1)[1])
            if cid in chars:
                rows.append((c, cid))
    from bot.sensor.camera import character_pos
    pos = {cid: character_pos(ui.pm, chars[cid].ptr) for _r, cid in rows}
    far = []
    for r, cid in rows:                       # two rows whose characters stand far apart
        if all(((pos[cid][0] - pos[c2][0]) ** 2 + (pos[cid][1] - pos[c2][1]) ** 2) ** 0.5 > 20 for _r2, c2 in far):
            far.append((r, cid))
    rows = far[:2]
    if len(rows) < 2:
        print("need two Lords & Heroes rows on screen for characters standing apart")
        return
    print("rows", [(cid, pos[cid]) for _r, cid in rows])
    fails = 0
    lat = []
    with game_focus():
        for i in range(n):
            row, cid = rows[i % 2]
            x, y = character_pos(ui.pm, chars[cid].ptr)
            _park(ui)
            cam0 = read_camera(m).ground_at_center()
            t0 = time.perf_counter()
            win32api.SetCursorPos(ui.comp(row).center)
            wait.next_frame(2, ui)
            for j in range(2):
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                if hold:
                    wait.next_frame(hold, ui)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                if j == 0 and gap:
                    wait.next_frame(gap, ui)
            near = lambda: (lambda g: ((g[0] - x) ** 2 + (g[1] - y) ** 2) ** 0.5 < 8.0)(
                read_camera(m).ground_at_center())
            moved = wait.wait_until(near, 2.0, "camera on the character", must=False)
            if not moved:
                fails += 1
                print(f"  trial {i}: double-click on row {cid} did not centre the camera "
                      f"(camera {cam0} -> {read_camera(m).ground_at_center()}, char {x:.1f},{y:.1f})", flush=True)
                continue
            cam = wait.camera_settled(m, timeout=3, must=False)
            lat.append((time.perf_counter() - t0) * 1000)
        _park(ui)
    return_to_terminal()
    print(f"dclick gap={gap} hold={hold}: {n - fails}/{n} ok; double-click to camera settled median "
          f"{statistics.median(lat) if lat else 0:.0f} ms, max {max(lat) if lat else 0:.0f} ms")


def focus(ui: UI, n: int, frames: int) -> None:
    import win32gui
    from bot.focus import _raise, game_hwnd
    tabs = {name: ui.first(name) for name in TABS}
    sel = lambda name: (ui.state(tabs[name]) or "").startswith("selected")
    fails = 0
    lat = []
    g = game_hwnd()
    for i in range(n):
        return_to_terminal()
        cur = next((nm for nm in TABS if sel(nm)), TABS[1])
        target = TABS[0] if cur == TABS[1] else TABS[1]
        time.sleep(0.3)                                   # the terminal really is in front for a while
        t0 = time.perf_counter()
        if not _raise(g):
            print("could not raise the game")
            continue
        t_raised = time.perf_counter()
        if frames:
            wait.next_frame(frames, ui)
        _click_raw(ui, tabs[target], "state", 1)
        if wait.wait_until(lambda: sel(target), 1.0, "tab selected", must=False):
            lat.append(((t_raised - t0) * 1000, (time.perf_counter() - t_raised) * 1000))
        else:
            fails += 1
            print(f"  trial {i}: click right after the raise NOT registered", flush=True)
    win32api.SetCursorPos(NEUTRAL)
    return_to_terminal()
    print(f"focus frames={frames}: {n - fails}/{n} ok; raise ms median "
          f"{statistics.median(a for a, _ in lat) if lat else 0:.0f}, raise->selected median "
          f"{statistics.median(b for _, b in lat) if lat else 0:.0f} ms")


def main() -> int:
    a = sys.argv[1:]
    ui = UI(MemorySensor())
    cmd = a[0]
    if cmd == "hover":
        hover(ui, int(a[1]) if len(a) > 1 else 30)
    elif cmd == "click":
        h = a[2] if a[2] == "state" else int(a[2])
        click(ui, int(a[1]), h, int(a[3]))
    elif cmd == "key":
        key_test(ui, int(a[1]), int(a[2]), a[3] if len(a) > 3 else "8")
    elif cmd == "dclick":
        dclick(ui, int(a[1]), int(a[2]), int(a[3]))
    elif cmd == "focus":
        focus(ui, int(a[1]), int(a[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
