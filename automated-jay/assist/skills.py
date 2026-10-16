"""Skill automation: spend every unspent skill point on Ikit Claw, Verminlord Warpseers and Warlock
Engineers in the player's fixed order (strategy/skills.json), then "as fits" (passives first,
active-ability skills last). Other characters are left alone.

How it works on screen (verified on 9.0.4, 1920x1080, UI scale 1):
  - Lords & Heroes list (top bar button) -> clicking a row's rank badge opens that character's skills.
  - The arrows beside the name plate cycle through every character of the faction and wrap around.
  - Character type = the subtitle under the name plate ("Legendary Lord", "Warlock Engineer", ...),
    matched against templates in assist/templates/.
  - "Skill Points: N" badge is gold when N > 0.
  - Typing in "Search Skills" highlights the matching node in red; the difference between a capture
    with an empty search and one with the name typed is the node to click.
  - Clicking a node spends one point immediately (undo exists until the panel closes). Clicking a node
    that is maxed or still locked changes nothing, which is how "maxed" is detected.

    python -X utf8 -m assist.skills run
"""
from __future__ import annotations
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import win32api
import win32con
from PIL import Image

from . import gamedata as gd
from bot.focus import game_focus
from tools.ui import click_at, drag, grab, move_to, type_text

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"
STRATEGY = HERE.parent / "strategy" / "skills.json"

LORDS_BUTTON = (1772, 22)
LORDS_HEADER = (1640, 258, 1910, 290)
FIRST_ROW_BADGE = (1678, 381)
NAME = (795, 12, 1125, 48)
SUB = (850, 58, 1070, 86)
BADGE = (1790, 92, 1834, 134)
SKILLS_TAB = (840, 95, 1080, 125)
NEXT_CHAR = (1200, 30)
CLOSE = (960, 1050)
SEARCH_BOX = (225, 1050)
SEARCH_CLEAR = (377, 1050)
TREE = (345, 225, 1905, 790)
PARK = (960, 1075)
THUMB_ROW, THUMB_X0, THUMB_X1 = 1002, 395, 1845

# subtitle template -> character key in skills.json (name template required too where listed)
TYPES = {
    "ikit_claw": ("sub_legendary_lord", "name_ikit_claw"),
    "warlock_engineer": ("sub_warlock_engineer", None),
    "verminlord_warpseer": ("sub_verminlord_warpseer", None),
}


# ------------------------------------------------------------------ image helpers

def _tmpl(name: str) -> Image.Image | None:
    p = TEMPLATES / f"{name}.png"
    return Image.open(p).convert("RGB") if p.exists() else None


def similar(a: Image.Image, b: Image.Image) -> float:
    x = np.asarray(a.convert("L"), dtype=float)
    y = np.asarray(b.convert("L").resize(a.size), dtype=float)
    x -= x.mean()
    y -= y.mean()
    d = np.sqrt((x * x).sum() * (y * y).sum())
    return float((x * y).sum() / d) if d else 0.0


BADGE_DIGIT = (1801, 100, 1823, 126)
POINTS_OFF = 0x240        # unspent skill points: u32 at [character + 0x3F0] + 0x240 (verified 9.0.4)


def has_points(img: Image.Image) -> bool:
    """The badge glow pulses, so read the digit: anything that is not the '0' glyph means points."""
    z = _tmpl("badge_digit_zero")
    return z is None or similar(img.crop(BADGE_DIGIT), z) < 0.6


def points_by_character() -> dict[int, int]:
    """character pointer -> unspent skill points, for the character types this step handles."""
    from bot.sensor.world import World, characters, find_player_faction
    w = World()
    F = find_player_faction(w)
    subtypes = {c["agent_subtype"] for c in orders()["characters"].values()}
    out = {}
    for c in characters(w, F):
        if c.subtype in subtypes:
            out[c.ptr] = w.u32(w.q(c.ptr + 0x3F0) + POINTS_OFF)
    return out


def region_changed(a: Image.Image, b: Image.Image, box) -> int:
    x = np.asarray(a.crop(box)).astype(int)
    y = np.asarray(b.crop(box)).astype(int)
    return int((np.abs(x - y).max(axis=2) > 50).sum())


def highlight_box(base: Image.Image, hl: Image.Image):
    """Bounding box of the node the search highlighted, or None.

    The highlight looks different by node state: a locked (grey) node turns red, an available or taken
    node (already drawn in its row colour) only gets a brighter border. Both show up as the largest
    patch of changed pixels in the tree area between the two captures."""
    import cv2
    x = np.asarray(base.crop(TREE)).astype(int)
    y = np.asarray(hl.crop(TREE)).astype(int)
    m = (np.abs(x - y).max(axis=2) > 35).astype(np.uint8)
    m = cv2.dilate(m, np.ones((9, 9), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n <= 1:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    bx, by, bw, bh, area = stats[i]
    if area < 600 or bw > 320 or bh > 110 or bw < 60:
        return None                                   # nothing clear, or several nodes lit
    return (int(bx) + TREE[0], int(by) + TREE[1], int(bx + bw) + TREE[0], int(by + bh) + TREE[1])


def thumb_span(img: Image.Image):
    row = np.asarray(img).astype(int)[THUMB_ROW, THUMB_X0:THUMB_X1]
    xs = np.where((row[:, 1] > 120) & (row[:, 0] < 120) & (row[:, 1] - row[:, 0] > 40))[0]
    return (int(xs.min()) + THUMB_X0, int(xs.max()) + THUMB_X0) if len(xs) >= 2 else None


def search_term(name: str) -> str:
    """Lowercase prefix of the skill name the search box can take (letters, digits, space, hyphen)."""
    s = name.strip().strip('"').lower()
    m = re.match(r"[a-z0-9 \-]+", s)
    return (m.group(0) if m else s).strip()


# ------------------------------------------------------------------ panel driving (game focused)

def _park() -> None:
    move_to(*PARK)
    time.sleep(0.5)


def _drag(x0: int, y0: int, x1: int) -> None:
    drag(x0, y0, x1, y0)


class SkillPanel:
    def __init__(self) -> None:
        self.side = "left"

    def is_open(self, img: Image.Image | None = None) -> bool:
        t = _tmpl("skills_tab")
        return t is not None and similar((img or grab()).crop(SKILLS_TAB), t) > 0.8

    def open(self) -> None:
        img = grab()
        if self.is_open(img):
            return
        hdr = _tmpl("lords_list_header")
        if hdr is None or similar(img.crop(LORDS_HEADER), hdr) < 0.8:
            click_at(*LORDS_BUTTON)
            time.sleep(1.5)
        click_at(*FIRST_ROW_BADGE)
        time.sleep(2.0)
        if not self.is_open():
            raise RuntimeError("skill panel did not open")
        self.side = "left"

    def close(self) -> None:
        click_at(*CLOSE)
        time.sleep(1.0)

    def next_character(self) -> None:
        click_at(*NEXT_CHAR)
        time.sleep(1.5)
        self.side = "left"

    def character_type(self, img: Image.Image) -> str | None:
        for key, (sub, name) in TYPES.items():
            ts = _tmpl(sub)
            if ts is None or similar(img.crop(SUB), ts) < 0.9:
                continue
            if name:
                tn = _tmpl(name)
                if tn is None or similar(img.crop(NAME), tn) < 0.9:
                    continue
            return key
        return None

    def scroll(self, side: str) -> None:
        if self.side == side:
            return
        span = thumb_span(grab())
        if span:
            _drag((span[0] + span[1]) // 2, THUMB_ROW + 1, 5 if side == "left" else 1915)
        self.side = side

    def locate(self, name: str):
        term = search_term(name)
        for side in (self.side, "right" if self.side == "left" else "left"):
            self.scroll(side)
            click_at(*SEARCH_CLEAR)
            time.sleep(0.4)
            _park()
            base = grab()
            click_at(*SEARCH_BOX)
            time.sleep(0.3)
            type_text(term)
            time.sleep(0.9)
            _park()
            box = highlight_box(base, grab())
            if box and box[2] < TREE[2] - 8 and box[0] > TREE[0] + 8:
                return box
        return None

    def spend(self, name: str, ranks: int) -> int:
        """Click the node up to `ranks` times while points remain; returns points spent.
        A click counts only if some character's unspent points went down in memory."""
        box = self.locate(name)
        if box is None:
            return 0
        cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
        spent = 0
        for _ in range(ranks):
            if not has_points(grab()):
                break
            before = sum(points_by_character().values())
            click_at(cx, cy)
            time.sleep(0.4)
            _park()
            if sum(points_by_character().values()) >= before:
                break
            spent += 1
        return spent


# ------------------------------------------------------------------ orders

def orders() -> dict:
    return json.load(open(STRATEGY, encoding="utf-8"))


def attempt_list(char_key: str) -> list[tuple[str, int, str]]:
    """The player's order (mounts to take first, they unlock by rank), then the rest of the tree:
    passive skills first, active-ability skills last."""
    o = orders()
    c = o["characters"][char_key]
    nodes = {r["key"]: r for r in gd._load("character_skill_nodes_tables")}
    skills = {r["key"]: r for r in gd._load("character_skills_tables")}
    effects: dict[str, list[str]] = {}
    maxlvl: dict[str, int] = {}
    for r in gd._load("character_skill_level_to_effects_junctions_tables"):
        effects.setdefault(r["character_skill_key"], []).append(r["effect_key"])
        maxlvl[r["character_skill_key"]] = max(maxlvl.get(r["character_skill_key"], 0), int(r["level"]))
    loc = gd.loc()

    def name_of(node_key: str) -> str:
        sk = nodes[node_key]["character_skill_key"]
        n = loc.get("character_skills_localised_name_" + sk, "")
        return gd._tr(n) if n else ""

    out: list[tuple[str, int, str]] = []
    mounts = c.get("mounts", {})
    for n in mounts.get("take", []):
        out.append((name_of(n), 1, nodes[n]["character_skill_key"]))
    listed = set()
    for item in c["order"]:
        out.append((item["skill"], item["ranks"], nodes[item["node"]]["character_skill_key"]))
        listed.add(item["node"])
    skip = set(mounts.get("skip", [])) | set(mounts.get("take", [])) | listed
    items = [r["item"] for r in gd._load("character_skill_node_set_items_tables") if r["set"] == c["node_set"]]
    rest = []
    for n in items:
        nd = nodes.get(n)
        if not nd or n in skip or nd["visible_in_ui"] is False:
            continue
        sk = nd["character_skill_key"]
        nm = name_of(n)
        if not nm or nm.startswith("[HIDDEN]"):
            continue
        ability = any("abilit" in e or "spell" in e for e in effects.get(sk, []))
        rest.append((ability, int(nd["indent"]), int(nd["tier"]), nm, max(1, maxlvl.get(sk, 1)), sk))
    rest.sort()
    out += [(nm, ranks, sk) for _, _, _, nm, ranks, sk in rest]
    return out


# ------------------------------------------------------------------ the automation step

def run_screen(log=print) -> str:
    """Older screen-search version (search box + screenshot diff). Manual use only, never a fallback."""
    done: list[str] = []
    if not any(points_by_character().values()):
        return "no unspent points"
    with game_focus():
        panel = SkillPanel()
        panel.open()
        try:
            first_name = grab().crop(NAME)
            for _ in range(60):                       # safety bound on the number of characters
                img = grab()
                key = panel.character_type(img)
                if key and has_points(img):
                    spent_here = []
                    for name, ranks, _sk in attempt_list(key):
                        if not has_points(grab()):
                            break
                        n = panel.spend(name, ranks)
                        if n:
                            spent_here.append(f"{name} x{n}")
                    if spent_here:
                        done.append(f"{key}: " + ", ".join(spent_here))
                        log(f"skills: {key}: {', '.join(spent_here)}")
                panel.next_character()
                if similar(grab().crop(NAME), first_name) > 0.97:
                    break
        finally:
            click_at(*SEARCH_CLEAR)
            panel.close()
    return "; ".join(done) if done else "no unspent points"


# ------------------------------------------------------------------ UI-tree version (default)
#
# Every skill node in the skills panel is a UI component whose id is the character_skill_key; its child
# "icon_check" is visible when the skill is maxed. The Lords & Heroes list rows are components
# "character_row_<id>" (id = u32 at character + 0x110) with the rank badge as child "skill_button";
# clicking it opens that character's skills. Positions come straight from the UI tree (bot/sensor/ui.py),
# so nothing is searched for on screen.

CHAR_ID_OFF = 0x110
SKILLS_PANEL = "character_details_panel_skills"


def _skill_targets():
    """[(character ptr, char_key, character id, points)] for characters the orders cover that have points."""
    from bot.sensor.world import World, characters, find_player_faction
    w = World()
    F = find_player_faction(w)
    by_subtype = {c["agent_subtype"]: k for k, c in orders()["characters"].items()}
    out = []
    for c in characters(w, F):
        k = by_subtype.get(c.subtype)
        if not k:
            continue
        pts = w.u32(w.q(c.ptr + 0x3F0) + POINTS_OFF)
        if pts:
            out.append((c.ptr, k, w.u32(c.ptr + CHAR_ID_OFF), pts, c.name))
    return out, w


def _points(w, ptr) -> int:
    return w.u32(w.q(ptr + 0x3F0) + POINTS_OFF)


def _first(ui, cid: str, under: str | None = None):
    """First visible component with this id (optionally inside a component with id `under`)."""
    for c, ids in ui.walk():
        if ids[-1] == cid and (under is None or under in ids[:-1]):
            return c
    return None


def _child(ui, c: int, cid: str):
    for ch in ui.children(c):
        if ui.id(ch) == cid:
            return ch
    return None


def _open_for(ui, char_id: int) -> bool:
    """Open the skills panel of the character with this id via its Lords & Heroes row."""
    from .heroes import open_lords_list
    open_lords_list()
    row = _first(ui, f"character_row_{char_id}")
    if row is None:
        return False
    badge = None
    for c, ids in ui.walk(row):
        if ids[-1] == "skill_button":
            badge = c
            break
    if badge is None:
        return False
    click_at(*ui.comp(badge).center)
    time.sleep(1.5)
    return _first(ui, SKILLS_PANEL) is not None


def _node_visible_rect(ui, node: int, clip):
    k = ui.comp(node)
    card = _child(ui, node, "card")
    if card:
        k = ui.comp(card)
    inside = clip.x + 4 <= k.x and k.x + k.w <= clip.x + clip.w - 4
    return k, inside


def _maxed(ui, node: int) -> bool:
    card = _child(ui, node, "card") or node
    chk = _child(ui, card, "icon_check")
    return chk is not None and ui.pm.read_bytes(chk + 0x353, 1)[0] != 0


def run(log=print) -> str:
    targets, w = _skill_targets()
    if not targets:
        return "no unspent points"
    from bot.sensor.ui import UI
    ui = UI(w.s)
    if ui.find_root() is None:
        return "game UI not found in memory; nothing clicked"
    done = []
    with game_focus():
        for ptr, key, char_id, pts, name in targets:
            if not _open_for(ui, char_id):
                done.append(f"{name}: could not open skills")
                continue
            panel = SkillPanel()
            spent_here = []
            for sname, ranks, sk in attempt_list(key):
                if _points(w, ptr) == 0:
                    break
                node = _first(ui, sk, under=SKILLS_PANEL)
                if node is None or (ranks == 1 and _maxed(ui, node)):
                    continue                      # the tick shows once any rank is taken, so it only
                                                  # proves "maxed" for one-rank skills
                clip_c = _first(ui, "list_clip", under=SKILLS_PANEL)
                if clip_c is None:
                    break
                clip = ui.comp(clip_c)
                k, inside = _node_visible_rect(ui, node, clip)
                if not inside:
                    panel.side = None                         # force the drag
                    panel.scroll("left" if k.x < clip.x else "right")
                    time.sleep(0.4)
                    k, inside = _node_visible_rect(ui, node, clip)
                    if not inside:
                        continue
                n = 0
                for _ in range(ranks):
                    before = _points(w, ptr)
                    if before == 0:
                        break
                    click_at(*k.center)
                    time.sleep(0.35)
                    if _points(w, ptr) >= before:
                        break
                    n += 1
                if n:
                    spent_here.append(f"{sname} x{n}")
            panel.close()
            if spent_here:
                done.append(f"{name}: " + ", ".join(spent_here))
                log(f"skills: {name}: {', '.join(spent_here)}")
    return "; ".join(done) if done else "no points could be spent"


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if cmd == "run":
        print(run())
    elif cmd == "plan":
        who = sys.argv[2] if len(sys.argv) > 2 else "ikit_claw"
        for i, (n, r, sk) in enumerate(attempt_list(who), 1):
            print(f"{i:2d}. {n} x{r}  [{sk}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
