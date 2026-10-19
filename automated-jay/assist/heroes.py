"""Heroes and the campaign camera: move a free hero into a lord's army the way the player does it by hand (select the
hero, right-click the lord's army flag, take the embed action in the Hero Actions panel), and bring a map label on
screen to click it.

Everything comes from memory and the game's UI tree; nothing is looked for on screen (verified 2026-10-16, 9.0.4):
  Lords & Heroes   top bar hud_campaign/bar_small_top/TabGroup/tab_units (state "selected" while the list is shown);
                   rows character_row_<character id> (id = u32 at character +0x110). A single click selects that
                   character without moving the camera; a double-click also pans the camera to it (eased, ~1.9 s).
  map labels       children of the root panel 3d_ui_parent, in screen pixels: label_<character id> (an army's flag;
                   a garrisoned lord's flag sits above the settlement) and label_settlement:<region key>.
  camera           bot/sensor/camera.py: eye and projection from memory, so a map position's pixel is known before
                   it is on screen.
  Hero Actions     HERO_ACTIONS (see below): opened by right-clicking the lord's flag with the hero selected; a hero
                   that cannot reach the lord this turn gets a move order instead (no panel) and joins later.

The camera is moved with WASD, closed-loop on the target's projected pixel, read back every rendered frame: the keys
are released as soon as the target is inside AIM, and the label is clicked once it is inside SAFE and has stopped
moving (tools/wait.py). A target that is already on screen costs no camera move at all.

    python -X utf8 -m assist.heroes "Balequint Marzqueek" "Ikit Claw"
"""
from __future__ import annotations
import math
import sys
import time

import pydirectinput

from bot.focus import game_focus, require_game_front
from bot.sensor.camera import GROUND_H, character_pos, read_camera as _read_camera
from bot.sensor.world import World, characters, find_player_faction
from tools import timing, wait
from tools.ui import click, double_click, move_to

FLAG_H = 2.6                 # army banner height above the lord's position (world units)
# screen area clear of the HUD where map clicks are safe: the minimap and the Lords & Heroes list start at x ~1636,
# the selected character's info panel ends at x ~285, the unit panel starts at y ~830 (1920x1080, UI scale 1).
# 2026-10-16: with the old right edge (1660) a Verminlord's flag label at x 1617..1667 passed, and the right-click
# landed on the minimap frame.
SAFE = (300, 140, 1600, 800)
AIM = (560, 300, 1340, 640)  # WASD steers the target into this box; the camera's coast after the release stays in SAFE
STILL_PX = 1.0               # a label moving less than this per frame (for STILL_FRAMES frames) can be clicked: a
STILL_FRAMES = 2             # click takes ~3 frames, so it lands within a few px of where it was aimed
WASD_MAX = 20.0              # map units: nearer targets are panned to with WASD, farther ones get a jump (jump_row).
                             # Measured 2026-10-16 (eye height ~12): WASD accelerates over ~0.4 s to ~6 px/frame
                             # (~17 map units/s) and coasts ~0.44 s / ~93 px after the release; a jump takes 1.6-1.8 s
                             # to < 1 px/frame at any distance (Lords & Heroes or Provinces row double-click, minimap)
PAN_TIMEOUT = 12.0           # s
PARK = (1700, 760)


def read_camera(s, timeout: float = 4.0):
    """The camera, waiting out moments when the camera block does not read as a campaign camera: the static
    pointer briefly leads elsewhere right after some UI actions (seen live 2026-10-16 after recruiting a lord
    and after an Escape that closed an army panel); it comes back on its own within a moment."""
    try:
        return _read_camera(s)
    except RuntimeError:
        return wait.wait_until(lambda: _read_camera(s), timeout, "camera block readable", poll=0.01)


def park() -> None:
    """Cursor off the map and off the panels (no wait: nothing reads the screen)."""
    move_to(*PARK)


# ------------------------------------------------------------------ Lords & Heroes list

def lords_row(ui, char_id: int):
    """The character's row in the Lords & Heroes list (opened and scrolled into view as needed), or None."""
    from .skills import _lords_row
    return _lords_row(ui, char_id)


def row_selected(ui, row: int) -> bool:
    return (ui.state(row) or "").startswith("selected")


def select_row(ui, char_id: int, what: str = "") -> int | None:
    """Select a character with a single click on its Lords & Heroes row (the camera stays where it is)."""
    row = lords_row(ui, char_id)
    if row is None:
        return None
    click(ui, row)
    wait.wait_until(lambda: row_selected(ui, row), 1.0, what or f"character {char_id} selected", must=False)
    return row


# ------------------------------------------------------------------ map labels and the camera

def map_label(ui, comp_id: str):
    """The map label (a child of 3d_ui_parent) as a Comp, or None when the game does not show it."""
    p = ui.root_child("3d_ui_parent")
    c = ui.child(p, comp_id, visible_only=True) if p else None
    return ui.comp(c) if c else None


def in_safe(k) -> bool:
    """The whole label, not just its centre, is clear of the HUD."""
    return k is not None and SAFE[0] <= k.x and k.x + k.w <= SAFE[2] and SAFE[1] <= k.y and k.y + k.h <= SAFE[3]


def _sane(k) -> bool:
    return -4000 < k.x < 6000 and -4000 < k.y < 6000 and k.w > 0 and k.h > 0


def _target_px(ui, cam, x: float, y: float, h: float, comp_id: str):
    """Where the target is on screen: its label when the game shows one, else the projection of (x, y, h).
    None when it is behind the camera."""
    k = map_label(ui, comp_id)
    if k is not None and _sane(k):
        return k.center
    return cam.project(x, y, h)


def _steer(cam, p, x: float, y: float) -> set[str]:
    """The WASD keys that move the camera toward the target (screen pixel p, or None when it is behind the camera:
    then from the ground direction in the camera's frame)."""
    if p is None:
        cx, cy = cam.ground_at_center()
        rx, ry = cam.right[0], cam.right[2]
        fx, fy = cam.fwd[0], cam.fwd[2]
        a = (x - cx) * rx + (y - cy) * ry
        b = (x - cx) * fx + (y - cy) * fy
        keys = {"w" if b > 0 else "s"}
        if abs(a) > 2.0:
            keys.add("d" if a > 0 else "a")
        return keys
    keys = set()
    if p[0] < AIM[0]:
        keys.add("a")
    elif p[0] > AIM[2]:
        keys.add("d")
    if p[1] < AIM[1]:
        keys.add("w")
    elif p[1] > AIM[3]:
        keys.add("s")
    return keys


def _settled(ui, comp_id: str, cam_px, timeout: float = 3.0):
    """Until the target stops moving on screen: its pixel (the label, else cam_px()) moved less than STILL_PX per
    frame for STILL_FRAMES frames. -> its label Comp (None when the game shows no label), or False on timeout."""
    st = {"prev": None, "n": 0}

    def probe():
        k = map_label(ui, comp_id)
        p = (k.x, k.y) if k is not None and _sane(k) else cam_px()
        prev, st["prev"] = st["prev"], p
        if p is not None and prev is not None and math.hypot(p[0] - prev[0], p[1] - prev[1]) < STILL_PX:
            st["n"] += 1
        else:
            st["n"] = 0
        if st["n"] >= STILL_FRAMES:
            return (k,)
        wait.next_frame(1, ui)
        return None
    r = wait.wait_until(probe, timeout, f"{comp_id} still on screen", poll=0, must=False)
    return r[0] if r else False


def province_row(ui, province: str):
    """The province's row in the Provinces list (top bar tab_regions; row_entry_<province key>), opened and scrolled
    into view as needed, or None."""
    from .build import _scroll_into_clip
    tab = ui.cached("tab_regions", under="bar_small_top")
    if tab is None:
        return None
    if not (ui.state(tab) or "").startswith("selected"):
        click(ui, tab)
    row = wait.wait_until(lambda: ui.first(f"row_entry_{province}"), 2.0, f"row_entry_{province} listed", must=False)
    if row is None or not _scroll_into_clip(ui, row, "Provinces list"):
        return None
    return row


def jump_row(ui, row) -> bool:
    """Double-click a Lords & Heroes row (centres on that character) or a Provinces row (centres on the province's
    capital): an eased camera move of 1.6-1.8 s whatever the distance, which also selects what the row stands for.
    Returns once the camera has started moving (or did not need to)."""
    if row is None:
        return False
    e0 = tuple(read_camera(ui.s).eye)
    double_click(*ui.comp(row).center, target=row)
    wait.wait_until(lambda: tuple(read_camera(ui.s).eye) != e0, 0.3, "camera starts moving", must=False)
    return True


def _far(cam, x: float, y: float, h: float) -> bool:
    """WASD would take longer than a jump: the target is more than WASD_MAX map units from the screen centre (or
    behind the camera)."""
    if cam.project(x, y, h) is None:
        return True
    cx, cy = cam.ground_at_center()
    return math.hypot(x - cx, y - cy) > WASD_MAX


_MP: dict = {}           # campaign model -> another human faction is in it (multiplayer)


def multiplayer(w: World) -> bool:
    """Another human faction is in the campaign (from memory: the player's diplomacy list, is_human)."""
    from bot.sensor.world import is_human
    m = w.s.model
    if m not in _MP:
        F = find_player_faction(w)
        rel = w.q(F + 0xDB8) if F else 0
        hit = False
        if rel:
            n, base = w.u32(rel + 4), w.q(rel + 8)
            for i in range(min(n, 4000)):
                try:
                    o = w.q(base + 0x78 * i + 0x28)
                    if o and o != F and is_human(w, o):
                        hit = True
                        break
                except Exception:
                    continue
        _MP.clear()
        _MP[m] = hit
    return _MP[m]


def pan_by_edge(w: World) -> bool:
    """Pan with the cursor at the screen edge instead of WASD: multiplayer has no WASD camera (player note
    2026-10-18: there the camera moves only by edge scrolling or the middle-button drag). strategy/automation.json
    "camera_pan": "auto" (default: edge in multiplayer, WASD otherwise), "edge" or "keys"."""
    try:
        import json as _json
        from bot import config as _cfg
        mode = _json.load(open(_cfg.STRATEGY_DIR / "automation.json", encoding="utf-8")).get("camera_pan", "auto")
    except Exception:
        mode = "auto"
    if mode in ("edge", "keys"):
        return mode == "edge"
    return multiplayer(w)


def _edge_cursor(dirs: set[str]) -> None:
    """The cursor on the screen edge (corner for a diagonal) that scrolls the camera toward dirs (w a s d); no
    directions: back to the middle of the map, which stops the scrolling."""
    import win32api
    from bot import config as _cfg
    W, H = _cfg.RESOLUTION
    x = 0 if "a" in dirs else W - 1 if "d" in dirs else W // 2
    y = 0 if "w" in dirs else H - 1 if "s" in dirs else H // 2
    win32api.SetCursorPos((x, y))


def bring_into_view(w: World, ui, x: float, y: float, comp_id: str, h: float = GROUND_H, jump=None):
    """Make the map label `comp_id` (of the thing at map position x, y, height h) clickable: inside SAFE and moving
    less than STILL_PX per frame. Returns (label Comp or None, jumped).
      already there      no input at all;
      far (> WASD_MAX)   jump() first when given (a row double-click: see jump_row). It changes the selection, so
                         `jumped` tells the caller to select again what it needs (the camera stays put then);
      near / after that  WASD, closed-loop: every frame the target's pixel is read (its label, or the camera
                         projection while the game shows no label) and the keys toward it are held until it is
                         inside AIM; once the camera has coasted to a stop the label must be inside SAFE (else steer
                         again).
    The game must be in front."""
    cam_px = lambda: read_camera(w.s).project(x, y, h)
    if in_safe(map_label(ui, comp_id)):
        k = _settled(ui, comp_id, cam_px, timeout=2.0)
        if k and in_safe(k):
            return k, False
    jumped = False
    t0 = time.perf_counter()
    if jump is not None and _far(read_camera(w.s), x, y, h):
        jumped = bool(jump())
        if jumped:
            k = _settled(ui, comp_id, cam_px, timeout=4.0)
            if k and in_safe(k):
                timing.wait_event(f"camera jump to {comp_id}", (time.perf_counter() - t0) * 1000, True, 0)
                return k, True
    held: set[str] = set()
    edge = pan_by_edge(w)
    end = time.perf_counter() + PAN_TIMEOUT
    frames = 0
    try:
        while time.perf_counter() < end:
            cam = read_camera(w.s)
            want = _steer(cam, _target_px(ui, cam, x, y, h, comp_id), x, y)
            if want:
                require_game_front()           # every frame while keys are down: an alt-tab stops the pan at once
            if edge:                           # multiplayer: the cursor at the screen edge toward the target
                if want != held:
                    _edge_cursor(want)
            else:
                for key in held - want:
                    pydirectinput.keyUp(key, _pause=False)
                for key in want - held:
                    pydirectinput.keyDown(key, _pause=False)
            held = want
            if held:
                frames += 1
                wait.next_frame(1, ui)
                continue
            k = _settled(ui, comp_id, cam_px)          # keys up: the camera coasts to a stop
            if k and in_safe(k):
                timing.wait_event(f"camera pan to {comp_id} ({frames} frames of keys)",
                                  (time.perf_counter() - t0) * 1000, True, frames)
                return k, jumped
            cam = read_camera(w.s)
            if not _steer(cam, _target_px(ui, cam, x, y, h, comp_id), x, y):
                break                                  # on target but the game shows no label (or it is covered)
    finally:
        if edge:
            if held:
                _edge_cursor(set())
        else:
            for key in held:
                pydirectinput.keyUp(key, _pause=False)
    timing.wait_event(f"camera pan to {comp_id}", (time.perf_counter() - t0) * 1000, False, frames)
    return None, jumped


# ------------------------------------------------------------------ heroes

def hero_movement(w: World, C: int) -> float | None:
    """Movement left this turn, 0..1, for a character that is NOT leading a force (a free hero).
    Decompiled action_points_remaining_percent (9.0.4) = remaining (vtable +0x40) / per-turn maximum (vtable +0x48).
    When [C+0x3B0] -> force is unset both come from the character itself: i32 C+0x30 = left, i32 C+0x3C = this
    turn's maximum. Verified live: a hero recruited this turn reads (0, 0, 3584000, 3584000) at C+0x30."""
    try:
        import struct
        left, _, _, mx = struct.unpack("<4i", w.pm.read_bytes(C + 0x30, 16))
        return max(0.0, min(1.0, left / mx)) if mx > 0 else None
    except Exception:
        return None


# Hero Actions (9.0.4): right-clicking a lord's flag with a hero selected opens the root panel agent_options, titled
# "Hero Actions": options_panel/stage2_approach/method_list/method/button_method, one card per action, with
# dy_method_name ("Increase Mobility" is the Warlock Engineer's embed action) and dy_target_name (the lord's name).
# The panel is offered also when the lord is out of reach this turn: the hero then walks as far as he can and joins
# on a later turn. The panel slides up from below the screen (~0.3 s); the first time after a load it shows a
# placeholder card for one frame (a pointer taken then never takes a click), so the card is clicked only once the
# same component has kept the same on-screen rectangle for 3 frames. Taking the card closes the panel in ~30 ms; the
# hero starts walking ~70 ms later and is embedded when he reaches the lord.
HERO_ACTIONS = "agent_options"
CARD_TRIES = 3                 # a click on the card that does not close the panel is repeated (re-aimed) this often
WALKING = 2                    # u32 character +0x88: 2 while the character walks, 1 at rest (it flips back exactly when
                               # the walk ends and the movement points are booked; checked live 2026-10-16)
WALK_TIMEOUT = 20.0            # s: a hero walking its whole movement for the turn took 4.5 s
LATE_PANEL_S = 1.0             # s: after the hero stopped, the Hero Actions panel is still awaited this long


def _embedded(w: World, C: int) -> int:
    try:
        e = w.q(C + 0x438)
        return w.q(w.q(e + 0x10) + 0x18) if e and w.q(e + 0x10) else 0
    except Exception:
        return 0


def walking(w: World, C: int) -> bool:
    """The character is walking right now (a move order being carried out)."""
    try:
        return w.u32(C + 0x88) == WALKING
    except Exception:
        return False


def _settled_card(ui, panel, timeout: float = 2.0):
    """The Hero Actions card (button_method) once it is clickable: fully on screen, the same component with the same
    rectangle for 3 frames. -> pointer or None."""
    W, H = 1920, 1080

    def read():
        b = ui.first("button_method", under=panel)
        if b is None:
            return None
        k = ui.comp(b)
        return b, k.x, k.y, k.w, k.h
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        v = wait.stable(read, n=3, timeout=max(0.05, end - time.perf_counter()), what="Hero Actions card still", ui=ui,
                        must=False)
        if v is None:
            return None
        b, x, y, kw, kh = v
        if x >= 0 and y >= 0 and x + kw <= W and y + kh <= H:
            return b
        wait.next_frame(1, ui)
    return None


def _take_card(ui, panel, lord_name: str) -> str | None:
    """Click the Hero Actions card for this lord until the panel closes. None when taken, else what went wrong (the
    panel is closed with its X then)."""
    for _ in range(CARD_TRIES):
        card = _settled_card(ui, panel)
        if card is None:
            break
        tgt = ui.first("dy_target_name", under=card)
        name = (ui.text(tgt) or "").strip() if tgt else ""
        if name and name != lord_name:
            _decline(ui, panel)
            return f"Hero Actions offered {name}, not {lord_name}"
        click(ui, card)
        if wait.gone(ui, panel, timeout=0.3, must=False, what="Hero Actions closed by the card"):
            return None
    if ui.effective_visible(panel):
        _decline(ui, panel)
    return "the Hero Actions card did not take the click"


def _decline(ui, panel) -> None:
    x = ui.first("button_decline", under=panel)
    if x is not None and ui.effective_visible(panel):
        click(ui, x)
        wait.gone(ui, panel, timeout=1.0, must=False, what="Hero Actions closed")


def move_into_army(hero_name, lord_name, log=print, ui=None, settle: bool = True) -> str:
    """Select the hero with a single click on his Lords & Heroes row, bring the lord's map flag (label_<lord id>) on
    screen, right-click it, then take the Hero Actions card (the embed action) and check that the hero set off.
    settle: wait until the walk has ended (the hero joined, or stopped with his movement used up); otherwise return
    once he is walking ("on the way") and let the caller wait (wait_until_stopped).
    hero_name / lord_name: a name, or a Character (bot/sensor/world.py), which is matched by pointer (names repeat)."""
    from bot.sensor.ui import UI
    from .army_builder import clear
    w = World(ui.s) if ui is not None else World()
    F = find_player_faction(w)
    everyone = characters(w, F)

    def find(x):
        if isinstance(x, str):
            return next((c for c in everyone if c.name == x), None)
        return next((c for c in everyone if c.ptr == x.ptr), None)
    hero, lord = find(hero_name), find(lord_name)
    hero_name = hero_name if isinstance(hero_name, str) else hero_name.name
    lord_name = lord_name if isinstance(lord_name, str) else lord_name.name
    if hero is None or lord is None:
        return f"{hero_name} or {lord_name} not found"
    if hero.embedded_force:
        return f"{hero_name} is already in an army"
    p0 = character_pos(w.pm, hero.ptr)
    lx, ly = character_pos(w.pm, lord.ptr)
    hid, lid = w.u32(hero.ptr + 0x110), w.u32(lord.ptr + 0x110)
    if ui is None:
        ui = UI(w.s)
        ui.find_root()
    flag_id = f"label_{lid}"
    set_off = lambda: _embedded(w, hero.ptr) or walking(w, hero.ptr) or character_pos(w.pm, hero.ptr) != p0
    with game_focus():
        clear(ui)
        if select_row(ui, hid, f"{hero_name} selected") is None:
            return f"{hero_name} not in the Lords & Heroes list"
        flag, jumped = bring_into_view(w, ui, lx, ly, flag_id, FLAG_H, jump=lambda: jump_row(ui, lords_row(ui, lid)))
        if jumped:                                 # the jump selected the lord: select the hero again (no camera move)
            select_row(ui, hid, f"{hero_name} selected")
            flag = map_label(ui, flag_id)
        if flag is None or not in_safe(flag):
            return f"could not bring {lord_name}'s flag on screen"
        click(ui, flag.ptr, right=True)
        panel = wait.wait_until(lambda: ui.root_child(HERO_ACTIONS) or (set_off() and -1), 2.0,
                                "Hero Actions panel (or the hero on the move)", must=False)
        if panel == -1:
            # the hero stirred first, but the panel can still come (2026-10-17, turn 73: the hero stirred at once,
            # the panel opened a moment later, was left unanswered and blocked End Turn): it is awaited until the
            # hero has stopped or joined, and a moment more
            wait.wait_until(lambda: ui.root_child(HERO_ACTIONS) or _embedded(w, hero.ptr) or not walking(w, hero.ptr),
                            WALK_TIMEOUT, "Hero Actions panel (or the walk over)", must=False)
            panel = wait.wait_until(lambda: ui.root_child(HERO_ACTIONS), LATE_PANEL_S, "Hero Actions panel, late",
                                    must=False)
        if panel:
            problem = _take_card(ui, panel, lord_name)
            if problem:
                park()
                return f"{hero_name}: {problem}"
        wait.wait_until(set_off, 1.0, f"{hero_name} on the move", must=False)
        park()
    if settle:
        wait_until_stopped(w, hero.ptr)
    late = ui.root_child(HERO_ACTIONS)
    if late:                                       # opened once the hero was in reach: take it now, never leave it
        with game_focus():
            problem = _take_card(ui, late, lord_name)
            park()
        if problem:
            return f"{hero_name}: {problem}"
        if settle:
            wait_until_stopped(w, hero.ptr)
    if _embedded(w, hero.ptr):
        return f"{hero_name} joined {lord_name}'s army"
    if character_pos(w.pm, hero.ptr) != p0 or walking(w, hero.ptr):
        return f"{hero_name} is on the way to {lord_name} (joins on arrival)"
    return f"{hero_name} did not move; check the game"


def wait_until_stopped(w: World, C: int, timeout: float = WALK_TIMEOUT) -> tuple[float, float]:
    """Until the character is no longer walking (u32 +0x88, see WALKING) or is embedded in an army. No input; returns
    at once for a character at rest. Returns the last position."""
    wait.wait_until(lambda: _embedded(w, C) or not walking(w, C), timeout, "character stopped walking", poll=0.005,
                    must=False, focus=False)
    return character_pos(w.pm, C)


def main() -> int:
    from bot.focus import return_to_terminal
    try:
        print(move_into_army(sys.argv[1], sys.argv[2]))
    finally:
        return_to_terminal()
    return 0


if __name__ == "__main__":
    sys.exit(main())
