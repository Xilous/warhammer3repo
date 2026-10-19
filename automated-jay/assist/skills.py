"""Skill automation: spend every unspent skill point on Ikit Claw, Verminlord Warpseers and Warlock
Engineers in the player's fixed order (strategy/skills.json), then "as fits" (passives first,
active-ability skills last). Other characters are left alone.

Everything is read from memory and the game's UI tree (verified 2026-10-16, 9.0.4); nothing is searched for on
screen, and every wait is a condition (tools/wait.py):

  points     unspent skill points: u32 at [character + 0x3F0] + 0x240. A click counts when they go down.
  open       Lords & Heroes list (hud_campaign/bar_small_top/TabGroup/tab_units, state "selected" while shown):
             row character_row_<character id> (id = u32 at character + 0x110) -> its rank badge skill_button
             opens character_details_panel on that character's skills (character_details_panel_skills).
  switch     the open panel lists the characters of the Lords & Heroes list along the top
             (char_select_list/.../CcoCampaignCharacter<id>/button_character_holder, state "selected" for the one
             shown). Clicking one shows that character without closing the panel.
  tree       the game builds a NEW skill tree (new components) for every character it shows, 130-210 ms after the
             switch; until then the previous character's tree is on screen. The step waits until the tree rows
             (list_box/chainN/chain) are new components, then reads the tree once.
  node       a component whose id is the character_skill_key; its child "card" has the node's state: "available"
             (a click spends a point), "maxed", "locked", "locked_rank" (a click changes nothing: skipped without
             a click). Any other state is clicked and judged by the points, as before.
  scroll     the tree is wider than its list_clip; the scrollbar thumb is hslider/handle. A node outside the clip
             reads visible at its off-screen position: it is scrolled into view (thumb dragged to that end).
  close      character_details_panel/.../button_ok.

    python -X utf8 -m assist.skills run
    python -X utf8 -m assist.skills plan [ikit_claw|warlock_engineer|verminlord_warpseer]
"""
from __future__ import annotations

from bot import config
import json
import sys
from functools import lru_cache
from pathlib import Path

from . import gamedata as gd
from bot.focus import game_focus
from tools import wait
from tools.ui import click, drag, move_to, wheel

HERE = Path(__file__).resolve().parent
STRATEGY = config.STRATEGY_DIR / "skills.json"

POINTS_OFF = 0x240        # unspent skill points: u32 at [character + 0x3F0] + 0x240 (verified 9.0.4)
CHAR_ID_OFF = 0x110       # character id: u32 at character + 0x110 (character_row_<id>, CcoCampaignCharacter<id>)
DETAILS = "character_details_panel"
SKILLS_PANEL = "character_details_panel_skills"
SKIP_STATES = frozenset({"maxed", "locked", "locked_rank"})   # card states a click does not change (2026-10-16)
TREE_TIMEOUT_S = 1.5      # the new character's tree is normally built 130-210 ms after the switch
NOT_TAKEN: set = set()    # (character, skill, turn) a click did not take: not clicked again that turn
LOCKED_UI: dict = {}      # (character, turn) -> skills whose card read locked/maxed (UI stop-gap: the skill tree's
                          # prerequisite locks are not read from memory yet; ranks and rank locks are)


# ------------------------------------------------------------------ orders

def orders() -> dict:
    return json.load(open(STRATEGY, encoding="utf-8"))


@lru_cache(maxsize=None)
def _tables():
    """The skill tables (about 19 MB of JSON): read once per process, they only change with a game patch."""
    nodes = {r["key"]: r for r in gd._load("character_skill_nodes_tables")}
    effects: dict[str, list[str]] = {}
    maxlvl: dict[str, int] = {}
    for r in gd._load("character_skill_level_to_effects_junctions_tables"):
        effects.setdefault(r["character_skill_key"], []).append(r["effect_key"])
        maxlvl[r["character_skill_key"]] = max(maxlvl.get(r["character_skill_key"], 0), int(r["level"]))
    set_items: dict[str, list[str]] = {}
    for r in gd._load("character_skill_node_set_items_tables"):
        set_items.setdefault(r["set"], []).append(r["item"])
    return nodes, effects, maxlvl, set_items


def attempt_list(char_key: str) -> list[tuple[str, int, str]]:
    """The player's order (mounts and "asap" skills first, they unlock by rank), then the rest of the tree:
    passive skills first, active-ability skills last."""
    o = orders()
    c = o["characters"][char_key]
    nodes, effects, maxlvl, set_items = _tables()
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
    for item in sorted(c["order"], key=lambda i: not i.get("asap")):   # stable: the order is kept within each group
        out.append((item["skill"], item["ranks"], nodes[item["node"]]["character_skill_key"]))
        listed.add(item["node"])
    skip = set(mounts.get("skip", [])) | set(mounts.get("take", [])) | listed
    rest = []
    for n in set_items.get(c["node_set"], []):
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


# ------------------------------------------------------------------ memory

def _skill_targets():
    """[(character ptr, char_key, character id, points, name)] for characters the orders cover that have points."""
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


@lru_cache(maxsize=1)
def _unlock_ranks() -> dict[str, int]:
    """skill key -> the rank its first level unlocks at (character_skill_level_details_tables)."""
    out: dict[str, int] = {}
    for r in gd._load("character_skill_level_details_tables"):
        k, lv, at = r.get("skill_key"), r.get("level"), r.get("unlocked_at_rank") or 0
        if k and lv == 1 and (k not in out or at < out[k]):
            out[k] = int(at)
    return out


def _rank(w, ptr: int) -> int | None:
    """The character's rank from memory: [C+0x3F0]+0x244 plus one (decompiled character:rank(), FUN_142466F8C)."""
    try:
        return w.u32(w.q(ptr + 0x3F0) + 0x244) + 1
    except Exception:
        return None


def _turn(w) -> int | None:
    try:
        return w.s.read().turn
    except Exception:
        return None


def _points(w, ptr) -> int:
    return w.u32(w.q(ptr + 0x3F0) + POINTS_OFF)


# ------------------------------------------------------------------ the panel (UI tree)

_last_sig: tuple = ()      # the tree rows seen last: a reopened panel can show some of them for a moment


def _tree_sig(ui) -> tuple:
    """Pointers of the skill tree's rows (character_details_panel_skills/listview/list_clip/list_box/chainN/chain).
    The game builds new ones for every character it shows; () while the panel is not shown."""
    if not ui.root_child(DETAILS):                # (a lookup under a panel that is not open walks the whole tree)
        return ()
    sk = ui.cached(SKILLS_PANEL, under=DETAILS)
    lb = ui.cached("list_box", under=sk) if sk else None
    if lb is None:
        return ()
    return tuple(ch for row in ui.children(lb) for ch in ui.children(row))


def _selected(ui, char_id: int) -> bool:
    """The open panel shows this character (its entry along the top is "selected")."""
    e = ui.cached(f"CcoCampaignCharacter{char_id}", under=DETAILS) if ui.root_child(DETAILS) else None
    h = ui.child(e, "button_character_holder") if e else None
    return h is not None and (ui.state(h) or "").startswith("selected")


def tree_rows(char_key: str) -> int:
    """Rows of this character type's skill tree: one per indent level of its visible nodes (ikit 6, warlock 4,
    verminlord 6 on 9.0.4, matching the panel)."""
    nodes, _e, _m, set_items = _tables()
    node_set = orders()["characters"][char_key]["node_set"]
    return len({int(nodes[n]["indent"]) for n in set_items.get(node_set, [])
                if n in nodes and nodes[n]["visible_in_ui"] is not False})


def _await_tree(ui, char_id: int, before: tuple, rows: int) -> bool:
    """Until the panel shows this character and its tree has all `rows` rows, every one a new component (none of
    `before`, the rows seen last), plus one frame. Measured 2026-10-16: the game adds the new rows one
    by one (or all at once) 15-140 ms after the switch; a panel reopened right after closing first shows a few rows
    of the previous character's tree. When the game does not rebuild (it already showed this character), the
    timeout lets it through."""
    old = set(before)

    def built():
        if not _selected(ui, char_id):
            return None
        s = _tree_sig(ui)
        return s if len(s) >= rows and not old.intersection(s) else None
    got = wait.wait_until(built, TREE_TIMEOUT_S, f"skill tree built for character {char_id}", must=False)
    if got is None:
        return _selected(ui, char_id) and bool(_tree_sig(ui))
    wait.next_frame(1, ui)                       # the frame that added the last row has finished laying it out
    return True


def _lords_row(ui, char_id: int):
    """The character's row in the Lords & Heroes list, opening the list and scrolling the row into view."""
    tab = ui.cached("tab_units", under="bar_small_top")
    if tab is None:
        return None
    if not (ui.state(tab) or "").startswith("selected"):
        click(ui, tab)
    row = wait.wait_until(lambda: ui.first(f"character_row_{char_id}"), 2.0, f"character_row_{char_id} listed",
                          must=False)
    if row is None:
        return None
    clip = ui.clip_of(row)
    for _ in range(30):
        if clip is None or ui.in_clip(row):
            return row
        cl, k = ui.comp(clip), ui.comp(row)
        wheel(*cl.center, 1 if k.y < cl.y else -1)
        wait.stable(lambda: ui.comp(row).y, n=2, timeout=1.0, what="Lords & Heroes list still", ui=ui, must=False)
    return None


def _show(ui, char_id: int, rows: int) -> bool:
    """Show this character's skills: switch the open panel to it, or open the panel from the Lords & Heroes list."""
    if ui.root_child(DETAILS):
        if _selected(ui, char_id):
            return True
        e = ui.first(f"CcoCampaignCharacter{char_id}", under=DETAILS)
        h = ui.child(e, "button_character_holder") if e else None
        if h is not None and ui.in_clip(h):
            before = _tree_sig(ui)
            click(ui, h)
            return _await_tree(ui, char_id, before, rows)
        _close(ui)                               # not in the panel's list: go through the Lords & Heroes list
    row = _lords_row(ui, char_id)
    badge = ui.first("skill_button", under=row) if row else None
    if badge is None:
        return False
    before = _tree_sig(ui) or _last_sig
    click(ui, badge)
    if wait.wait_until(lambda: ui.root_child(DETAILS) and ui.first(SKILLS_PANEL, under=DETAILS), 3.0,
                       f"{SKILLS_PANEL} shown", must=False) is None:
        return False
    return _await_tree(ui, char_id, before, rows)


def _close(ui) -> None:
    global _last_sig
    _last_sig = _tree_sig(ui) or _last_sig
    ok = ui.first("button_ok", under=DETAILS) if ui.root_child(DETAILS) else None
    if ok is None:
        return
    click(ui, ok)
    wait.gone(ui, DETAILS, timeout=2.0)


class _Tree:
    """The shown character's skill tree, read once: {skill key: node}, the clip window and the scrollbar thumb."""

    def __init__(self, ui) -> None:
        global _last_sig
        self.ui = ui
        _last_sig = _tree_sig(ui)
        self.panel = ui.cached(SKILLS_PANEL, under=DETAILS)
        self.index = ui.index(self.panel) if self.panel else {}
        clips = self.index.get("list_clip", [])
        self.clip = clips[0] if clips else None
        hs = self.index.get("hslider", [])
        self.handle = ui.child(hs[0], "handle") if hs else None

    def card(self, sk: str) -> int | None:
        node = (self.index.get(sk) or [None])[0]
        if node is None:
            return None
        return self.ui.child(node, "card") or node

    def maxed_tick(self, card: int) -> bool:
        """The tick shows once any rank is taken, so it only proves "maxed" for one-rank skills."""
        chk = self.ui.child(card, "icon_check")
        return chk is not None and self.ui.visible(chk)

    def inside(self, card: int) -> bool:
        k, cl = self.ui.comp(card), self.ui.comp(self.clip)
        return cl.x + 4 <= k.x and k.x + k.w <= cl.x + cl.w - 4

    def scroll_to(self, card: int) -> bool:
        """Drag the thumb to the end the card lies towards, until the card is inside the clip and still."""
        if self.handle is None:
            return False
        ui = self.ui
        k, cl, h = ui.comp(card), ui.comp(self.clip), ui.comp(self.handle)
        hx, hy = h.center
        drag(hx, hy, 5 if k.x < cl.x else 1915, hy, target=self.handle)
        wait.stable_rect(ui, card, n=2, timeout=1.0, what=f"{ui.id(ui.parent(card))} still after the scroll",
                         must=False)
        return self.inside(card)


def _spend(ui, w, ptr: int, plan) -> list[str]:
    tree = _Tree(ui)
    if tree.clip is None:
        return []
    out = []
    for sname, ranks, sk in plan:
        if _points(w, ptr) == 0:
            break
        card = tree.card(sk)
        if card is None:
            continue
        if (ui.state(card) or "") in SKIP_STATES or (ranks == 1 and tree.maxed_tick(card)):
            LOCKED_UI.setdefault((ptr, _turn(w)), set()).add(sk)
            continue
        if (ptr, sk, _turn(w)) in NOT_TAKEN:
            continue
        rank = _rank(w, ptr)
        if rank is not None and _unlock_ranks().get(sk, 0) > rank:
            continue                             # not unlocked at this rank yet (a mount at rank 15): no click
                                                 # (2026-10-18: 2.5 s lost on it every multiplayer turn)
        if not tree.inside(card) and not tree.scroll_to(card):
            continue
        n = 0
        for _ in range(ranks):
            before = _points(w, ptr)
            if before == 0:
                break
            def press():
                click(ui, card)
                # off the card at once: resting on it brings up its tooltip, which covers the next card to the right
                # and takes that click (2026-10-18, multiplayer: three skills lost behind a tooltip, 2.5 s each)
                try:
                    k = ui.comp(tree.clip)
                    move_to(int(k.x + k.w / 2), max(5, int(k.y) - 18))
                except Exception:
                    move_to(960, 160)
            # paced by the game (bot/sensor/commands.py): clicked again only when no command reached the game; the
            # point is taken when memory says so, however long the sync takes
            from bot.sensor import commands
            # no retry: click() presses only once the game shows the cursor over this card, so no command means
            # the game refused the skill (2026-10-19: the Boneripper mount at rank 15 wrote none; a retry with its
            # 2.5 s grace cost 6 s every turn)
            st, _v = commands.act(w.pm, press, lambda: _points(w, ptr) < before)
            if st != "done":
                NOT_TAKEN.add((ptr, sk, _turn(w)))   # not again this turn (2026-10-18: a locked mount skill was
                break                                # clicked and waited on in every pass)
            n += 1
            if n < ranks:                        # the card shows "maxed" a frame later: no click on a full skill
                wait.next_frame(1, ui)
                if (ui.state(card) or "") in SKIP_STATES:
                    break
        if n:
            out.append(f"{sname} x{n}")
    return out


# ------------------------------------------------------------------ the automation step

def run(log=print) -> str:
    targets, w = _skill_targets()
    if not targets:
        return "no unspent points"
    from bot.sensor.ui import UI
    ui = UI(w.s)
    if ui.find_root() is None:
        return "game UI not found in memory; nothing clicked"
    plans = {key: attempt_list(key) for key in {t[1] for t in targets}}      # all reading before any input
    rows = {key: tree_rows(key) for key in plans}
    done = []
    with game_focus():
        try:
            for ptr, key, char_id, pts, name in targets:
                if not _show(ui, char_id, rows[key]):
                    done.append(f"{name}: could not open skills")
                    continue
                spent_here = _spend(ui, w, ptr, plans[key])
                if spent_here:
                    done.append(f"{name}: " + ", ".join(spent_here))
                    log(f"skills: {name}: {', '.join(spent_here)}")
        finally:
            if ui.root_child(DETAILS):
                _close(ui)
    return "; ".join(done) if done else "no points could be spent"


def missed() -> list[str]:
    """The memory check after the step (player request 2026-10-19). A character the orders cover that still has
    points after the step must have none of its planned skills left takeable in memory: every one taken to its
    planned rank ([C+0x3F0]+0x200, army_builder.character_skills), or above the character's rank. A planned skill the
    game refused (a click that wrote no command or took no point: NOT_TAKEN; a card read locked: LOCKED_UI) is
    reported as refused; anything else is missed."""
    from .army_builder import character_skills
    targets, w = _skill_targets()
    turn, out = _turn(w), []
    for ptr, key, _cid, pts, name in targets:
        taken, rank = character_skills(w, ptr), _rank(w, ptr)
        open_ = [(sname, sk) for sname, ranks, sk in attempt_list(key)
                 if taken.get(sk, 0) < ranks and not (rank is not None and _unlock_ranks().get(sk, 0) > rank)]
        refused = [s for s, sk in open_ if (ptr, sk, turn) in NOT_TAKEN or sk in LOCKED_UI.get((ptr, turn), ())]
        left = [s for s, _sk in open_ if s not in refused]
        if left:
            out.append(f"{name}: {pts} skill point{'s' if pts > 1 else ''} unspent, {left[0]} can still be taken")
        elif refused:
            out.append(f"{name}: {pts} skill point{'s' if pts > 1 else ''} unspent (refused by the game: "
                       f"{', '.join(refused[:3])})")
    return out


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if cmd == "run":
        from bot.focus import return_to_terminal
        try:
            print(run())
        finally:
            return_to_terminal()
    elif cmd == "plan":
        who = sys.argv[2] if len(sys.argv) > 2 else "ikit_claw"
        for i, (n, r, sk) in enumerate(attempt_list(who), 1):
            print(f"{i:2d}. {n} x{r}  [{sk}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
