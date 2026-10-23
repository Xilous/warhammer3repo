"""Skill automation: spend every unspent skill point on Ikit Claw, Verminlord Warpseers, Thanquol and Warlock
Engineers in the player's fixed order (strategy/skills.json), then "as fits" (passives first,
active-ability skills last). Every other lord (agent type "general") follows the generic_lord template: the
same army and campaign rows, found by skill key in its own tree (player request 2026-10-22). Other heroes are left
alone.

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
    python -X utf8 -m assist.skills plan [ikit_claw|warlock_engineer|verminlord_warpseer|thanquol|
                                          generic_lord:<agent subtype>, e.g. generic_lord:wh2_main_skv_warlord]
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


GENERIC = "generic_lord"      # the template for lords without their own (key "generic_lord:<agent subtype>")


@lru_cache(maxsize=1)
def _node_sets() -> dict[str, str]:
    """agent subtype -> its skill node set (character_skill_node_sets_tables; one per Skaven subtype on 9.0.4)."""
    out: dict[str, str] = {}
    for r in gd._load("character_skill_node_sets_tables"):
        out.setdefault(r["agent_subtype_key"], r["key"])
    return out


def character_orders(char_key: str) -> dict:
    """The orders for a template key: a characters entry as written, or generic_lord:<subtype> made into one
    (each skill key looked up in that subtype's node set, skills its tree lacks left out, mounts taken as they unlock)."""
    o = orders()
    if char_key in o["characters"]:
        return o["characters"][char_key]
    sub = char_key.split(":", 1)[1]
    g = o[GENERIC]
    node_set = _node_sets()[sub]
    nodes, _e, _m, set_items = _tables()
    by_skill = {nodes[n]["character_skill_key"]: n for n in set_items.get(node_set, []) if n in nodes}
    loc = gd.loc()
    by_name = {}                 # the same skill under another key (a schemer's Inspiring Presence: schemer_military_00)
    for sk, n in by_skill.items():
        nm = loc.get("character_skills_localised_name_" + sk, "")
        by_name.setdefault(gd._tr(nm) if nm else "", n)
    order = []
    for i in g["order"]:
        n = by_skill.get(i["skill_key"]) or by_name.get(i["skill"])
        if n:
            order.append({**i, "node": n})
    mounts = sorted((n for sk, n in by_skill.items() if "mount" in n or "mount" in sk),
                    key=lambda n: (_unlock_ranks().get((nodes[n]["character_skill_key"], 1), 0), n))
    # player decision 2026-10-23: a generic lord takes each mount as it unlocks (rank order); "skip" leaves them out
    take, skip = (mounts, []) if g.get("mounts", "take_as_unlocked") == "take_as_unlocked" else ([], mounts)
    never = [by_skill[k] for k in g.get("skip_skills", []) if k in by_skill]
    return {"agent_subtype": sub, "node_set": node_set, "order": order, "mounts": {"take": take, "skip": skip},
            "skip": never}


def attempt_list(char_key: str) -> list[tuple[str, int, str]]:
    """The player's order (mounts and "asap" skills first, they unlock by rank), then the rest of the tree:
    passive skills first, active-ability skills last."""
    c = character_orders(char_key)
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
    # "skip": nodes never taken, not even as leftovers (2026-10-22: the Warpseer's Soldiers of Renown, "not taken" in
    # the player's build, came first among the leftovers)
    skip = set(mounts.get("skip", [])) | set(mounts.get("take", [])) | listed | set(c.get("skip", []))
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
    from bot.sensor.world import World, armies, characters, find_player_faction
    w = World()
    F = find_player_faction(w)
    o = orders()
    by_subtype = {c["agent_subtype"]: k for k, c in o["characters"].items()}
    leading = {a.general_ptr for a in armies(w, F)} if GENERIC in o else set()
    out = []
    for c in characters(w, F):
        k = by_subtype.get(c.subtype)
        # a lord without a template of its own (agent type from memory), leading an army: the Masterplan Underlings
        # are "general" too but lead none and are not in the Lords & Heroes list (2026-10-22, turn 55: two of them
        # had 14 and 10 points); garrison commanders are "colonel"
        if not k and c.agent == "general" and c.ptr in leading and c.subtype in _node_sets():
            k = f"{GENERIC}:{c.subtype}"
        if not k:
            continue
        pts = w.u32(w.q(c.ptr + 0x3F0) + POINTS_OFF)
        if pts:
            out.append((c.ptr, k, w.u32(c.ptr + CHAR_ID_OFF), pts, c.name))
    return out, w


@lru_cache(maxsize=1)
def _unlock_ranks() -> dict[tuple[str, int], int]:
    """(skill key, level) -> unlocked_at_rank (character_skill_level_details_tables)."""
    out: dict[tuple[str, int], int] = {}
    for r in gd._load("character_skill_level_details_tables"):
        k, lv, at = r.get("skill_key"), r.get("level"), r.get("unlocked_at_rank") or 0
        if k and lv and ((k, int(lv)) not in out or at < out[(k, int(lv))]):
            out[(k, int(lv))] = int(at)
    return out


def _rank_locked(rank: int | None, sk: str, level: int = 1) -> bool:
    """The skill's `level` is not open at this rank yet. unlocked_at_rank counts from 0: a level opens at the rank
    above it (2026-10-22, live: Mentor, unlocked_at_rank 29, read locked on Thanquol at rank 29 and its tooltip said
    "Available at rank 30"; the same off-by-one was behind Thanquol's and the Warpseer's unique_0 reading open in
    memory and locked on the card at ranks 11 and 10)."""
    return rank is not None and _unlock_ranks().get((sk, level), 0) >= rank


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
    node_set = character_orders(char_key)["node_set"]
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
    for _ in range(2):          # a tab click the game did not take is a UI miss, clicked once more (2026-10-19,
        if not (ui.state(tab) or "").startswith("selected"):    # multiplayer: just after another player's battle
            click(ui, tab)                                      # the hover never showed and the list stayed shut)
        row = wait.wait_until(lambda: ui.first(f"character_row_{char_id}"), 2.0, f"character_row_{char_id} listed",
                              must=False)
        if row is not None or (ui.state(tab) or "").startswith("selected"):
            break
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


@lru_cache(maxsize=1)
def _links():
    """child node -> [(parent node, link type)] (character_skill_node_links_tables)."""
    out: dict[str, list] = {}
    for r in gd._load("character_skill_node_links_tables"):
        out.setdefault(r["child_key"], []).append((r["parent_key"], r["link_type"]))
    return out


@lru_cache(maxsize=1)
def _locks():
    """node -> [(skill key, level)]: taking that skill to that level locks the node (character_skill_nodes_skill_locks:
    Corruptive / Dictatorial, a Warlock Master's three unique skills, mounts)."""
    out: dict[str, list] = {}
    for r in gd._load("character_skill_nodes_skill_locks_tables"):
        out.setdefault(r["character_skill_node"], []).append((r["character_skill"], int(r.get("level") or 1)))
    return out


def memory_state(w, ptr: int, sk: str, ranks: int, node_set: str | None = None) -> str:
    """A skill's state from memory (player rule 2026-10-19: memory first): "taken" (at its planned rank: the
    character's skill list, army_builder.character_skills), "rank" (unlocks above the character's rank), "locked"
    (its node's REQUIRED parents not all taken, or fewer SUBSET_REQUIRED parents taken than required_num_parents),
    else "open". Taken and rank checked live; the node links are DB data and wait for their live check (_spend logs
    every disagreement with the card).
    The node is looked up in the character's own node set (2026-10-20: the first node anywhere with the skill key was
    taken, e.g. Triangulation from Jorek's tree, Warp-Smart from Tretch's, whose parents are never taken, so those
    skills read locked forever and the points went elsewhere). SUBSET_REQUIRED counts points: required_num_parents is
    the number of points spent in the parent skills (live: Rally! needs 6, taken with Blastmaster 3 + Engineering
    Skill 3)."""
    from .army_builder import character_skills
    taken = character_skills(w, ptr)
    if taken.get(sk, 0) >= ranks:
        return "taken"
    if _rank_locked(_rank(w, ptr), sk, taken.get(sk, 0) + 1):
        return "rank"
    nodes, _e, _m, set_items = _tables()
    pool = set_items.get(node_set, []) if node_set else nodes
    node = next((k for k in pool if k in nodes and nodes[k]["character_skill_key"] == sk), None)
    if node:
        links = _links().get(node, [])
        tk = lambda p: taken.get(nodes[p]["character_skill_key"], 0) if p in nodes else 0
        if any(tk(p) < 1 for p, t in links if t == "REQUIRED"):
            return "locked"
        sub = [p for p, t in links if t == "SUBSET_REQUIRED"]
        need = nodes[node].get("required_num_parents") or 0
        if sub and sum(tk(p) for p in sub) < max(1, need):
            return "locked"
        if any(taken.get(k, 0) >= lv for k, lv in _locks().get(node, [])):
            return "locked"                      # locked by a skill taken (2026-10-22)
    return "open"


def _log_check(**fields) -> None:
    import json, time
    try:
        with open(config.RUNS_DIR / "skills_check.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": round(time.time(), 1), **fields}) + "\n")
    except Exception:
        pass


def _spend(ui, w, ptr: int, plan, node_set: str | None = None) -> list[str]:
    tree = _Tree(ui)
    if tree.clip is None:
        return []
    out = []
    # After every skill taken the order is walked again from the top (2026-10-20: a skill unlocked by a point spent
    # earlier in the same pass was passed over, and the point went to a skill lower in the order)
    while _walk(ui, w, ptr, plan, node_set, tree, out):
        pass
    return out


def _walk(ui, w, ptr: int, plan, node_set, tree, out: list) -> bool:
    """One walk down the order; True as soon as a skill was taken (the caller walks again from the top)."""
    for sname, ranks, sk in plan:
        if _points(w, ptr) == 0:
            return False
        card = tree.card(sk)
        if card is None:
            continue
        mem = memory_state(w, ptr, sk, ranks, node_set)
        cs = (ui.state(card) or "").removesuffix("_hover")      # a card under the mouse: maxed_hover is maxed
        ui_locked = cs in SKIP_STATES or (ranks == 1 and tree.maxed_tick(card))
        if (mem != "open") != ui_locked and ui.state(card) is not None:   # the data for the switch to memory only:
            _log_check(skill=sk, memory=mem, card=ui.state(card), points=_points(w, ptr))   # see memory_state
        if mem != "open" or ui_locked:
            if ui_locked:
                LOCKED_UI.setdefault((ptr, _turn(w)), set()).add(sk)
            continue
        if (ptr, sk, _turn(w)) in NOT_TAKEN:
            continue
        if _rank_locked(_rank(w, ptr), sk):
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
                if (ui.state(card) or "").removesuffix("_hover") in SKIP_STATES:   # (the mouse is on it now)
                    break
        if n:
            out.append(f"{sname} x{n}")
            return True
    return False


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
                spent_here = _spend(ui, w, ptr, plans[key], character_orders(key)["node_set"])
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
                 if taken.get(sk, 0) < ranks and not _rank_locked(rank, sk, taken.get(sk, 0) + 1)]
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
