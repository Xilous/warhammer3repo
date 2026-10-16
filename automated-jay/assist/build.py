"""Building automation: apply the settlement priority list (strategy/settlements.json via buildplan)
to every owned province that is not next to an enemy at war, at the start of the turn.

State comes from memory (bot/sensor/world.py): owned regions, slots, buildings, construction in
progress, wars, adjacency. Actions go through the province panel UI:

  province panel  bottom-centre; arrows beside the title cycle the player's provinces.
                  Settlements are columns (memory province region order, reversed), each with a
                  grid of 74 px slot cards: slot i -> row i // per_row, col i % per_row.
  construct       click an empty slot -> strip of category cards above it (Landmark, Basic Military,
                  Advanced Military, Defence, Infrastructure). Hovering a category opens its panel:
                  one column per chain, one row per required main tier; buildable cards are parchment.
                  Click the parchment card whose icon is the target chain.
  upgrade         click the building -> its chain stacked above the slot; the next level is the
                  lowest parchment card above the slot. Click it.
Every action is verified in memory (the slot shows construction in progress) before moving on.

    python -X utf8 -m assist.build plan          # what would be done (memory only, no input)
    python -X utf8 -m assist.build run           # do it
"""
from __future__ import annotations
import json
import sys
import time
from dataclasses import dataclass

import numpy as np
import win32api
from PIL import Image

from . import gamedata as gd
from .buildplan import Building, Province, Settlement, plan_province, strategy
from .slots import icon_chains, match_cell
from bot.focus import game_focus
from bot.sensor.world import World, snapshot, region_provinces
from tools.ui import click_at, grab, move_path, move_to

PROVINCES_BUTTON = (1810, 22)
FIRST_OWN_PROVINCE_ROW = (1695, 357)
PANEL_NEXT = (1157, 772)
HEADER_Y = 831
SLOT_ROW0_Y, SLOT_PITCH = 891, 74
PARK = (1700, 700)


# ------------------------------------------------------------------ state -> planner model

def level_of(key: str) -> tuple[str, int] | None:
    for c, ls in gd.chains().items():
        for l in ls:
            if l.key == key:
                return c, l.index
    return None


@dataclass
class OwnedSettlement:
    region: str
    region_obj: int
    province: str
    column: int            # column index in the province panel
    columns: int           # settlements shown in that province panel
    slot_states: list      # memory Slot list (index = panel slot index)
    model: Settlement


def build_models(w: World, snap) -> tuple[dict[str, list[OwnedSettlement]], dict[str, str]]:
    prov_of, is_cap = region_provinces()
    out: dict[str, list[OwnedSettlement]] = {}
    for key, r in snap.own.items():
        p = prov_of.get(key, key)
        # province region order in memory -> panel columns are that order reversed
        P = w.q(w.q(r + 0x3A8) + 0x10)
        n = w.u32(P + 0x7C)
        arr = w.q(P + 0x80)
        order = [w.region_key(w.q(w.q(arr + 8 * i))) for i in range(n)][::-1]
        col = order.index(key) if key in order else 0
        slots = w.slots(r)
        main = port = None
        rest: list = []
        for i, s in enumerate(slots):
            lv = level_of(s.building) if s.building else None
            if i == 0 and lv:
                main = Building(*lv)
                continue
            if lv and lv[0] == strategy()["port_chain"]:
                port = Building(*lv)
                continue
            if not s.active:
                continue
            if s.constructing and not lv:
                rest.append(Building("__constructing__", 0))
            else:
                rest.append(Building(*lv) if lv else None)
        if main is None:
            continue
        model = Settlement(key, bool(is_cap.get(key)), main, port, rest,
                           gd.landmarks_for_region(key), key)
        out.setdefault(p, []).append(OwnedSettlement(key, r, p, col, len(order), slots, model))
    return out, snap.blocked_provinces


def planned_actions(w: World | None = None):
    """[(OwnedSettlement, Action)] in priority order, for unblocked provinces only."""
    w = w or World()
    snap = snapshot(w)
    if snap is None:
        raise RuntimeError("player faction not found in memory")
    models, blocked = build_models(w, snap)
    todo, skipped = [], []
    for p, owned in models.items():
        if p in blocked:
            skipped.append((p, blocked[p]))
            continue
        plans = plan_province(Province(p, [o.model for o in owned]))
        by_name = {o.region: o for o in owned}
        for sp in plans:
            o = by_name[sp.settlement.name]
            busy = any(s.constructing for s in o.slot_states)
            for a in sp.actions:
                if a.kind in ("upgrade_main", "upgrade_port", "construct", "upgrade"):
                    todo.append((o, a, busy))
    return todo, skipped, snap


# ------------------------------------------------------------------ screen geometry

def headers(img: Image.Image) -> list[tuple[int, int]]:
    """x-ranges of the settlement name plates (green bars, row ~838) in the province panel."""
    a = np.median(np.asarray(img.crop((300, 836, 1620, 841))).astype(int), axis=0)
    g = (a[:, 1] > 85) & (a[:, 1] - a[:, 0] > 60)
    segs, start = [], None
    for x, v in enumerate(list(g) + [False]):
        if v and start is None:
            start = x
        elif not v and start is not None:
            segs.append([start, x])
            start = None
    merged: list[list[int]] = []
    for sgm in segs:                                  # bridge gaps left by lettering
        if merged and sgm[0] - merged[-1][1] < 20:
            merged[-1][1] = sgm[1]
        else:
            merged.append(sgm)
    return [(x0 + 300, x1 + 300) for x0, x1 in merged if x1 - x0 > 120]


def slot_xy(img: Image.Image, column: int, index: int) -> tuple[int, int] | None:
    hs = headers(img)
    if column >= len(hs):
        return None
    x0, x1 = hs[column]
    per_row = max(1, round((x1 - x0 - 48) / SLOT_PITCH))
    first = x0 + 60
    return first + (index % per_row) * SLOT_PITCH, SLOT_ROW0_Y + (index // per_row) * SLOT_PITCH


def level_icon(level_key: str) -> str | None:
    from .slots import ICONS
    m = json.load(open(ICONS / "_level_to_icon.json"))
    return m.get(level_key)


def chain_icon(chain: str, index: int | None = None) -> str | None:
    """Icon of a chain's level (default: its first non-ruin level)."""
    ls = gd.chains().get(chain, [])
    if index is not None:
        ls = [l for l in ls if l.index == index] or ls
    for l in ls:
        if "ruin" in l.key:
            continue
        ic = level_icon(l.key)
        if ic:
            return ic
    return None


def parchment_cards(img: Image.Image, box) -> list[tuple[int, int]]:
    """Centres of bright parchment cards (~60-74 px) inside box (x0, y0, x1, y1)."""
    a = np.asarray(img.crop(box)).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    m = ((r > 150) & (g > 135) & (b > 100) & (r - b < 90) & (r - b > 15)).astype(np.uint8)
    import cv2
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if 40 <= w <= 95 and 40 <= h <= 95 and area > 1200:
            out.append((int(x + w / 2) + box[0], int(y + h / 2) + box[1]))
    return out


def strip_cards(img: Image.Image, sx: int, sy: int) -> list[tuple[int, int]]:
    """Category cards in the strip that pops up above an empty slot (row centred ~76 px above it)."""
    cy = sy - 76
    a = np.asarray(img.crop((max(0, sx - 450), cy - 14, min(1920, sx + 450), cy + 14))).astype(int)
    luma = (0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]).mean(axis=0)
    lit = luma > 40                       # the gaps between cards are near black
    out, start = [], None
    for x, v in enumerate(list(lit) + [False]):
        if v and start is None:
            start = x
        elif not v and start is not None:
            if 35 <= x - start <= 75 and luma[start:x].mean() > 110:
                out.append((max(0, sx - 450) + (start + x) // 2, cy))
            start = None
    return out


def identify_column(img: Image.Image, o: OwnedSettlement, others: list | None = None) -> bool:
    """Does the panel show o's province with o in o's column? Checked against any of o's slots that
    holds a finished building (a slot under construction shows a different picture). If none can be
    checked, accept when no other owned province has the same number of columns."""
    hs = headers(img)
    if len(hs) != o.columns:
        return False
    checked = False
    for i, st in enumerate(o.slot_states):
        if not st.building or st.constructing:
            continue
        want = level_icon(st.building)
        xy = slot_xy(img, o.column, i)
        if not want or xy is None:
            continue
        checked = True
        best = match_cell(img, xy[0], xy[1], top=1)
        if best and best[0][1] == want:
            return True
    if not checked:
        return not any(x.columns == o.columns and x.province != o.province for x in (others or []))
    return False


# ------------------------------------------------------------------ actions (game focused)

def provinces_list_open(img: Image.Image) -> bool:
    from .skills import _tmpl, similar
    t = _tmpl("provinces_list_header")
    return t is not None and similar(img.crop((1640, 258, 1910, 290)), t) > 0.8


def open_province(o: OwnedSettlement, others: list | None = None) -> bool:
    img = grab()
    if not headers(img):
        if not provinces_list_open(img):
            click_at(*PROVINCES_BUTTON)
            time.sleep(1.2)
        click_at(*FIRST_OWN_PROVINCE_ROW)
        time.sleep(2.0)
        if not headers(grab()):
            return False
    for _ in range(12):
        move_to(*PARK)
        time.sleep(0.4)
        if identify_column(grab(), o, others):
            return True
        click_at(*PANEL_NEXT)
        time.sleep(2.2)
    return False


def _climb(x: int, y_from: int, y_to: int, x_to: int | None = None) -> None:
    """Move the cursor up from the slot to a popup above it without leaving the popup chain: straight up at the
    slot's x, then across inside the popup. Jumps, not 6 px steps (2026-10-16: the game samples the cursor once per
    frame; each waypoint is held tools.ui.HOVER_MAX_FRAMES frames)."""
    pts = [(x, y_from), (x, y_to)]
    if x_to is not None:
        pts.append((x_to, y_to))
    move_path(pts)


def do_construct(o: OwnedSettlement, slot_index: int, chain: str) -> bool:
    img = grab()
    xy = slot_xy(img, o.column, slot_index)
    icon = chain_icon(chain)
    if xy is None or icon is None:
        return False
    sx, sy = xy
    click_at(sx, sy)
    time.sleep(1.2)
    strip = strip_cards(grab(), sx, sy)
    for cx, cy in sorted(strip):
        move_to(sx, sy)
        time.sleep(0.3)
        _climb(sx, sy - 10, cy, cx)
        time.sleep(1.2)
        panel = grab()
        cards = parchment_cards(panel, (max(0, cx - 900), 60, min(1920, cx + 900), cy - 45))
        for kx, ky in cards:
            best = match_cell(panel, kx, ky, top=2)
            if best and best[0][1] == icon and best[0][0] >= 0.35:
                _climb(cx, cy, ky, kx)
                time.sleep(0.3)
                click_at(kx, ky)
                time.sleep(1.5)
                return True
    move_to(*PARK)
    return False


def do_upgrade(o: OwnedSettlement, slot_index: int) -> bool:
    img = grab()
    xy = slot_xy(img, o.column, slot_index)
    if xy is None:
        return False
    sx, sy = xy
    click_at(sx, sy)
    time.sleep(1.2)
    cards = sorted(parchment_cards(grab(), (sx - 60, 60, sx + 60, sy - 45)), key=lambda c: -c[1])
    if len(cards) < 2:                                # only the current level: no upgrade available yet
        move_to(*PARK)
        return False
    kx, ky = cards[1]                                  # the card just above the current level
    _climb(sx, sy - 10, ky, kx)
    time.sleep(0.3)
    click_at(kx, ky)
    time.sleep(1.5)
    return True


def slot_index_for(o: OwnedSettlement, a) -> int | None:
    """Panel slot index for an action: main is 0, port is the port slot, others by their slot number."""
    if a.kind == "upgrade_main":
        return 0
    if a.kind == "upgrade_port":
        for i, s in enumerate(o.slot_states):
            lv = level_of(s.building) if s.building else None
            if lv and lv[0] == strategy()["port_chain"]:
                return i
        return None
    # planner slot numbers: 1 = main, 2 = port when present, then active secondary slots in order
    sec = [i for i, s in enumerate(o.slot_states)
           if i != 0 and s.active and not (s.building and level_of(s.building)
                                           and level_of(s.building)[0] == strategy()["port_chain"])]
    first = 3 if o.model.port is not None else 2
    k = (a.slot or 0) - first
    return sec[k] if 0 <= k < len(sec) else None


def run_screen(log=print, override_blocked: bool = False) -> str:
    """Older screen-matching version, kept as a fallback."""
    w = World()
    todo, skipped, snap = planned_actions(w)
    if override_blocked:
        # test-only: plan blocked provinces too
        models, _ = build_models(w, snap)
        todo = []
        for p, owned in models.items():
            for sp in plan_province(Province(p, [o.model for o in owned])):
                o = next(x for x in owned if x.region == sp.settlement.name)
                busy = any(s.constructing for s in o.slot_states)
                todo += [(o, a, busy) for a in sp.actions if a.kind in ("upgrade_main", "upgrade_port", "construct", "upgrade")]
    done, problems = [], []
    gold = w.s.read().treasury or 0
    with game_focus():
        for o, a, busy in todo:
            if a.cost > gold:
                problems.append(f"{o.region}: {a.item} needs {a.cost} gold")
                continue
            idx = slot_index_for(o, a)
            if idx is None:
                problems.append(f"{o.region}: no slot for {a.item}")
                continue
            if w.slots(o.region_obj)[idx].constructing:
                continue                       # this slot is already being built or upgraded
            if not open_province(o, [x for x, _, _ in todo]):
                problems.append(f"{o.region}: could not find its province panel")
                continue
            if a.kind == "construct":
                chain = next((t.chain for t in plan_targets(o) if t.item == a.item), None)
                ok = chain is not None and do_construct(o, idx, chain)
            else:
                ok = do_upgrade(o, idx)
            time.sleep(1.0)
            after = w.slots(o.region_obj)
            started = idx < len(after) and after[idx].constructing
            if ok and started:
                gold -= a.cost
                done.append(f"{gd.place_name(o.region)}: {a.item} {a.detail}")
                log(f"build: {done[-1]}")
            else:
                problems.append(f"{o.region}: {a.item} not started")
        move_to(*PARK)
    parts = []
    if done:
        parts.append("; ".join(done))
    if skipped:
        parts.append("blocked: " + ", ".join(gd.place_name(p) for p, _ in skipped))
    if problems:
        parts.append("problems: " + "; ".join(problems))
    return " | ".join(parts) if parts else "nothing to build"


# ------------------------------------------------------------------ UI-tree actions (default)
#
# Province panel components (9.0.4):
#   Provinces list rows      row_entry_<province key>      (top-bar Provinces button at (1810, 22))
#   settlement columns       CcoCampaignSettlement<region key>
#   building slots           CcoCampaignBuildingSlotregion_slot_<n>   n = u32 at memory slot +0x8
#   upgrade popup            construction_building_tree with level cards whose id is the building level key
#   build menu (empty slot)  building_categories_popup / CcoBuildingSetRecord<set key>; hovering a set
#                            shows construction_building_tree with level cards keyed the same way
# The popups only stay open while the cursor travels over them, so moves go slot -> popup in one path.

PROVINCES_BUTTON_XY = (1810, 22)


def _ui():
    from bot.sensor.ui import UI
    ui = UI()
    ui.find_root()
    return ui


def _first(ui, cid: str, under: str | None = None):
    """First visible component with this id (optionally below a component with id `under`): UI.first."""
    return ui.first(cid, under=under)


def ui_open_province(ui, province: str) -> bool:
    row = _first(ui, f"row_entry_{province}")
    if row is None:
        click_at(*PROVINCES_BUTTON_XY)
        time.sleep(1.2)
        row = _first(ui, f"row_entry_{province}")
        if row is None:
            return False
    click_at(*ui.comp(row).center)
    time.sleep(1.8)
    return _first(ui, "settlement_list") is not None


def ui_slot(ui, w: World, o: OwnedSettlement, idx: int):
    L = w.q(o.region_obj + 0x148) + 0x10
    sid = w.u32(w.q(w.q(L + 8) + 8 * idx) + 8)
    c = _first(ui, f"CcoCampaignBuildingSlotregion_slot_{sid}")
    return ui.comp(c) if c else None


def ui_upgrade(ui, slot, level_key: str) -> bool:
    sx, sy = slot.center
    click_at(sx, sy)
    time.sleep(1.0)
    card = _first(ui, level_key, under="construction_building_tree")
    if card is None:
        move_to(*PARK)
        return False
    kx, ky = ui.comp(card).center
    _climb(sx, sy - 10, ky, kx)
    time.sleep(0.3)
    click_at(kx, ky)
    time.sleep(1.2)
    return True


def ui_construct(ui, slot, level_key: str) -> bool:
    sx, sy = slot.center
    click_at(sx, sy)
    time.sleep(1.0)
    cats = [c for c, ids in ui.walk() if ids[-1].startswith("CcoBuildingSetRecord") and "building_categories_popup" in ids]
    for cat in cats:
        cx, cy = ui.comp(cat).center
        move_to(sx, sy)
        time.sleep(0.2)
        _climb(sx, sy - 10, cy, cx)
        time.sleep(1.0)
        card = _first(ui, level_key, under="construction_building_tree")
        if card is None:
            continue
        kx, ky = ui.comp(card).center
        _climb(cx, cy, ky, kx)
        time.sleep(0.3)
        click_at(kx, ky)
        time.sleep(1.2)
        return True
    move_to(*PARK)
    return False


def run(log=print, override_blocked: bool = False) -> str:
    w = World()
    todo, skipped, snap = planned_actions(w)
    if override_blocked:
        models, _ = build_models(w, snap)
        todo = []
        for p, owned in models.items():
            for sp in plan_province(Province(p, [o.model for o in owned])):
                o = next(x for x in owned if x.region == sp.settlement.name)
                busy = any(s.constructing for s in o.slot_states)
                todo += [(o, a, busy) for a in sp.actions if a.kind in ("upgrade_main", "upgrade_port", "construct", "upgrade")]
    done, problems = [], []
    gold = w.s.read().treasury or 0
    ui = _ui()
    opened = None
    with game_focus():
        for o, a, busy in todo:
            if a.cost > gold:
                problems.append(f"{o.region}: {a.item} needs {a.cost} gold")
                continue
            idx = slot_index_for(o, a)
            if idx is None or not a.level_key:
                problems.append(f"{o.region}: no slot for {a.item}")
                continue
            if w.slots(o.region_obj)[idx].constructing:
                continue
            if opened != o.province:
                if not ui_open_province(ui, o.province):
                    problems.append(f"{o.region}: could not open its province")
                    continue
                opened = o.province
            slot = ui_slot(ui, w, o, idx)
            if slot is None:
                problems.append(f"{o.region}: slot not on screen")
                continue
            ok = ui_construct(ui, slot, a.level_key) if a.kind == "construct" else ui_upgrade(ui, slot, a.level_key)
            time.sleep(0.6)
            after = w.slots(o.region_obj)
            if ok and idx < len(after) and after[idx].constructing:
                gold -= a.cost
                done.append(f"{gd.place_name(o.region)}: {a.item} {a.detail}")
                log(f"build: {done[-1]}")
            else:
                problems.append(f"{o.region}: {a.item} not started")
        move_to(*PARK)
    parts = []
    if done:
        parts.append("; ".join(done))
    if skipped:
        parts.append("blocked: " + ", ".join(gd.place_name(p) for p, _ in skipped))
    if problems:
        parts.append("problems: " + "; ".join(problems))
    return " | ".join(parts) if parts else "nothing to build"


def plan_targets(o: OwnedSettlement):
    from .buildplan import final_layout, per_province_rules
    return final_layout(o.model, lambda c, s: True)


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if cmd == "plan":
        todo, skipped, snap = planned_actions()
        print("at war with:", snap.at_war)
        for p, why in skipped:
            print(f"BLOCKED {p}: {why}")
        for o, a, busy in todo:
            print(f"{o.region} [{'busy' if busy else 'free'}] {a}")
        if not todo:
            print("nothing to build in unblocked provinces")
    elif cmd == "run":
        print(run(override_blocked="--override-blocked" in sys.argv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
