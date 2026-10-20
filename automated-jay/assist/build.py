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
AUTOMATION_FILE = config.STRATEGY_DIR / "automation.json"
# a click on a card / button that has not started construction by then never will
                              # (measured 2026-10-16: the slot shows construction 10-100 ms after the click)
POPUPS = ("building_categories_popup", "building_construction_popup")
POPUP_TIMEOUT_S = 1.0         # hovering a slot opens its popup in 18-22 ms (measured 2026-10-16); 0.3 s missed it
                              # while the previous slot's popup was still closing (2026-10-19, Swartzhafen)


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
                # a new building under construction: what it builds, from memory (2026-10-19: unknown, the Temple at
                # Zhufbar was planned a second time and the game greyed its card, "built_inactive")
                tl = level_of(s.target) if s.target else None
                rest.append(Building(*tl) if tl else Building("__constructing__", 0))
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
                elif a.kind == "replace" and buildings_setting("off_list_buildings", "ask") == "replace"                         and replaceable(o, slot_index_for(o, a)):
                    todo.append((o, a, busy))
    todo.sort(key=lambda t: spend_rank(t[0], t[1]))
    return todo, skipped


# Spending order across all provinces (player decision 2026-10-20). Before, the gold went province by province down
# each list and anything affordable lower down was bought while a top item waited, so the recruit buildings and the
# landmarks never got saved for. Now: main building (and port) upgrades, which unlock slots and tiers; the Warpstone
# Reactor line (+30/40/50% income from every building in the province, paid back in about 6 turns, landmarks' income
# included); landmarks; the army template's recruit buildings, the capital closest to tier 5 first; then the rest in
# settlements.json order. The settlement list itself still decides which buildings get a slot.
RECRUIT_CHAINS = ("wh3_dlc29_skv_stormfiends", "wh2_main_skv_engineers")
REACTOR_CHAIN = "wh2_main_skv_energy"
SAVE_TURNS = 2              # a top item affordable within this many turns of net income is saved for
SAVE_UP_TO = 3              # saving only for ranks 0-3 (main, Reactor, landmarks, recruit buildings), never fillers
SAVING: dict = {}           # this turn's saving: {"turn", "gold", "item", "rank"}; the army step keeps the gold too


def spend_rank(o: OwnedSettlement, a) -> tuple:
    """Where an action stands in the spending order (lower first)."""
    from .buildplan import current_tier
    if a.kind in ("upgrade_main", "upgrade_port"):
        return (0, 0, a.cost)
    lv = level_of(a.level_key) if a.level_key else None
    chain = lv[0] if lv else None
    if chain == REACTOR_CHAIN:
        return (1, 0, a.cost)
    if chain is not None and chain in o.model.landmarks:
        return (2, 0, a.cost)
    if chain in RECRUIT_CHAINS:
        return (3, -current_tier(o.model), o.province, RECRUIT_CHAINS.index(chain))
    names = [e["name"] for e in strategy()["priority"]]
    return (4, names.index(a.item) if a.item in names else len(names), a.cost)


def saving_reserve(w: World, F: int | None = None) -> int:
    """Gold the building step is saving this turn (the army step leaves it alone), 0 when none."""
    try:
        turn = w.s.read().turn
    except Exception:
        return 0
    return int(SAVING.get("gold", 0)) if SAVING.get("turn") == turn else 0


SPECIAL = ("special", "landmark", "legendary", "unique", "wonder")


def replaceable(o, idx) -> bool:
    """May the off-list rule demolish what stands in this slot? Only a normal (secondary) slot, never the main
    building or the port slot, and never a special building (a captured landmark, a legendary port: nothing that can
    be rebuilt). 2026-10-17: the plan wanted to demolish Bordeleaux's legendary port to put a Breeding Pit in the port
    slot."""
    if idx is None or idx >= len(o.slot_states):
        return False
    st = o.slot_states[idx]
    return st.type == "secondary" and not (st.building and any(k in st.building for k in SPECIAL))


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
    shown = lambda: ui.root_child(PANEL) and ui.first(col, under=PANEL)   # (a lookup under a closed panel walks
    if shown():                                                          # the whole tree)
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
    return wait.wait_until(shown, 3.0, f"{col} shown", must=False) is not None


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
    # another slot's popup still closing takes the hover (2026-10-19, Swartzhafen: the next slot's popup never came)
    pan = ui.first(PANEL)
    others = lambda: [c for c, n, _r in (ui.nodes(pan) if pan else []) if n in POPUPS
                      and ui.effective_visible(c) and ui.parent(c) != slot.ptr]
    wait.wait_until(lambda: not others(), 1.0, "previous building popup closed", must=False)
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
    """(A click that already went in: no command watch.) The slot is under construction in memory."""
    from bot.sensor.commands import EFFECT_CAP_S
    return bool(wait.wait_until(lambda: constructing(w, S), EFFECT_CAP_S, what, must=False))


def _press_started(ui, w: World, S: int, card: int, level_key: str) -> bool:
    """Press a construct / upgrade card and wait until memory shows the slot under construction ([[S+0x190]+0x10]).
    Paced by the game itself (bot/sensor/commands.py, player rule 2026-10-19): a click that wrote no command to the
    game is pressed once more; after a command, never (in multiplayer a second click could cancel the first)."""
    from bot.sensor import commands
    st, _ = commands.act_retry(w.pm, lambda: _press(ui, card, level_key, settled=True), lambda: constructing(w, S))
    if st != "done" and commands.WHY.get(st):
        REASON["last"] = commands.WHY[st]
    return st == "done"


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


REASON = {"last": ""}          # why the last construct / upgrade was not started (for the step's result line)


def _press(ui, ptr: int, what: str, settled: bool = False) -> bool:
    """Click a popup item only once the game shows the cursor over THAT item (its hover state), never on a guess:
    in a building popup the Repair button sits next to Abandon (2026-10-16: a click aimed while the popup was still
    being laid out landed on Abandon). False, without a click, when the hover does not register."""
    k = ui.comp(ptr) if settled else _settled(ui, ptr, what)
    if k is None or not ui.effective_visible(ptr):
        REASON["last"] = "its card is not shown"
        return False
    probe = ui.hover_probe(ptr)
    if probe is None:
        # the part of the card that shows the hover is in a state without one: the game does not take the click
        # (2026-10-18: the Morskittar Engine's card at Zhufbar, shown but locked by the story)
        btn = ui.child(ptr, "square_building_button")
        REASON["last"] = f"the game does not take a click on it (card {ui.state(btn) if btn else ui.state(ptr)})"
        return False
    x, y = k.center
    hovered = lambda: ui.state_ptr(probe[0]) in probe[1]
    move_to(x, y)
    if not wait.wait_until(hovered, 0.15, f"hover on {what}", must=False):
        move_to(x + 1, y)                         # the game re-checks hover only when the mouse moves
        wait.next_frame(1, ui)
        move_to(x, y)
        if not wait.wait_until(hovered, 0.15, f"hover on {what} (nudged)", must=False):
            REASON["last"] = "the cursor did not register on its card"
            return False
    click(ui, ptr)                                # hovered already: the button goes down at once
    return True



def _why_greyed(ui, card: int) -> str:
    """The greyed card's tooltip, the lines that say why it cannot be built (the game's own words)."""
    from .army_builder import card_text
    btn = ui.child(card, "square_building_button")
    import re as _re
    for c in (btn, card):
        t = card_text(ui, c) if c else ""
        t = _re.sub(r"\[\[[^\]]*\]\]", "", t).replace("||", "\n")
        lines = [x.strip() for x in t.splitlines() if x.strip()]
        bad = [x for x in lines if any(k in x.lower() for k in ("requires", "cannot", "not enough", "already",
                                                                 "need", "insufficient", "locked", "unavailable"))]
        if bad or lines:
            return "; ".join(bad or lines[-1:])[:160]
    return ""




def ui_upgrade(ui, w: World, S: int, slot, level_key: str) -> bool:
    REASON["last"] = ""
    pop = _slot_popup(ui, slot, "building_construction_popup")
    card = wait.wait_until(lambda: ui.first(level_key, under=pop), 1.0, f"{level_key} card", must=False) if pop else None
    if card is None:
        return False
    if _settled(ui, card, level_key) is None:
        return False
    if _greyed(ui, card):                         # the game would ignore the click
        REASON["last"] = "greyed out" + (f": {r}" if (r := _why_greyed(ui, card)) else "")
        return False
    return _press_started(ui, w, S, card, level_key)


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
    if ui.id(btn) != "button_repair":
        return "not started", 0
    from bot.sensor import commands
    st, after = commands.act(w.pm, lambda: _press(ui, btn, "button_repair"),
                             lambda: (lambda g: (g,) if g < gold else None)(treasury(w, F)))   # (a tuple: 0 gold left
    if st != "done":                                                                      # is still paid)
        return "not started", 0
    after = after[0]
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
    stale = got is None
    if stale:
        # the tree did not change: the hovered category is the one already shown (2026-10-19, Karag Dromar: four
        # 1 s timeouts and the Breeding Pit counted unread). The shown tree is used as it is; its cards carry the
        # level keys, so a card found there is the right one to click. stale: not proof of what it offers.
        got = chains()
        if not got:
            return None
    kids = wait.stable(chains, n=3, timeout=1.0, what="category tree complete", must=False, ui=ui) or got
    out = {}
    for c in kids:
        cid = ui.id(c) or ""
        if cid.startswith("CcoBuildingChainRecord"):
            out[cid[len("CcoBuildingChainRecord"):]] = c
    return kids, out, stale


def ui_construct(ui, w: World, S: int, slot, level_key: str, chain: str, region: str = "") -> bool:
    REASON["last"] = ""
    pop = _slot_popup(ui, slot, "building_categories_popup")
    lst = ui.first("category_list", under=pop) if pop else None
    if lst is None:
        return False
    # the popup adds its categories over a few frames: listed too early it had 2 of its 5 (2026-10-19, Swartzhafen:
    # the Breeding Pit taken for "not offered"); listed once the set has held for 3 frames
    ids = lambda: tuple(c for c in ui.children(lst) if (ui.id(c) or "").startswith("CcoBuildingSetRecord"))
    wait.wait_until(ids, 1.0, "building categories listed", must=False)
    cats = list(wait.stable(ids, n=3, timeout=1.0, what="building categories complete", must=False, ui=ui) or ids())
    # the popup grows its category icons in over a few frames: hovered before then, the cursor misses the icon and
    # its tree never shows (2026-10-19, Swartzhafen: an icon still 1 px tall, the Breeding Pit taken for "not
    # offered" for the rest of the session)
    rects = lambda: tuple(v for c in cats for k in (ui.comp(c),) for v in (k.x, k.y, k.w, k.h))
    wait.stable(rects, n=3, timeout=1.0, what="building categories laid out", must=False, ui=ui)
    known = _learned().get(chain)
    cats.sort(key=lambda c: ui.id(c) != known)
    before = _tree_chains(ui, slot.ptr)
    unread, stale = 0, False
    for cat in cats:
        got = None
        for nudge in (0, 1):                      # the game re-checks hover only when the mouse moves
            x, y = ui.comp(cat).center
            move_to(x + nudge, y)
            got = _category_tree(ui, slot.ptr, before)
            if got is not None:
                break
        if got is None:
            unread += 1
            continue
        before, chains, was_stale = got
        stale = stale or was_stale
        if not was_stale:
            _learn(list(chains), ui.id(cat) or "")
        if chain not in chains:
            continue
        card = ui.first(level_key, under=chains[chain])
        if card is None:
            continue
        # the tree slides in too: its card can read invisible for a few frames ("its card is not shown", Swartzhafen
        # turns 11-13)
        wait.wait_until(lambda: ui.effective_visible(card), 1.0, f"{level_key} shown", must=False)
        if _settled(ui, card, level_key) is None:
            return False
        if _greyed(ui, card):
            REASON["last"] = "greyed out" + (f": {r}" if (r := _why_greyed(ui, card)) else "")
            return False
        return _press_started(ui, w, S, card, level_key)
    if unread or stale:                           # not every category was seen: not a verdict, tried again next pass
        unread = unread or 1
        REASON["last"] = f"{unread} building categor{'y' if unread == 1 else 'ies'} did not open on hover"
        return False
    # memory decides what can be built (locks, main level, development points, cost); the popup is only where the
    # card is clicked, so a card not found there is a miss of the UI, never "the game does not offer it" (player
    # 2026-10-19: memory first, the popup only as the fallback)
    REASON["last"] = "its card was not found in the building popup (UI); memory says it can be built: tried again"
    return False


# ------------------------------------------------------------------ repairs

@dataclass
class Repair:
    o: OwnedSettlement
    idx: int
    level_key: str
    estimate: int          # level cost x damaged fraction: the game's price, or above it where a local discount applies


def slot_building(w: World, o, idx: int) -> str | None:
    """The building in o's slot idx, from a fresh read of memory (None: the slot is empty)."""
    models, _ = build_models(w, snapshot(w))
    o2 = next((x for xs in models.values() for x in xs if x.region == o.region), None)
    return o2.slot_states[idx].building if o2 and idx < len(o2.slot_states) else None


def ui_demolish(ui, w: World, o, idx: int, slot) -> str | None:
    """Demolish the building in this slot (player rule 2026-10-17: in a province the assistant manages, a building
    that is not on the settlement list is replaced by the planned one; frontline provinces stay the player's).
    The slot's hover popup has options_list/button_raze; a confirmation box, if the game shows one, is accepted.
    -> "gone" (the slot is empty), "pending" (the game demolishes at the end of the turn: until then the building
    stays in its slot and the slot shows work under way, [[S + 0x190] + 0x10] set; seen 2026-10-17, when every
    demolish was taken for a failure because the slot was not empty within 3 s), None: not demolished."""
    pop = _slot_popup(ui, slot, "building_construction_popup")
    if pop is None:
        return None
    btn = wait.wait_until(lambda: (lambda b: b if b and ui.effective_visible(b) else None)(
        ui.first("button_raze", under=pop)), 0.5, "button_raze", must=False)
    if btn is None:
        return None
    from bot.sensor import commands
    S = slot_ptr(w, o.region_obj, idx)
    effect = lambda: "gone" if slot_building(w, o, idx) is None else "pending" if constructing(w, S) else None
    with commands.Watch(w.pm) as cw:              # the raze click itself may be the command (no confirmation)
        if not _press(ui, btn, "button_raze"):
            return None
        box = wait.wait_until(lambda: ui.root_child("dialogue_box") or (cw.count and "sent"), 1.0,
                              "demolish confirmation", must=False)
    if box and box != "sent":
        tick = ui.first("button_tick", under=box)
        if tick is None:
            return None
        st, v = commands.act(w.pm, lambda: click(ui, tick), effect)
        wait.gone(ui, box, timeout=2.0, must=False, what="confirmation closed")
        return v if st == "done" else None
    if not cw.count and cw.ok:                    # no box and no command: the click did not reach the game
        return effect()
    return wait.wait_until(effect, commands.EFFECT_CAP_S, "building demolished", must=False) or None


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
    replacing = buildings_setting("off_list_buildings", "ask") == "replace"
    out = []
    for p, owned in models.items():
        if p in blocked and not override_blocked:
            continue
        for o in owned:
            listed = {t.chain for t in plan_targets(o)} | {strategy()["port_chain"]} if replacing else set()
            for i, st in enumerate(o.slot_states):
                if not st.building:
                    continue
                lv0 = level_of(st.building)
                if replacing and i != 0 and lv0 and lv0[0] not in listed:
                    continue                     # an off-list building is replaced, not repaired (2026-10-17)
                S = slot_ptr(w, o.region_obj, i)
                h = health(w, S)
                if h is None or not damaged(w, S) or construction_kind(w, S) == 1:
                    continue
                lv = levels.get(st.building)
                out.append(Repair(o, i, st.building, round((lv.cost if lv else 0) * (1 - h[0] / h[1]))))
    return out


def main_level_short(w: World, o, a) -> int | None:
    """The main building level the action's level needs, when the settlement's main building is below it (memory:
    the level record's requirement and the main slot's level), else None."""
    from bot.sensor.buildings import level_info
    info = level_info(w, a.level_key) if a.level_key and a.kind != "upgrade_main" else None
    if not info or not info["main_level"]:
        return None
    try:
        main = w.slots(o.region_obj)[0].level
    except Exception:
        return None
    return info["main_level"] if main is not None and main < info["main_level"] else None


def locked(w: World, F: int, a) -> bool:
    """The action's level or chain is locked for F by the game's scripts (bot/sensor/buildings.restricted)."""
    from bot.sensor.buildings import restricted
    if not a.level_key:
        return False
    r = restricted(w, F)
    return a.level_key in r or a.level_key.rsplit("_", 1)[0] in r


def real_cost(w: World, F: int, a) -> int:
    """What the game charges for the action's level, from memory (bot/sensor/buildings.construction_cost); the DB
    price only when the record cannot be read."""
    from bot.sensor.buildings import construction_cost
    c = construction_cost(w, F, a.level_key) if a.level_key else None
    return a.cost if c is None else c


def development_points(w: World, region_obj: int, F: int) -> int | None:
    """The province's development points for faction F, from memory (binding region:development_points,
    FUN_1427ae080, 9.0.4 2026-10-19): province P = [[R+0x3A8]+0x10]; its faction entries [P+0xA0] (count u32
    P+0x9C), the entry whose faction [[FP+0xD8]+0x10] has id u32 +8 == F's; u32 FP+0x3D8. Checked live: Black Water
    2, as the province panel showed; an upgrade takes its points the moment it starts (Southern Sylvania 1 -> 0) and
    a cancel gives them back, so a second upgrade in the same province reads 0 (the cards the game greyed out on
    2026-10-18, Eschen and Swartzhafen after Castle Drakenhof)."""
    try:
        P = w.q(w.q(region_obj + 0x3A8) + 0x10)
        fid = w.u32(F + 8)
        n, arr = w.u32(P + 0x9C), w.q(P + 0xA0)
        for i in range(min(n, 32)):
            FP = w.q(arr + 8 * i)
            o = w.q(FP + 0xD8)
            fac = w.q(o + 0x10) if o else 0
            if fac and w.u32(fac + 8) == fid:
                return w.u32(FP + 0x3D8)
    except Exception:
        pass
    return None


def dev_cost(level_key: str | None, w: World | None = None) -> int:
    """A building level's development point cost: from the running game's level record (bot/sensor/buildings.
    level_info), building_levels_tables only when it cannot be read. Main building upgrades need them."""
    if not level_key:
        return 0
    if w is not None:
        from bot.sensor.buildings import level_info
        info = level_info(w, level_key)
        if info is not None:
            return info["dev_points"]
    if not _DEV:
        _DEV.update({r["level_name"]: int(r.get("development_point_cost") or 0)
                     for r in gd._load("building_levels_tables")})
    return _DEV.get(level_key, 0)


_DEV: dict = {}


def treasury(w: World, F: int) -> int:
    """The faction's treasury: int at faction + 0xD58."""
    return struct.unpack("<i", w.pm.read_bytes(F + 0xD58, 4))[0]


FAILED: dict = {}          # (region, item) -> why the last run did not get it under way (a UI failure)
PROTECTED: set = set()     # (region, slot index) the last run kept for the Construction Cavern


def _failed(problems: list, o, a, text: str) -> None:
    problems.append(text)
    FAILED[(o.region, a.item)] = text.split(": ", 1)[-1]


def missed(w: World | None = None) -> list[str]:
    """The memory check after the step (player request 2026-10-19: Swartzhafen's empty slot was missed for turns
    while the step read "verified"). The plan is made again from memory, after the run: every action in it must be
    under way in its slot ([[S+0x190]+0x10]) or have a reason read from memory why not (the gold, a damaged building,
    the Cavern's slot, a blocked province is not planned at all). Anything else is missed: with the reason the run
    saw in the UI (a greyed card: the game's reason is not decoded from memory yet), or "not attempted"."""
    w = w or World()
    snap = snapshot(w)
    if snap is None:
        return []
    models, blocked = build_models(w, snap)
    todo, _ = _actions(models, blocked)
    gold = w.s.read().treasury or 0
    keep = SAVING.get("rank") if SAVING.get("turn") == w.s.read().turn else None
    out = []
    for o, a, _busy in todo:
        if keep is not None and spend_rank(o, a) > keep:
            continue                              # held back: the run saved for a higher item (SAVING)
        idx = slot_index_for(o, a)
        S = slot_ptr(w, o.region_obj, idx) if idx is not None else 0
        if S and constructing(w, S):
            continue
        why = FAILED.get((o.region, a.item))
        if why is None:                           # not tried: only a reason from memory excuses it
            if (real_cost(w, snap.faction, a) > gold or (o.region, idx) in PROTECTED or locked(w, snap.faction, a)
                    or main_level_short(w, o, a) is not None):
                continue
            need = dev_cost(a.level_key, w)
            if need and (have := development_points(w, o.region_obj, snap.faction)) is not None and have < need:
                continue
            if S and a.kind not in ("construct", "replace") and damaged(w, S):
                continue
            why = "not attempted"
        why = why.removeprefix(f"{a.item} not started ").strip("()") or why
        out.append(f"{gd.place_name(o.region)}: {a.item} ({why})")
    return out


def run(log=print, override_blocked: bool = False) -> str:
    FAILED.clear()
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
        # 2. Ikit's Forbidden Workshop: a Construction Cavern while the workshop needs one for level 2 (player build,
        #    2026-10-17; assist/workshop.py). The planned Warp-Turbine line counts (2026-10-20); only when no managed
        #    settlement plans it is a temporary one built and kept away from the off-list rule until it has counted
        from . import workshop
        off_list = [(o, i) for o, a, _b in todo if a.kind == "replace" for i in [slot_index_for(o, a)] if i is not None]
        def priority_of(o, building):                 # higher = lower priority on the settlement list
            order = [t.chain for t in plan_targets(o)]
            lv = level_of(building)
            return order.index(lv[0]) if lv and lv[0] in order else len(order)
        cavern = gd.chains()[workshop.CAVERN_CHAIN][0]
        from .buildplan import current_tier
        turn = w.s.read().turn
        faction = w.faction_name(snap.faction)
        protected, target, note = workshop.plan(w, snap.faction, models, blocked, turn, off_list,
                                                priority_of=priority_of, special=SPECIAL,
                                                can_host=lambda o: current_tier(o.model) >= cavern.tier,
                                                faction=faction,
                                                planned=lambda o: any(t.chain == workshop.CAVERN_CHAIN
                                                                      for t in plan_targets(o)))
        if note:
            problems.append(f"workshop: {note}")
        if target is not None:
            o, idx, demolish = target
            S = slot_ptr(w, o.region_obj, idx)
            lv = gd.chains()[workshop.CAVERN_CHAIN][0]
            old = o.slot_states[idx].building
            place = gd.place_name(o.region)
            protected.add((o.region, idx))
            if lv.cost > gold:
                problems.append(f"workshop: a Construction Cavern needs {lv.cost} gold")
            elif not ui_open_province(ui, o) or (slot := ui_slot(ui, w, o, idx)) is None:
                problems.append(f"workshop: could not open the Cavern's slot in {place}")
            else:
                # the one Cavern's slot, recorded before the first click: whatever a click does, no other slot is
                # ever chosen (player rule: one Cavern, ever)
                workshop.commit(o.region, idx, turn, faction=faction)
                how = ui_demolish(ui, w, o, idx, slot) if demolish else "gone"
                if how == "pending":
                    done.append(f"{place}: demolishing {gd.level_name(old)} for the Construction Cavern (built there "
                                f"next turn; the {gd.level_name(old)} is rebuilt once the Cavern has counted)")
                    log(f"build: {done[-1]}")
                elif how is None:
                    problems.append(f"workshop: could not demolish {gd.level_name(old)} in {place} for the Cavern")
                elif (slot := ui_slot(ui, w, o, idx)) is not None and ui_construct(
                        ui, w, S, slot, workshop.CAVERN, workshop.CAVERN_CHAIN):
                    workshop.commit(o.region, idx, turn, started=True)
                    gold -= lv.cost
                    done.append(f"{place}: Construction Cavern (for the Forbidden Workshop, removed again once it "
                                f"has counted)")
                    log(f"build: {done[-1]}")
                else:
                    problems.append(f"workshop: could not start the Construction Cavern in {place}")
        # 3. constructions and upgrades, in spending order; a top item affordable within SAVE_TURNS turns of net
        #    income is saved for: nothing ranked below it is bought this turn (player decision 2026-10-20)
        SAVING.clear()
        try:
            from bot.sensor.economy import read as economy
            net = max(economy(w, snap.faction).net, 0)
        except Exception:
            net = 0
        held = 0
        for o, a, busy in todo:
            rank = spend_rank(o, a)
            if SAVING and rank > SAVING["rank"]:
                held += 1
                continue
            idx = slot_index_for(o, a)
            S = slot_ptr(w, o.region_obj, idx) if idx is not None else 0
            # right before the action, from memory: the plan still holds (multiplayer, 2026-10-19: the other players
            # move while a pass runs; a settlement can be taken, a slot changed)
            if w.region_owner(o.region_obj) != snap.faction:
                problems.append(f"{o.region}: no longer yours (taken during the pass)")
                continue
            if idx is not None and idx < len(o.slot_states):
                now = w.slots(o.region_obj)
                if idx < len(now) and now[idx].building != o.slot_states[idx].building and not now[idx].constructing:
                    problems.append(f"{o.region}: slot changed since the plan ({o.slot_states[idx].building} -> "
                                    f"{now[idx].building}); planned again next pass")
                    continue
            if (o.region, idx) in protected:          # the Cavern's slot (also while it is empty, waiting for it)
                problems.append(f"{o.region}: Construction Cavern slot kept for the Forbidden Workshop (level 2)")
                continue
            if S and constructing(w, S):
                if a.kind == "replace":           # the game offers no Demolish on a slot with work under way
                    problems.append(f"{o.region}: {a.detail} once the work under way in that slot is done")
                continue                          # being built, upgraded or repaired
            if locked(w, snap.faction, a):
                problems.append(f"{o.region}: {a.item} is locked by the game (a story or event lock, from memory)")
                continue
            if (lvl := main_level_short(w, o, a)) is not None:
                problems.append(f"{o.region}: {a.item} needs main building level {lvl}")
                continue
            cost = real_cost(w, snap.faction, a)
            need = dev_cost(a.level_key, w)
            if need and (have := development_points(w, o.region_obj, snap.faction)) is not None and have < need:
                problems.append(f"{o.region}: {a.item} needs {need} development points (the province has {have})")
                continue
            if cost > gold:
                if rank[0] <= SAVE_UP_TO and cost - gold <= SAVE_TURNS * net:
                    SAVING.update(turn=w.s.read().turn, gold=cost, item=f"{gd.place_name(o.region)}: {a.item}",
                                  rank=rank)
                problems.append(f"{o.region}: {a.item} needs {cost} gold")
                continue
            if idx is None or not a.level_key:
                _failed(problems, o, a, f"{o.region}: no slot for {a.item}")
                continue
            if a.kind not in ("construct", "replace") and damaged(w, S):   # (a replaced one goes anyway)
                problems.append(f"{o.region}: {a.item} waits for a repair")
                continue
            if not ui_open_province(ui, o):
                _failed(problems, o, a, f"{o.region}: could not open its province")
                continue
            slot = ui_slot(ui, w, o, idx)
            if slot is None:
                _failed(problems, o, a, f"{o.region}: slot not on screen")
                continue
            if a.kind == "replace":
                old = next((s.building for s in [o.slot_states[idx]] if s.building), None)
                old_name = gd.level_name(old) if old else "the building"
                how = ui_demolish(ui, w, o, idx, slot)
                if how is None:
                    _failed(problems, o, a, f"{o.region}: could not demolish {old_name}")
                    continue
                if how == "pending":                  # the slot is free next turn: the planned building goes up then
                    done.append(f"{gd.place_name(o.region)}: demolishing {old_name} (not on your list; "
                                f"{a.item} goes up there next turn)")
                    log(f"build: {done[-1]}")
                    continue
                done.append(f"{gd.place_name(o.region)}: demolished {old_name} (not on your list)")
                log(f"build: {done[-1]}")
                slot = ui_slot(ui, w, o, idx)
                chain = next((t.chain for t in plan_targets(o) if t.item == a.item), None)
                ok = slot is not None and chain is not None and ui_construct(ui, w, S, slot, a.level_key, chain,
                                                                             o.region)
                a = type(a)(a.settlement, "construct", a.item, f"-> {gd.level_name(a.level_key)}", a.slot, a.cost,
                            a.turns, a.level_key)
            elif a.kind == "construct":
                chain = next((t.chain for t in plan_targets(o) if t.item == a.item), None)
                ok = chain is not None and ui_construct(ui, w, S, slot, a.level_key, chain, o.region)
            else:
                ok = ui_upgrade(ui, w, S, slot, a.level_key)
            if ok:
                gold = min(w.s.read().treasury or gold, gold - cost)   # (the treasury can lag the slot in MP)
                done.append(f"{gd.place_name(o.region)}: {a.item} {a.detail}")
                log(f"build: {done[-1]}")
            else:
                _failed(problems, o, a, f"{o.region}: {a.item} not started"
                        + (f" ({REASON['last']})" if REASON["last"] else ""))
        move_to(*PARK)
    PROTECTED.clear()
    PROTECTED.update(protected)
    parts = []
    if done:
        parts.append("; ".join(done))
    if SAVING:
        parts.append(f"saving for {SAVING['item']} ({SAVING['gold']} gold, {gold} now, about "
                     f"{-(-(SAVING['gold'] - gold) // max(net, 1))} turn(s) of income)"
                     + (f"; {held} cheaper item(s) wait for it" if held else ""))
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
