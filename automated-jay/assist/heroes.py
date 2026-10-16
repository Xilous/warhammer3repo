"""Move a free hero into a lord's army, the way the player does it by hand:
select the hero, right-click the lord's army flag, pick the embed action in the Hero Actions panel.

Screen positions come from memory (bot/sensor/camera.py): character map positions and the camera, so
flags are found exactly instead of by looking for them. The camera is moved with WASD (ordinary input),
closed-loop on the camera position read back from memory.

Navigation uses the Lords & Heroes list: double-click centres on a character at a fixed zoom, single click
selects without moving the camera. WASD panning is the fallback.

Verified 2026-10-16 (9.0.4) on a lord garrisoned in a settlement: the army is targeted by its banner
above the settlement (world height ~2.6 over the lord's position; hover tooltip "Ikit Claw - Your army").
Right-click opens "Hero Actions"; the Warlock Engineer's embed action is listed as "Increase Mobility".
A hero that cannot reach the lord this turn gets a move order instead and joins on a later turn.

    python -X utf8 -m assist.heroes "Balequint Marzqueek" "Ikit Claw"
"""
from __future__ import annotations
import sys
import time

import pydirectinput
import win32api
from PIL import Image

from bot import config
from bot.focus import game_focus
from bot.sensor.camera import character_pos, read_camera as _read_camera
from bot.sensor.world import World, characters, find_player_faction
from tools.ui import click_at, double_click, grab, hold_key, move_to, wheel

FLAG_H = 2.6                 # army banner height above the lord's position (world units)
HERO_H = 0.7
SAFE = (260, 140, 1660, 800)  # screen area clear of the HUD where map clicks are safe
HERO_ACTIONS_BOX_1280 = (575, 581, 760, 606)
HERO_ACTION_FIRST_CARD = (982, 978)

# Lords & Heroes list (top-bar button). Double-clicking a row selects that character and centres the
# camera on it at a fixed zoom (eye height ~11.5, same pitch every time); a single click selects it
# without moving the camera. Embedded heroes are listed indented under their lord.
LORDS_BUTTON = (1772, 22)
LIST_HEADER = (1640, 258, 1910, 290)
ROW0_Y, ROW_PITCH, MAX_ROWS = 354, 79, 9
NAME_X = {False: 1717, True: 1750}
PORTRAIT_X = {False: 1648, True: 1681}


def read_camera(s, timeout: float = 4.0):
    """The camera, waiting out moments when the camera block does not read as a campaign camera: the static
    pointer briefly leads elsewhere right after some UI actions (seen live 2026-10-16 after recruiting a lord
    and after an Escape that closed an army panel); it comes back on its own within a moment."""
    end = time.monotonic() + timeout
    while True:
        try:
            return _read_camera(s)
        except RuntimeError:
            if time.monotonic() > end:
                raise
            time.sleep(0.25)


def _on_screen(p) -> bool:
    return p is not None and SAFE[0] <= p[0] <= SAFE[2] and SAFE[1] <= p[1] <= SAFE[3]


def pan_to(w: World, x: float, y: float, tries: int = 12) -> bool:
    """Hold WASD until the camera's centre ground point is near (x, y). Game must be focused."""
    for _ in range(tries):
        cam = read_camera(w.s)
        if _on_screen(cam.project(x, y)) and _on_screen(cam.project(x, y, FLAG_H)):
            return True
        cx, cy = cam.ground_at_center()
        dx, dy = x - cx, y - cy
        for key, d in (("d" if dx > 0 else "a", abs(dx)), ("w" if dy > 0 else "s", abs(dy))):
            if d < 1.0:
                continue
            hold_key(key, min(1.5, max(0.08, d / 22.0)))
        time.sleep(0.5)
    cam = read_camera(w.s)
    return _on_screen(cam.project(x, y))


def _double_click(x: int, y: int) -> None:
    double_click(x, y)
    time.sleep(2.2)


def open_lords_list() -> bool:
    from .skills import _tmpl, similar
    t = _tmpl("lords_list_header")
    if similar(grab().crop(LIST_HEADER), t) > 0.8:
        return True
    click_at(*LORDS_BUTTON)
    time.sleep(1.2)
    return similar(grab().crop(LIST_HEADER), t) > 0.8


def _park() -> None:
    move_to(1700, 760)
    time.sleep(0.4)


BAR_FRAME_X, BAR_FILL_X = 1882, 1885


def list_rows(ui=None) -> list[tuple[int, bool, float]]:
    """(y, indented, movement left 0..1) for each row of the open Lords & Heroes list that is on screen, top to bottom.

    Rows come from the UI tree (character_row_<character id> under the list's list_clip), not from pixels: the
    old pixel test (left portrait slot dark = indented) read a free hero's top-level row as indented. A row is
    indented (a hero embedded in the army above it) when its indent_parent child sits to the right of the row
    (+30 px; such rows also have a "vline" connector child). Movement left is the orange fill of the vertical bar
    on the right of the row (a bronze frame that is always drawn, filled from the bottom as movement remains)."""
    import numpy as np
    if ui is None:
        from bot.sensor.ui import UI
        ui = UI()
    rows = []
    for c, ids in ui.walk():
        if not ids[-1].startswith("character_row_") or "list_clip" not in ids:
            continue
        clip = next((p for p in _ancestors(ui, c) if ui.id(p) == "list_clip"), None)
        k = ui.comp(c)
        cy = k.y + k.h / 2
        if clip is not None:
            cl = ui.comp(clip)
            if not cl.y <= cy <= cl.y + cl.h:
                continue                              # scrolled out of the list window
        kids = {ui.id(x): x for x in ui.children(c)}
        ip = kids.get("indent_parent")
        indented = ip is not None and ui.comp(ip).x - k.x > 10
        rows.append((int(cy), indented))
    rows.sort()
    if not rows:
        return []
    _park()
    img = np.asarray(grab()).astype(int)
    out = []
    for y, indented in rows:
        frame = img[y - 24:y + 24, BAR_FRAME_X]
        bronze = (frame[:, 0] > 115) & (frame[:, 0] < 165) & (frame[:, 1] > 70) & (frame[:, 1] < 105) \
            & (frame[:, 2] > 35) & (frame[:, 2] < 75)
        move = 0.0
        if bronze.sum() >= 12:
            ys = np.nonzero(bronze)[0]
            fill = img[y - 24 + ys.min():y - 24 + ys.max() + 1, BAR_FILL_X]
            orange = (fill[:, 0] > 140) & (fill[:, 1] > 90) & (fill[:, 2] < 30)
            move = round(float(orange.mean()), 2)
        out.append((y, indented, move))
    return out


def _ancestors(ui, c: int, limit: int = 12):
    for _ in range(limit):
        c = ui.parent(c)
        if not c:
            return
        yield c


def _list_signature():
    import numpy as np
    return np.asarray(grab().crop((1640, 300, 1910, 300 + ROW_PITCH * MAX_ROWS)).convert("L").resize((54, 140)), dtype=float)


def scroll_list(notches: int) -> bool:
    """Scroll the Lords & Heroes list (negative = down). Returns False when nothing moved."""
    import numpy as np
    before = _list_signature()
    move_to(1780, ROW0_Y + ROW_PITCH)
    time.sleep(0.2)
    wheel(1780, ROW0_Y + ROW_PITCH, notches)
    _park()
    return float(np.abs(_list_signature() - before).mean()) > 2.0


def identify_rows(w: World, F: int, want: set[str] | None = None) -> dict[str, tuple[int, int, bool]]:
    """name -> (scroll step, row y, indented). Double-clicks each top-level row and matches the camera
    centre to character positions (indented rows are embedded heroes, which share their lord's spot).
    Scrolls the list down when the wanted names are not all visible. Leaves the list scrolled to top."""
    chars = characters(w, F)
    pos = {c.name: character_pos(w.pm, c.ptr) for c in chars}
    out: dict[str, tuple[int, int, bool]] = {}
    step = 0
    while True:
        for y, ind, _move in list_rows():
            if ind:
                continue
            _double_click(NAME_X[ind], y)
            _park()
            cx, cy = read_camera(w.s).ground_at_center()
            best = min(pos, key=lambda n: (pos[n][0] - cx) ** 2 + (pos[n][1] - cy) ** 2)
            if (pos[best][0] - cx) ** 2 + (pos[best][1] - cy) ** 2 < 4.0 and best not in out:
                out[best] = (step, y, ind)
        if want is not None and want <= set(out):
            break
        if step >= 20 or not scroll_list(-3):
            break
        step += 1
    while step > 0 and scroll_list(3):
        step -= 1
    return out


def goto_row(step: int) -> None:
    for _ in range(step):
        scroll_list(-3)


def pan_until_visible(w: World, ui, x: float, y: float, comp_id: str, tries: int = 14):
    """Pan the camera toward map point (x, y) until the UI component `comp_id` (a map label) sits in the
    safe screen area. Returns the component or None. Game must be focused."""
    def visible():
        for c, ids in ui.walk():
            if ids[-1] == comp_id:
                k = ui.comp(c)
                cx, cy = k.center
                if SAFE[0] <= cx <= SAFE[2] and SAFE[1] <= cy <= SAFE[3]:
                    return k
        return None
    for _ in range(tries):
        k = visible()
        if k is not None:
            return k
        cx, cy = read_camera(w.s).ground_at_center()
        dx, dy = x - cx, y - cy
        for key, d in (("d" if dx > 0 else "a", abs(dx)), ("w" if dy > 0 else "s", abs(dy))):
            if d < 1.0:
                continue
            hold_key(key, min(1.5, max(0.08, d / 22.0)))
        time.sleep(0.5)
    return visible()


def hero_actions_open() -> bool:
    from .skills import _tmpl, similar
    t = Image.open(config.ROOT / "assist" / "templates" / "hero_actions_header_1280.png")
    live = grab().resize((1280, 720)).crop(HERO_ACTIONS_BOX_1280)
    return similar(live, t) > 0.8


def hero_movement(w: World, C: int) -> float | None:
    """Movement left this turn, 0..1, for a character that is NOT leading a force (a free hero).
    Decompiled action_points_remaining_percent (9.0.4): when [C+0x3B0] -> force is unset the game uses the
    character's own action points: i32 C+0x3C = left, i32 C+0x30 = this turn's maximum. A hero recruited this
    turn has 0 left."""
    try:
        import struct
        mx, _, _, left = struct.unpack("<4i", w.pm.read_bytes(C + 0x30, 16))
        return max(0.0, min(1.0, left / mx)) if mx > 0 else None
    except Exception:
        return None


def move_into_army(hero_name, lord_name, log=print) -> str:
    """Select the hero by double-clicking his Lords & Heroes row, pan until the lord's map flag component
    (label_<lord id>) is on screen, right-click it, then take the Hero Actions embed card.
    hero_name / lord_name: a name, or a Character (bot/sensor/world.py), which is matched by pointer (names repeat)."""
    from bot.sensor.ui import UI
    from .army_builder import clear, first, park
    w = World()
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
    hx, hy = character_pos(w.pm, hero.ptr)
    lx, ly = character_pos(w.pm, lord.ptr)
    hid, lid = w.u32(hero.ptr + 0x110), w.u32(lord.ptr + 0x110)
    ui = UI(w.s)
    ui.find_root()
    with game_focus():
        clear(ui)
        open_lords_list()
        row = first(ui, f"character_row_{hid}")
        if row is None:
            return f"{hero_name} not in the Lords & Heroes list"
        _double_click(*ui.comp(row).center)
        park()
        flag = pan_until_visible(w, ui, lx, ly, f"label_{lid}")
        if flag is None:
            return f"could not bring {lord_name}'s flag on screen"
        click_at(*flag.center, right=True)
        time.sleep(2.0)
        card = None
        for c, ids in ui.walk():
            if "hero_actions" in "/".join(ids).lower() or (ids[-1].startswith("CcoAgentAction") if ids else False):
                card = c
        if hero_actions_open():
            click_at(*HERO_ACTION_FIRST_CARD)          # the embed action
            time.sleep(2.0)
        park()
    for c in characters(w, F):
        if c.ptr == hero.ptr:
            if c.embedded_force:
                return f"{hero_name} joined {lord_name}'s army"
            nx, ny = character_pos(w.pm, c.ptr)
            if (nx, ny) != (hx, hy):
                return f"{hero_name} is on the way to {lord_name} (joins on arrival)"
    return f"{hero_name} did not move; check the game"


def main() -> int:
    print(move_into_army(sys.argv[1], sys.argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
