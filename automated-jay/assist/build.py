"""Building automation: repair damaged buildings, then apply the settlement priority list (strategy/settlements.json
via buildplan) to every owned province that is not next to an enemy at war, at the start of the turn.

State comes from memory (bot/sensor/world.py): owned regions, slots, buildings, construction in progress, building
health, wars, adjacency. Actions go through the province panel, found in the game's UI tree (bot/sensor/ui.py); every
wait is a condition on the UI tree or memory (tools/wait.py). Verified 2026-10-16, 9.0.4:

  province panel  Provinces tab (hud_campaign/bar_small_top/TabGroup/tab_regions) -> row row_entry_<province>
                  -> settlement_panel with one column CcoCampaignSettlement<region key> per settlement and the
                  slots CcoCampaignBuildingSlotregion_slot_<n> (n = u32 at memory slot + 0x8). The panel slides in
                  from below the screen when it opens (~0.4 s).
  slot popup      HOVERING a slot opens its popup, a child of the slot component, in 18-22 ms. Slots are never
                  clicked: a click on a slot under construction cancels that construction (refunded).
  upgrade         building_construction_popup/.../construction_building_tree: one card per level of the chain, id =
                  building level key, its square_building_button state "built", "normal" (can be built) or "greyed"
                  (not now: no click). The card states settle a frame or two after the popup appears.
  construct       an empty slot's building_categories_popup has one card per category, CcoBuildingSetRecord<set>.
                  Hovering a category builds its construction_building_tree (CcoBuildingChainRecord<chain>, one chain
                  per frame); the category each chain was found in is remembered (runs/build_categories.json), so
                  later constructions of that chain hover one category only.
  repair          a damaged building's popup has options_list/button_repair (next to button_abandon: never clicked).
                  Health: f32 building + 0x38 / max + 0x3C (building = [[slot + 0x190] + 0x20]). A repair costs gold
                  at once (treasury int at faction + 0xD58) and takes a turn: it is a construction in the slot
                  ([[slot + 0x190] + 0x10], u32 + 0x10 = 1; 3 for a construction or upgrade). An upgrade started on a
                  damaged building halts until it is repaired; repairing it keeps the upgrade, which then continues.
  clicks          a popup item is clicked only once the game shows the cursor over that item (its hover state).
Every action is confirmed in memory (construction in the slot, or the treasury going down) before the next one.

    python -X utf8 -m assist.build plan          # what would be done (memory only, no input)
    python -X utf8 -m assist.build run           # do it
"""
from __future__ import annotations
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from . import gamedata as gd
from .buildplan import Building, Province, Settlement, plan_province, strategy
from bot import config
from bot.focus import game_focus
from bot.sensor.world import World, snapshot, region_provinces
from tools import wait
from tools.ui import click, move_to, wheel

PARK = (1700, 700)
PANEL = "settlement_panel"
CATEGORIES_FILE = config.RUNS_DIR / "build_categories.json"
AUTOMATION_FILE = Path(__file__).resolve().parents[1] / "strategy" / "automation.json"
EFFECT_TIMEOUT_S = 1.0        # a click on a card / button that has not started construction by then never will
                              # (measured 2026-10-16: the slot shows construction 10-100 ms after the click)
POPUP_TIMEOUT_S = 0.3         # hovering a slot opens its popup in 18-22 ms (measured 2026-10-16)


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


def _actions(models, blocked: dict, override_blocked: bool = False):
    todo, skipped = [], []
    for p, owned in models.items():
        if p in blocked and not override_blocked:
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
    return todo, skipped


def planned_actions(w: World | None = None):
    """[(OwnedSettlement, Action)] in priority order, for unblocked provinces only."""
    w = w or World()
    snap = snapshot(w)
    if snap is None:
        raise RuntimeError("player faction not found in memory")
    models, blocked = build_models(w, snap)
    todo, skipped = _actions(models, blocked)
    return todo, skipped, snap


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


# ------------------------------------------------------------------ memory, one slot at a time

def slot_ptr(w: World, region_obj: int, idx: int) -> int:
    """The memory slot object: [[region + 0x148] + 0x18] entry idx."""
    L = w.q(region_obj + 0x148) + 0x10
    return w.q(w.q(L + 8) + 8 * idx)


def constructing(w: World, S: int) -> bool:
    """Construction (or a repair, or an upgrade) in progress in this slot: [[S + 0x190] + 0x10] != 0."""
    sb = w.q(S + 0x190)
    return bool(sb) and bool(w.q(sb + 0x10))


def health(w: World, S: int) -> tuple[float, float] | None:
    """(health, max health) of the building in this slot: f32 at building + 0x38 / + 0x3C, building = [[S + 0x190] +
    0x20] (decompiled BUILDING_SCRIPT_INTERFACE.percent_health = 100 * hp / max, 9.0.4). None for an empty slot."""
    sb = w.q(S + 0x190)
    b = w.q(sb + 0x20) if sb else 0
    if not b:
        return None
    hp, mx = struct.unpack("<2f", w.pm.read_bytes(b + 0x38, 8))
    return hp, mx


def damaged(w: World, S: int) -> bool:
    """The building is damaged. An upgrade the game starts on it halts until it is repaired (tooltip "This unfinished
    building is damaged and construction on it has halted", seen 2026-10-16), so it is never upgraded."""
    h = health(w, S)
    return h is not None and h[1] > 0 and h[0] < h[1] - 1e-3


# ------------------------------------------------------------------ UI-tree actions (game focused)

def _ui(w: World | None = None):
    from bot.sensor.ui import UI
    ui = UI(w.s if w is not None else None)
    ui.find_root()
    return ui


def _scroll_into_clip(ui, item: int, what: str) -> bool:
    """Wheel a list until the item lies inside its list_clip (items outside still read visible, off screen)."""
    clip = ui.clip_of(item)
    for _ in range(30):
        if clip is None or ui.in_clip(item):
            return True
        cl, k = ui.comp(clip), ui.comp(item)
        wheel(*cl.center, 1 if k.y < cl.y else -1)
        wait.stable(lambda: ui.comp(item).y, n=2, timeout=1.0, what=f"{what} still", ui=ui, must=False)
    return False


def ui_open_province(ui, o: OwnedSettlement) -> bool:
    """The province panel showing o's settlement column (CcoCampaignSettlement<region>: unique to its province, so a
    panel still showing the previous province never passes)."""
    col = f"CcoCampaignSettlement{o.region}"
    if ui.first(col, under=PANEL) is not None:
        return True
    row = ui.first(f"row_entry_{o.province}")
    if row is None:
        tab = ui.cached("tab_regions", under="bar_small_top")
        if tab is None:
            return False
        if not (ui.state(tab) or "").startswith("selected"):
            click(ui, tab)
        row = wait.wait_until(lambda: ui.first(f"row_entry_{o.province}"), 2.0, f"row_entry_{o.province} listed",
                              must=False)
        if row is None:
            return False
    if not _scroll_into_clip(ui, row, "Provinces list"):
        return False
    click(ui, row)
    return wait.appears(ui, col, under=PANEL, timeout=3.0, must=False) is not None


def ui_slot(ui, w: World, o: OwnedSettlement, idx: int):
    sid = w.u32(slot_ptr(w, o.region_obj, idx) + 8)
    return wait.appears(ui, f"CcoCampaignBuildingSlotregion_slot_{sid}", under=PANEL, timeout=1.0, must=False)


def _slot_popup(ui, slot, cid: str, timeout: float = POPUP_TIMEOUT_S):
    """Hover the slot (never click it: a click on a slot under construction cancels that construction, refunded;
    seen 2026-10-16) until the game opens its popup, a child of the slot component (18-22 ms measured). The settlement
    panel slides in when it opens, so the slot must be still first. The game re-checks hover only when the mouse
    moves: halfway through the timeout the cursor is nudged 1 px. -> the popup, or None (a slot whose construction
    already has its repair queued opens none)."""
    k = ui.comp(slot.ptr)
    off = not (0 <= k.x + k.w / 2 < config.RESOLUTION[0] and 0 <= k.y + k.h / 2 < config.RESOLUTION[1])
    k = wait.stable_rect(ui, slot.ptr, n=3 if off else 1, timeout=2.0, must=False, what=f"{slot.id} still")
    if k is None:
        return None
    x, y = k.center
    move_to(x, y)
    probe = lambda: ui.child(slot.ptr, cid, visible_only=True)
    p = wait.wait_until(probe, timeout / 2, f"{cid} on {slot.id}", must=False)
    if p is None:
        move_to(x + 1, y)
        wait.next_frame(1, ui)
        move_to(x, y)
        p = wait.wait_until(probe, timeout / 2, f"{cid} on {slot.id} (nudged)", must=False)
    return p


def _await_started(w: World, S: int, what: str) -> bool:
    return bool(wait.wait_until(lambda: constructing(w, S), EFFECT_TIMEOUT_S, what, must=False))


def _settled(ui, ptr: int, what: str):
    """A popup item once the popup is laid out: its rectangle and state (and its square_building_button's state)
    unchanged for 3 frames. Measured 2026-10-16: right after the popup appears the options buttons are still being
    placed and a card can read "normal" for a frame before it turns "greyed". -> Comp, or None."""
    btn = ui.child(ptr, "square_building_button")

    def look():
        k = ui.comp(ptr)
        return (k.x, k.y, k.w, k.h, ui.state(ptr) or "", (ui.state(btn) or "") if btn else "")
    got = wait.stable(look, n=3, timeout=1.0, what=f"{what} laid out", must=False, ui=ui)
    return ui.comp(ptr) if got is not None else None


def _press(ui, ptr: int, what: str, settled: bool = False) -> bool:
    """Click a popup item only once the game shows the cursor over THAT item (its hover state), never on a guess:
    in a building popup the Repair button sits next to Abandon (2026-10-16: a click aimed while the popup was still
    being laid out landed on Abandon). False, without a click, when the hover does not register."""
    k = ui.comp(ptr) if settled else _settled(ui, ptr, what)
    if k is None or not ui.effective_visible(ptr):
        return False
    probe = ui.hover_probe(ptr)
    if probe is None:
        return False
    x, y = k.center
    hovered = lambda: ui.state_ptr(probe[0]) in probe[1]
    move_to(x, y)
    if not wait.wait_until(hovered, 0.15, f"hover on {what}", must=False):
        move_to(x + 1, y)                         # the game re-checks hover only when the mouse moves
        wait.next_frame(1, ui)
        move_to(x, y)
        if not wait.wait_until(hovered, 0.15, f"hover on {what} (nudged)", must=False):
            return False
    click(ui, ptr)                                # hovered already: the button goes down at once
    return True


def ui_upgrade(ui, w: World, S: int, slot, level_key: str) -> bool:
    pop = _slot_popup(ui, slot, "building_construction_popup")
    card = wait.wait_until(lambda: ui.first(level_key, under=pop), 1.0, f"{level_key} card", must=False) if pop else None
    if card is None:
        return False
    if _settled(ui, card, level_key) is None or _greyed(ui, card):
        return False                              # the game would ignore the click
    if not _press(ui, card, level_key, settled=True):
        return False
    return _await_started(w, S, f"{level_key} under construction")


def _greyed(ui, card: int) -> bool:
    """The level card cannot be built now (square_building_button state "greyed")."""
    btn = ui.child(card, "square_building_button")
    return btn is not None and (ui.state(btn) or "") == "greyed"


def ui_repair(ui, w: World, F: int, S: int, slot) -> tuple[str, int]:
    """Repair the building in this slot: its popup's options_list/button_repair. -> ("repaired", cost), ("queued", 0)
    when the game offers no repair (one is already under way), or ("not started", 0). A repair costs gold at once
    (faction treasury, int at F + 0xD58, goes down 6-75 ms after the click) and takes a turn: a damaged building
    gets a repair construction ([[S + 0x190] + 0x10], its u32 + 0x10 = 1); a halted upgrade keeps its construction
    and continues once repaired."""
    busy = constructing(w, S)
    pop = _slot_popup(ui, slot, "building_construction_popup")
    if pop is None:
        return ("queued" if busy else "not started"), 0
    btn = wait.wait_until(lambda: ui.first("button_repair", under=pop), 0.25, "button_repair", must=False)
    if btn is None:
        return ("queued" if busy else "not started"), 0
    gold = treasury(w, F)
    if ui.id(btn) != "button_repair" or not _press(ui, btn, "button_repair"):
        return "not started", 0
    after = wait.value_changes(lambda: treasury(w, F), gold, timeout=EFFECT_TIMEOUT_S, must=False,
                               what=f"repair paid for {slot.id}")
    if after is None or after >= gold:
        return "not started", 0
    if not busy:
        _await_started(w, S, f"repair under way in {slot.id}")
    return "repaired", gold - after


def _learned() -> dict[str, str]:
    try:
        return json.loads(CATEGORIES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _learn(chains: list[str], category: str) -> None:
    m = _learned()
    if all(m.get(c) == category for c in chains):
        return
    m.update({c: category for c in chains})
    try:
        CATEGORIES_FILE.write_text(json.dumps(m, indent=1, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def _tree_chains(ui, under: int) -> tuple:
    """Components in the chain list of the construction_building_tree shown below `under` (() when none is)."""
    t = ui.first("construction_building_tree", under=under)
    cl = ui.first("chain_list", under=t) if t else None
    return tuple(ui.children(cl)) if cl else ()


def _category_tree(ui, under: int, before: tuple):
    """Once the hovered category's construction_building_tree is built (its chain list differs from `before`, then
    is unchanged for 3 frames: measured 2026-10-16, the game adds one chain per frame, 15-45 ms after the hover):
    (chain list pointers, {chain: chain component})."""
    chains = lambda: _tree_chains(ui, under)
    got = wait.wait_until(lambda: (lambda c: c if c and c != before else None)(chains()), 1.0,
                          "category tree rebuilt", must=False)
    if got is None:
        return None
    kids = wait.stable(chains, n=3, timeout=1.0, what="category tree complete", must=False, ui=ui) or got
    out = {}
    for c in kids:
        cid = ui.id(c) or ""
        if cid.startswith("CcoBuildingChainRecord"):
            out[cid[len("CcoBuildingChainRecord"):]] = c
    return kids, out


def ui_construct(ui, w: World, S: int, slot, level_key: str, chain: str) -> bool:
    pop = _slot_popup(ui, slot, "building_categories_popup")
    lst = ui.first("category_list", under=pop) if pop else None
    if lst is None:
        return False
    cats = [c for c in ui.children(lst) if (ui.id(c) or "").startswith("CcoBuildingSetRecord")]
    known = _learned().get(chain)
    cats.sort(key=lambda c: ui.id(c) != known)
    before = _tree_chains(ui, slot.ptr)
    for cat in cats:
        move_to(*ui.comp(cat).center)
        got = _category_tree(ui, slot.ptr, before)
        if got is None:
            continue
        before, chains = got
        _learn(list(chains), ui.id(cat) or "")
        if chain not in chains:
            continue
        card = ui.first(level_key, under=chains[chain])
        if card is None:
            continue
        if _settled(ui, card, level_key) is None or _greyed(ui, card):
            return False
        if not _press(ui, card, level_key, settled=True):
            return False
        return _await_started(w, S, f"{level_key} under construction")
    return False


# ------------------------------------------------------------------ repairs

@dataclass
class Repair:
    o: OwnedSettlement
    idx: int
    level_key: str
    estimate: int          # level cost x damaged fraction: the game's price, or above it where a local discount applies


def construction_kind(w: World, S: int) -> int | None:
    """u32 at construction + 0x10: 1 for a repair, 3 for a construction or upgrade (9.0.4, 2026-10-16)."""
    sb = w.q(S + 0x190)
    c = w.q(sb + 0x10) if sb else 0
    return w.u32(c + 0x10) if c else None


def buildings_setting(name: str, default=True):
    """strategy/automation.json "buildings" settings (read fresh at every pass)."""
    try:
        a = json.loads(AUTOMATION_FILE.read_text(encoding="utf-8"))
        return a.get("buildings", {}).get(name, default)
    except (OSError, ValueError, AttributeError):
        return default


def planned_repairs(w: World, models, blocked: dict, override_blocked: bool = False) -> list[Repair]:
    """Damaged buildings in provinces where building is allowed (the war block applies to repairs too), skipping
    those already under repair. Province by province, slot order (main building first)."""
    if not buildings_setting("repair_damaged"):
        return []
    levels = {l.key: l for ls in gd.chains().values() for l in ls}
    out = []
    for p, owned in models.items():
        if p in blocked and not override_blocked:
            continue
        for o in owned:
            for i, st in enumerate(o.slot_states):
                if not st.building:
                    continue
                S = slot_ptr(w, o.region_obj, i)
                h = health(w, S)
                if h is None or not damaged(w, S) or construction_kind(w, S) == 1:
                    continue
                lv = levels.get(st.building)
                out.append(Repair(o, i, st.building, round((lv.cost if lv else 0) * (1 - h[0] / h[1]))))
    return out


def treasury(w: World, F: int) -> int:
    """The faction's treasury: int at faction + 0xD58."""
    return struct.unpack("<i", w.pm.read_bytes(F + 0xD58, 4))[0]


def run(log=print, override_blocked: bool = False) -> str:
    w = World()
    snap = snapshot(w)
    if snap is None:
        raise RuntimeError("player faction not found in memory")
    models, blocked = build_models(w, snap)
    todo, skipped = _actions(models, blocked)
    if override_blocked:                          # test only: plan blocked provinces too
        todo, _ = _actions(models, blocked, override_blocked=True)
    repairs = planned_repairs(w, models, blocked, override_blocked)
    done, problems = [], []
    gold = w.s.read().treasury or 0
    ui = _ui(w)
    with game_focus():
        # 1. repairs, before any construction or upgrade (player rule, 2026-10-16)
        for r in repairs:
            o, name = r.o, gd.level_name(r.level_key)
            if r.estimate > gold:
                problems.append(f"{o.region}: repair of {name} needs {r.estimate} gold")
                continue
            if not ui_open_province(ui, o):
                problems.append(f"{o.region}: could not open its province")
                continue
            slot = ui_slot(ui, w, o, r.idx)
            if slot is None:
                problems.append(f"{o.region}: slot not on screen")
                continue
            how, cost = ui_repair(ui, w, snap.faction, slot_ptr(w, o.region_obj, r.idx), slot)
            if how == "repaired":
                gold -= cost
                done.append(f"repaired {name} in {gd.place_name(o.region)}")
                log(f"build: {done[-1]}")
            elif how == "not started":
                problems.append(f"{o.region}: repair of {name} not started")
        # 2. constructions and upgrades
        for o, a, busy in todo:
            idx = slot_index_for(o, a)
            S = slot_ptr(w, o.region_obj, idx) if idx is not None else 0
            if S and constructing(w, S):
                continue                          # being built, upgraded or repaired
            if a.cost > gold:
                problems.append(f"{o.region}: {a.item} needs {a.cost} gold")
                continue
            if idx is None or not a.level_key:
                problems.append(f"{o.region}: no slot for {a.item}")
                continue
            if a.kind != "construct" and damaged(w, S):
                problems.append(f"{o.region}: {a.item} waits for a repair")
                continue
            if not ui_open_province(ui, o):
                problems.append(f"{o.region}: could not open its province")
                continue
            slot = ui_slot(ui, w, o, idx)
            if slot is None:
                problems.append(f"{o.region}: slot not on screen")
                continue
            if a.kind == "construct":
                chain = next((t.chain for t in plan_targets(o) if t.item == a.item), None)
                ok = chain is not None and ui_construct(ui, w, S, slot, a.level_key, chain)
            else:
                ok = ui_upgrade(ui, w, S, slot, a.level_key)
            if ok:
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
    from .buildplan import final_layout
    return final_layout(o.model, lambda c, s: True)


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if cmd == "plan":
        todo, skipped, snap = planned_actions()
        print("at war with:", snap.at_war)
        for p, why in skipped:
            print(f"BLOCKED {p}: {why}")
        w = World()
        models, blocked = build_models(w, snap)
        for r in planned_repairs(w, models, blocked):
            print(f"{r.o.region} repair slot {r.idx} {gd.level_name(r.level_key)} (about {r.estimate} gold)")
        for o, a, busy in todo:
            print(f"{o.region} [{'busy' if busy else 'free'}] {a}")
        if not todo:
            print("nothing to build in unblocked provinces")
    elif cmd == "run":
        from bot.focus import return_to_terminal
        try:
            print(run(override_blocked="--override-blocked" in sys.argv))
        finally:
            return_to_terminal()
    return 0


if __name__ == "__main__":
    sys.exit(main())
