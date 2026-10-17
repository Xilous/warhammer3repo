"""Tech automation: when research is idle, queue the next beeline target; after the beeline,
the cheapest remaining tech.

Stateless by design. Verified game behaviour (9.0.4):
  - clicking a tech queues it plus its missing prerequisites and REPLACES any previous queue
  - clicking a tech that is already queued TOGGLES the queue off (current research keeps going)
  - Shift-click does not append
  (re-checked in memory, 2026-10-16: clicking a queued locked tech re-targets the queue to it; clicking
  the tech being researched CANCELS research and the queue; Plans Within Plans and everything behind it
  cannot be queued while Record Effective Recipes is unresearched: the click is ignored.)
So the step only acts when the HUD says research is idle (nothing queued), clicks targets in order,
and stops at the first one that shows a queue badge (hourglass + turns) after the click. Already
researched targets show no badge and are skipped. Manual research by the player is handled the same way.

Screen geometry (1920x1080, UI scale 1, verified 2026-10-16 on 9.0.4):
  tech label centre, panel scrolled fully left:  x = 189 + 267.3 * tier,  y = 262.5 + 66.9 * indent
  panel scrolled fully right shifts everything left by 858 px
  idle badge: yellow "!" on the Technology button of the end-turn ring, around (1733, 863)

Default path (`run`): research state from memory, panel driven through the UI tree (see the
"UI-tree version" section below). The screenshot version above is kept as `run_screen` for manual use only:
the turn-start step never falls back to it (fixed coordinates click blindly when the layout is not as expected).

    python -X utf8 -m assist.tech status        # memory: what is being researched, what would be clicked
    python -X utf8 -m assist.tech run           # queue research if idle (raises the game briefly)
    python -X utf8 -m assist.tech run_screen    # the old screenshot version
    python -X utf8 -m assist.tech plan          # print the click order
"""
from __future__ import annotations

from bot import config
import json
import sys
import time
from dataclasses import dataclass

import numpy as np
import pydirectinput
import win32api
import win32con
from PIL import Image

from . import gamedata as gd
from bot.focus import game_focus
from tools import wait
from tools.ui import click, click_at, drag, grab, move_to, press

FACTION = "wh2_main_skv_clan_skryre"
NODE_SET = "skv_mil"
TECH_HOTKEY = "8"
CLOSE_BUTTON = (960, 1042)
PARK = (960, 1062)               # neutral cursor spot for before/after captures
X0, DX, Y0, DY = 189.0, 267.3, 262.5, 66.9
SCROLL_RIGHT_SHIFT = 858
VISIBLE_X = (60, 1860)
THUMB_ROW = 994
IDLE_BADGE_BOX = (1718, 848, 1748, 878)
BADGE_MIN = 25                   # tan hourglass pixels in a node's badge box when queued/available


@dataclass(frozen=True)
class Node:
    key: str
    name: str
    tier: int
    indent: int
    rp: int


def nodes() -> dict[str, Node]:
    loc = gd.loc()
    out = {}
    for r in gd._load("technology_nodes_tables"):
        if r["technology_node_set"] != NODE_SET or r["faction_key"] not in ("", FACTION):
            continue
        k = r["technology_key"]
        out[k] = Node(k, loc.get("technologies_onscreen_name_" + k, k), int(r["tier"]), int(r["indent"]),
                      int(float(r["research_points_required"] or 0)))
    return out


def click_order() -> list[str]:
    """Beeline targets in the guide's click order (first appearance in the expanded order), then every
    other tech cheapest first."""
    b = json.load(open(config.BEELINE_FILE, encoding="utf-8"))
    targets = set(b["targets"])
    first = [k for k in (json.load(open(config.STRATEGY_DIR / "automation.json", encoding="utf-8"))
                         .get("tech", {}).get("first") or [])]           # the player's own "research these first"
    order = first + [t for t in b["order"] if t in targets and t not in first]
    ns = nodes()
    rest = sorted((k for k in ns if k not in order), key=lambda k: (ns[k].rp, ns[k].tier, ns[k].indent))
    return order + rest


# ------------------------------------------------------------------ screen reading

def research_idle(img: Image.Image | None = None) -> bool:
    a = np.asarray((img or grab()).crop(IDLE_BADGE_BOX)).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return int(((r > 200) & (g > 160) & (b < 100)).sum()) > 40


def tech_panel_open(img: Image.Image | None = None) -> bool:
    """The panel title plate and the scrollbar row are only there with the panel open."""
    a = np.asarray((img or grab()).crop((60, THUMB_ROW - 1, 1860, THUMB_ROW + 1))).astype(int)
    green = (a[..., 1] > 120) & (a[..., 0] < 120) & (a[..., 1] - a[..., 0] > 40)
    return int(green.sum()) >= 2


def thumb_span(img: Image.Image) -> tuple[int, int] | None:
    row = np.asarray(img).astype(int)[THUMB_ROW]
    xs = np.where((row[:, 1] > 120) & (row[:, 0] < 120) & (row[:, 1] - row[:, 0] > 40))[0]
    return (int(xs.min()), int(xs.max())) if len(xs) >= 2 else None


def node_badge(img: Image.Image, x: int, y: int) -> int:
    """Tan hourglass pixels in the badge box at the top-right of a tech label centred at (x, y)."""
    a = np.asarray(img.crop((x + 52, y - 42, x + 108, y - 6))).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return int(((r > 150) & (g > 120) & (b < 140) & (r - b > 40)).sum())


# ------------------------------------------------------------------ panel actions (game must be focused)

class Panel:
    def __init__(self) -> None:
        self.side: str | None = None

    def open(self) -> None:
        press(TECH_HOTKEY)
        time.sleep(2.0)
        if not tech_panel_open():
            raise RuntimeError("technology panel did not open")
        self.side = None

    def close(self) -> None:
        click_at(*CLOSE_BUTTON)
        time.sleep(1.0)

    def scroll(self, side: str) -> None:
        if self.side == side:
            return
        span = thumb_span(grab())
        if span is None:
            raise RuntimeError("scrollbar not found")
        cx = (span[0] + span[1]) // 2
        drag(cx, THUMB_ROW + 2, 5 if side == "left" else 1915, THUMB_ROW + 2)
        self.side = side

    def position(self, n: Node) -> tuple[int, int]:
        x = X0 + DX * n.tier
        y = Y0 + DY * n.indent
        if x <= VISIBLE_X[1]:
            self.scroll("left")
        else:
            self.scroll("right")
            x -= SCROLL_RIGHT_SHIFT
        return int(x), int(y)

    def try_queue(self, n: Node) -> bool:
        """Only call while research is idle (nothing queued), or the click may toggle a queue off."""
        x, y = self.position(n)
        click_at(x, y)
        move_to(*PARK)
        time.sleep(1.0)
        return node_badge(grab(), x, y) >= BADGE_MIN


# ------------------------------------------------------------------ the automation step (screen version)

def run_screen(log=print) -> str:
    """Older screenshot version (fixed geometry + queue-badge pixels). Manual use only, never a fallback."""
    if not research_idle():
        return "research already running"
    ns = nodes()
    with game_focus():
        panel = Panel()
        panel.open()
        try:
            for key in click_order():
                n = ns[key]
                if panel.try_queue(n):
                    log(f"tech: queued {n.name}")
                    result = f"queued {n.name}"
                    break
            else:
                result = "nothing left to research"
        finally:
            panel.close()
    time.sleep(0.8)
    if result.startswith("queued") and research_idle():
        result += " (WARNING: research still shows idle)"
    return result


# ------------------------------------------------------------------ memory (verified 9.0.4)
#
# T = [player faction + 0xFD8] is the faction's technology manager.
#   [T+0x28]          entry being researched (0 when idle); researching iff non-null and u32 [E+8] == 2
#   [T+0x30]          entry last clicked as research target. Set on every click, even one the game rejects
#                     (so it can be non-null while research is idle); 0 after research is cancelled.
#                     The queued chain itself is not stored in T (first 0x1000 bytes), the faction (0x3000)
#                     or the entries: a click that re-targets the queue changes only T+0x28/T+0x30.
#   u32 T+0x3C        number of researched techs; T+0x38 cap / T+0x3C count / [T+0x40] array of entries
#   T+0xC / [T+0x10]  tech sets: count / array -> set A; rows: count u32 A+4, array [A+8], stride 0x10;
#                     row R: count u32 R+4, entries [R+8], stride 0x80
#   entry E           key = string object at [[E]+0x50]+8; state u32 E+8 (STATE_*); byte E+0x78 is 0
#                     for every node of the player's tree

TECH_MANAGER = 0xFD8
STATE_RESEARCHED, STATE_RESEARCHING, STATE_AVAILABLE, STATE_LOCKED = 0, 2, 3, 4
STATE_NAMES = {0: "researched", 2: "researching", 3: "available", 4: "locked"}


@dataclass(frozen=True)
class TechEntry:
    key: str
    state: int
    flag78: int
    ptr: int


def _entry_key(w, e: int) -> str | None:
    from bot.sensor.world import string_object
    return string_object(w.pm, w.q(w.q(e) + 0x50) + 8)


def tech_manager(w) -> int:
    from bot.sensor.world import find_player_faction
    F = find_player_faction(w)
    if not F:
        raise RuntimeError("player faction not found")
    T = w.q(F + TECH_MANAGER)
    if not T:
        raise RuntimeError("technology manager not found")
    return T


def tech_entries(w, T: int) -> dict[str, TechEntry]:
    out: dict[str, TechEntry] = {}
    n_sets = w.u32(T + 0xC)
    if not 0 < n_sets < 16:
        raise RuntimeError(f"implausible tech set count {n_sets}")
    sets = w.q(T + 0x10)
    for i in range(n_sets):
        A = w.q(sets + 8 * i)
        n_rows = w.u32(A + 4)
        rows = w.q(A + 8)
        for j in range(min(n_rows, 64)):
            R = rows + 0x10 * j
            n = w.u32(R + 4)
            base = w.q(R + 8)
            for k in range(min(n, 64)):
                E = base + 0x80 * k
                key = _entry_key(w, E)
                if key:
                    out[key] = TechEntry(key, w.u32(E + 8), w.pm.read_bytes(E + 0x78, 1)[0], E)
    return out


def researching(w, T: int) -> str | None:
    """Key of the tech being researched, or None when research is idle."""
    E = w.q(T + 0x28)
    if not E or w.u32(E + 8) != STATE_RESEARCHING:
        return None
    return _entry_key(w, E)


def research_target(w, T: int) -> str | None:
    """Key of the last clicked research target ([T+0x30]), or None. Only meaningful while researching."""
    E = w.q(T + 0x30)
    return _entry_key(w, E) if E else None


def _name(key: str | None, ns: dict[str, Node]) -> str:
    return ns[key].name if key in ns else str(key)


def candidates(entries: dict[str, TechEntry]) -> list[str]:
    """Click order with researched techs (and anything not in the live tree) removed. Locked techs stay:
    clicking one queues it with its missing prerequisites."""
    return [k for k in click_order()
            if k in entries and entries[k].state != STATE_RESEARCHED and entries[k].flag78 == 0]


# ------------------------------------------------------------------ UI-tree version (default)
#
# Technology panel components (9.0.4, 1920x1080):
#   HUD button          hud_campaign/.../button_technology, child alert_icon visible while research is idle
#   panel               technology_panel; closed with button_ok (button_ok_holder, bottom centre)
#   tree                technology_list/list_clip/list_box/tech_template/tree_parent/slot_parent/<tech key>
#                       Every node of the tree is a visible component whose id is the technology key, child
#                       technology_entry: icon_check visible = researched; dy_time (hourglass + turns)
#                       visible = available or queued, so a LOCKED node with dy_time visible is in the
#                       queued chain; researching_icon visible = being researched.
#   scrolling           the tree (2703 px) is wider than list_clip (x 36..1882): nodes past the clip still
#                       read as visible, at off-screen x. technology_list/hslider/handle is dragged; the
#                       node rectangles follow the scroll, so positions are re-read after a drag. The panel
#                       remembers its scroll position between openings.

PANEL_ID = "technology_panel"
PANEL_PARK = (960, 160)          # inside the panel, above the tree: no tooltip over a node
OPEN_TIMEOUT = 2.0               # s: the panel appears ~10 ms after the click; its 56 nodes are built ~20 ms later
REGISTER_TIMEOUT = 0.5           # s: a click the game took changes [T+0x30] (or starts research) within a few frames
RESEARCH_TIMEOUT = 0.5           # s: after a registered click, research starts at once unless the game ignored it
# There is no fixed settle after the panel opens: nodes report hover as soon as they are built, and every click is
# checked in memory ([T+0x30] is written by every click the game registers): a click that is not registered is
# sent again, one that is registered but does not start research is a target the game will not queue.


def _first(ui, cid: str, under: str | None = None):
    """First visible component with this id (optionally below a component with id `under`): UI.first."""
    return ui.first(cid, under=under)


def _panel_open(ui) -> bool:
    return ui.root_child(PANEL_ID) is not None


def _open_panel(ui) -> int | None:
    """Open the technology panel (if needed); returns the tree's slot_parent once its nodes are built, or None."""
    if not _panel_open(ui):
        b = ui.cached("button_technology", under="hud_campaign")
        if b is None:
            return None
        click(ui, b)
        if wait.appears(ui, PANEL_ID, timeout=OPEN_TIMEOUT, must=False) is None:
            return None
    sp = wait.appears(ui, "slot_parent", under=PANEL_ID, timeout=OPEN_TIMEOUT, must=False)
    if sp is None:
        return None
    built = wait.stable(lambda: len(ui.children(sp.ptr)), n=3, eps=0, timeout=OPEN_TIMEOUT, must=False,
                        what="technology nodes built", ui=ui)
    return sp.ptr if built else None


def queued_in_ui(ui, entries: dict[str, TechEntry], slot: int | None = None) -> list[str]:
    """Locked techs the open panel shows as queued (dy_time visible on a locked node)."""
    slot = slot or ui.first("slot_parent", under=PANEL_ID)
    if slot is None:
        return []
    out = []
    for n in ui.children(slot):
        key = ui.id(n)
        if key not in entries or entries[key].state != STATE_LOCKED:
            continue
        if ui.first("dy_time", start=n) is not None:
            out.append(key)
    return out


def _close_panel(ui) -> bool:
    if not _panel_open(ui):
        return True
    b = ui.first("button_ok", under=PANEL_ID)
    if b is not None:
        click(ui, b)
        if wait.wait_until(lambda: not _panel_open(ui), 1.0, "technology panel closed", must=False):
            return True
    if _panel_open(ui):                  # Escape is safe here: a panel is open, so it closes that panel
        press("esc")
        wait.wait_until(lambda: not _panel_open(ui) or ui.root_child("esc_menu"), 1.0,
                        "technology panel closed by Escape", must=False)
    if ui.root_child("esc_menu"):
        r = ui.first("button_resume", under="esc_menu")
        if r is not None:
            click(ui, r)
            wait.wait_until(lambda: ui.root_child("esc_menu") is None, 1.0, "game menu closed", must=False)
    return not _panel_open(ui)


def _inside(k, clip) -> bool:
    return (clip.x + 4 <= k.x and k.x + k.w <= clip.x + clip.w - 4
            and clip.y + 4 <= k.y and k.y + k.h <= clip.y + clip.h - 4)


def _node_on_screen(ui, key: str, slot: int):
    """The node's rectangle once it sits inside the tree's clip window (dragging the scrollbar if needed), or None.
    Nodes past the clip still read visible, at off-screen x: the clip decides."""
    panel = ui.root_child(PANEL_ID)
    clip_c = ui.first("list_clip", under="technology_list", start=panel)
    for _ in range(3):
        node = ui.child(slot, key, visible_only=True)
        if node is None or clip_c is None:
            return None
        k, clip = ui.comp(node), ui.comp(clip_c)
        if _inside(k, clip):
            return k
        h = ui.first("handle", under="hslider", start=panel)
        if h is None:
            return None
        hx, hy = ui.comp(h).center
        drag(hx, hy, 5 if k.x < clip.x else 1915, hy, target=h)
        move_to(*PANEL_PARK)
        wait.stable_rect(ui, node, n=2, timeout=1.0, must=False, what=f"{key} still after the scroll")
    return None


def _click_node(ui, w, T: int, k) -> str:
    """Click a node and read the outcome from memory: "started" (research running), "ignored" (the game took the
    click, [T+0x30] moved, but will not research it) or "lost" (no sign the click was taken)."""
    before = w.q(T + 0x30)
    click(ui, k.ptr)
    move_to(*PANEL_PARK)
    took = wait.wait_until(lambda: researching(w, T) or w.q(T + 0x30) != before, REGISTER_TIMEOUT,
                           "research click registered ([T+0x30] or research)", must=False)
    if not took:
        return "lost"
    return "started" if wait.wait_until(lambda: researching(w, T), RESEARCH_TIMEOUT, "research started",
                                        must=False) else "ignored"


MAX_CLICKS = 4                   # targets tried per run before giving up (each is verified in memory)


def run(log=print) -> str:
    """Research state from memory; only when idle, open the panel, click the first target in click order
    (scrolled into view from the UI tree) and confirm in memory that research started. A target the game
    will not queue (the click is ignored) is skipped for the next one.

    No click is ever sent while research is running: clicking the tech being researched cancels it."""
    from bot.sensor.ui import UI
    from bot.sensor.world import World
    try:
        w = World()
        T = tech_manager(w)
        entries = tech_entries(w, T)
        cur = researching(w, T)
    except Exception as e:
        log(f"tech: memory read failed ({e})")
        return f"could not read research from memory ({e}); nothing clicked"
    ns = nodes()
    if cur:
        return f"researching {_name(cur, ns)}"
    todo = candidates(entries)
    if not todo:
        return "nothing left to research"
    ui = UI(w.s)
    if ui.find_root() is None:
        return "game UI not found in memory; nothing clicked"
    tried: list[str] = []
    result = None
    closed = True
    with game_focus():
        slot = _open_panel(ui)
        if slot is None:
            closed = _close_panel(ui)
            return "could not open the technology panel" + ("" if closed else " (WARNING: it may still be open)")
        try:
            for key in todo[:MAX_CLICKS]:
                if researching(w, T):            # started late by an earlier click: never click again
                    break
                k = _node_on_screen(ui, key, slot)
                if k is None:
                    tried.append(f"{_name(key, ns)}: node not on screen")
                    continue
                outcome = _click_node(ui, w, T, k)
                if outcome == "lost" and not researching(w, T):
                    outcome = _click_node(ui, w, T, k)      # not taken at all (no [T+0x30] write): once more
                if outcome == "started":
                    break
                tried.append(f"{_name(key, ns)}: click " + ("ignored" if outcome == "ignored" else "not taken"))
            cur = researching(w, T)
            if cur:
                target = research_target(w, T) or cur
                chain = []
                if target != cur:                # the panel marks the queued chain (dy_time on locked nodes)
                    tnode = ui.child(slot, target, visible_only=True)
                    if tnode is not None:
                        wait.wait_until(lambda: ui.first("dy_time", start=tnode), 0.5, "queued chain shown",
                                        must=False)
                    chain = queued_in_ui(ui, tech_entries(w, T), slot)
                via = "" if target == cur else f" (path to {_name(target, ns)}, {len(chain)} locked techs queued)"
                result = f"queued {_name(cur, ns)}{via}"
                if tried:
                    result += " | skipped: " + "; ".join(tried)
                log(f"tech: {result}")
        finally:
            closed = _close_panel(ui)
    if result is None:
        result = "nothing queued: " + "; ".join(tried)
    if not closed:
        result += " (WARNING: technology panel still open)"
    return result


def status() -> str:
    from bot.sensor.world import World
    w = World()
    T = tech_manager(w)
    entries = tech_entries(w, T)
    ns = nodes()
    cur = researching(w, T)
    counts = {n: sum(1 for e in entries.values() if e.state == s) for s, n in STATE_NAMES.items()}
    todo = candidates(entries)
    tgt = research_target(w, T)
    lines = [f"researching: {_name(cur, ns) if cur else 'nothing (idle)'}"
             + (f" (target {_name(tgt, ns)})" if cur and tgt and tgt != cur else ""),
             f"researched (T+0x3C): {w.u32(T + 0x3C)}; tree: {counts}",
             "next click: " + (f"{_name(todo[0], ns)} [{todo[0]}, {STATE_NAMES.get(entries[todo[0]].state)}]"
                               if todo else "nothing left")]
    return "\n".join(lines)


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print(status())
    elif cmd == "plan":
        ns = nodes()
        for i, k in enumerate(click_order(), 1):
            print(f"{i:2d}. {ns[k].name} (tier {ns[k].tier}, {ns[k].rp} RP)")
    elif cmd == "run":
        print(run())
    elif cmd == "run_screen":
        print(run_screen())
    return 0


if __name__ == "__main__":
    sys.exit(main())
