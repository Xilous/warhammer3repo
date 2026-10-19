"""Army builder: refill each ticked army to the template, and raise new armies (assist/new_army.py).

A tick means "refill once" (player rule 2026-10-18): only an army missing template units can be ticked, and only
while the refill is possible (refill_check: a province recruits the whole template, an engineer is free or the
engineer cap has room); it is cleared once the army matches again (untick_refilled). A new army is raised first in a
pass and ticked, so it is recruited in the same pass.

A tick counts only while the army's general is the one that was ticked (assist/army.py tick_for: cqis repeat
between campaigns). Per ticked army, in order:
  1. heroes are never disbanded automatically (they can be legendary, and a disband cannot be undone): an embedded
     hero the template does not want is reported ("extra hero <name> in <army>: remove it yourself"). The lord is
     never touched;
  2. disband every troop that is not in the template, but ONLY once the army stands in a province that can
     recruit its missing units locally (player rule: a stripped lord on the march gets attacked). Before anything
     is pressed, each card to disband is matched to an off-template unit in memory by the unit name in its
     tooltip, and the selection is checked card by card (card state "selected..."); afterwards memory must show
     exactly those units gone;
  3. if the army stands in an owned region of a province whose finished buildings recruit a missing unit LOCALLY,
     queue the missing units from the local pool only, never the global pool (global recruitment costs far more);
  4. otherwise order the army to the CLOSEST eligible province, re-evaluated every turn (a province that becomes
     eligible mid-march wins if it is closer). Closest = fewest region hops over the game's land adjacency graph,
     then straight-line distance. A settlement held by another of our armies is never a target. The army marches
     only to recruit units, never for a hero;
  5. Warlock Engineer (never a reason to move the army or to pick a province): a free engineer counts as the
     army's engineer. Claims (runs/engineer_claims.json) keep an engineer walking to one army from being taken by
     another ticked army, and stop a second one being recruited while the first is on the way. When the army has
     none, one is recruited as soon as the faction cap allows, wherever the army is, at the owned settlement
     nearest the army whose province can recruit one (a Construction Cavern / Bog Mine province, or the province
     a Verminlord Warpseer with Inscrutable Genius stands in). The settlement's Recruit Hero panel has the final
     say (engineer tab inactive = not here; Recruit button inactive = cap full, nothing recruited, retried every
     turn). The engineer is sent to the army every turn until it joins (the army may have moved). A hero
     recruited this turn cannot move yet, and a 20/20 army cannot take it.

Units already queued count as present (both template units take 2 turns to recruit).

UI ids used (9.0.4): character_row_<id> (Lords & Heroes), main_units_panel / "LandUnit n" / "AgentUnit n" (unit
cards; state name "selected..." while selected; tooltip string {u32 length +0x238, wchar* +0x240} that starts with
the unit's on-screen name), button_disband, dialogue_box/button_tick, button_recruitment, recruitment_docker /
local1 / "<unit key>_recruitable", label_settlement:<region>, button_agents, agent_parent/list_box/engineer,
general_candidate_0_, button_confirm.
"""
from __future__ import annotations
import json
import math
import re
import struct
from collections import Counter, deque

from bot import config
from bot.focus import game_focus
from bot.sensor.camera import character_pos
from bot.sensor.ui import UI
from bot.sensor.world import World, armies, characters, find_player_faction, region_provinces, string_object
from tools import wait
from tools.ui import click, held, move_to as move_cursor, press, wheel
from . import gamedata as gd
from .army import delta, enabled_armies, load_automation, set_enabled, tick_for, unit_name
from .heroes import (bring_into_view, hero_movement, in_safe, jump_row, lords_row, map_label, move_into_army, park,
                     province_row, row_selected, wait_until_stopped)

ENGINEER = "wh2_main_skv_warlock_engineer"
CLAIMS = config.RUNS_DIR / "engineer_claims.json"     # engineer character id -> army cqi it walks to
CAPS = config.RUNS_DIR / "caps.json"                  # faction -> caps the game shows only in its panels
FULL = 20                                             # units per army, lord and heroes included


def region_name(k: str) -> str:
    return gd.loc().get("regions_onscreen_" + k, k)


# ------------------------------------------------------------------ small UI helpers

def first(ui: UI, cid: str, under: str | None = None):
    """First visible component with this id (optionally below a component with id `under`): UI.first."""
    return ui.first(cid, under=under)


BUSY = ("main_units_panel", "recruitment_docker", "settlement_panel", "character_panel")
NOTCH_PX = 82                       # one wheel notch scrolls a recruitment pool by about this much


def _busy(ui: UI) -> tuple[str, ...]:
    """Which of the panels Escape would close are open (one walk of the visible tree)."""
    return tuple(sorted({i for _c, i, _r in ui.nodes(skip=("3d_ui_parent",)) if i in BUSY}))


def _resume(ui: UI) -> bool:
    """Close the game menu with Resume Game, once the button has stopped moving (2026-10-17: a click while the menu
    was still sliding in opened its info page instead, and End Turn then failed twice). Checked; up to 3 tries."""
    for _ in range(3):
        menu = ui.root_child("esc_menu")
        if not menu:
            return True
        b = ui.first("button_resume", under=menu)
        if not b:
            return False
        wait.stable_rect(ui, b, n=3, timeout=1.0, must=False, what="Resume Game still")
        click(ui, b)
        if wait.gone(ui, "esc_menu", timeout=1.5, must=False, what="game menu closed"):
            return True
    return not ui.root_child("esc_menu")


def clear(ui: UI) -> None:
    """Close the escape menu if open; otherwise press Escape once, only when a panel or selection is open (Escape
    with nothing selected opens the game menu), and wait until it took effect."""
    if ui.root_child("esc_menu"):
        _resume(ui)
        return
    busy = _busy(ui)
    if not busy:
        return
    press("esc")
    wait.wait_until(lambda: ui.root_child("esc_menu") or _busy(ui) != busy, 1.0, "Escape took effect", must=False)
    if ui.root_child("esc_menu"):
        _resume(ui)


def _lord_card(ui: UI):
    mup = ui.first("main_units_panel")
    return ui.first("LandUnit 0", under=mup) if mup else None


def _shows_army(ui: UI, army) -> bool:
    """The units panel shows this army: its lord's card (LandUnit 0) is named after the general."""
    c = _lord_card(ui)
    return c is not None and (card_unit_name(ui, c).splitlines() or [""])[0].strip() == army.general_name


def select_army(ui: UI, army) -> bool:
    """Select the army with a single click on its general's Lords & Heroes row (the camera does not move). True
    once the units panel shows this army. Already shown: no input."""
    if _shows_army(ui, army) and not set(_busy(ui)) - {"main_units_panel"}:
        return True
    clear(ui)
    row = lords_row(ui, army.general_id)
    if row is None:
        return False
    click(ui, row)
    if wait.wait_until(lambda: _shows_army(ui, army), 2.0, f"{army.general_name}'s army shown", must=False):
        return True
    return first(ui, "units", under="main_units_panel") is not None and row_selected(ui, row)


def unit_cards(ui: UI) -> tuple[list, list]:
    """(troop cards in display order excluding the lord, hero cards) from the selected army's panel."""
    troops, heroes = [], []
    mup = ui.first("main_units_panel")
    for c, n, _r in (ui.nodes(mup) if mup else ()):
        if n.startswith("LandUnit ") and n != "LandUnit 0":
            troops.append((int(n.split()[1]), c))
        elif n.startswith("AgentUnit "):
            heroes.append((int(n.split()[1]), c))
    troops.sort()
    heroes.sort()
    return [c for _, c in troops], [c for _, c in heroes]


def card_text(ui: UI, card: int) -> str:
    """A unit card's tooltip: "<unit name>||Left-click to select..." ("<name>\\n<type>||..." for characters).
    String object at card +0x238: u32 length (characters), u32 capacity, wchar* text at +0x240."""
    try:
        n = int.from_bytes(ui.pm.read_bytes(card + 0x238, 4), "little")
        p = ui.q(card + 0x240)
        if not p or not 0 < n < 1024:
            return ""
        return ui.pm.read_bytes(p, 2 * n).decode("utf-16-le", "replace")
    except Exception:
        return ""


def card_unit_name(ui: UI, card: int) -> str:
    return card_text(ui, card).split("||")[0].strip()


def card_selected(ui: UI, card: int) -> bool:
    """The card's state name ("selected", "selected_hover", ...) is the selection the game acts on, Shift-range
    members included. The byte at card +0x1B8 is not: it stays 2 on a card a later Shift-click dropped."""
    return (ui.state(card) or "").startswith("selected")


def confirm_dialog(ui: UI) -> bool:
    t = wait.wait_until(lambda: first(ui, "button_tick", under="dialogue_box")
                        or first(ui, "button_tick", under="popup_message_box"), 2.0, "confirmation box", must=False)
    if t is None:
        return False
    click(ui, t)
    wait.gone(ui, t, timeout=2.0, must=False, what="confirmation box closed")
    return True


def press_disband(ui: UI, over_card: int) -> bool:
    k = ui.comp(over_card)
    move_cursor(k.center[0], int(k.y) + 10)         # the unit button group appears above the card
    b = wait.appears(ui, "button_disband", timeout=1.5, must=False)
    if b is None:
        return False
    click(ui, b.ptr)
    return confirm_dialog(ui)


# ------------------------------------------------------------------ 1/2. heroes and disband

def extra_heroes(w: World, F: int, army) -> list:
    """Characters embedded in the army beyond the template's heroes (the lord is not one of them)."""
    want = load_automation()["army_builder"]["template"]["heroes"]
    kept, out = Counter(), []
    for c in characters(w, F):
        if c.embedded_force != army.force_ptr or c.ptr == army.general_ptr:
            continue
        if c.subtype in want and kept[c.subtype] < want[c.subtype]:
            kept[c.subtype] += 1
        else:
            out.append(c)
    return out


def disband(ui: UI, w: World, F: int, army, log) -> list[str]:
    """Disband the troops that are not in the template. Never a hero, never the lord: only troop cards
    (LandUnit 1..n) are ever selected, and the selection must be exactly the off-template units in memory."""
    d = delta(army, [])
    if not d.disband:
        return []
    want = Counter(load_automation()["army_builder"]["template"]["units"])
    troop_keys = [u.key for u in army.units if "_cha_" not in u.key]
    expect = Counter(d.disband)                                   # off-template units, from memory
    keys_named: dict[str, set[str]] = {}
    for k in set(troop_keys):
        keys_named.setdefault(unit_name(k), set()).add(k)
    if any(len(ks) > 1 for ks in keys_named.values()):
        return ["disband skipped: two different units in this army share a name, so their cards cannot be told apart"]
    key_of = {n: next(iter(ks)) for n, ks in keys_named.items()}
    want_names = Counter(unit_name(k) for k in troop_keys)

    def cards():
        t, h = unit_cards(ui)
        n = [card_unit_name(ui, c) for c in t]
        return (t, h, n) if len(t) == len(troop_keys) and Counter(n) == want_names else None
    got = wait.wait_until(cards, 1.0, "unit cards match the army in memory", must=False)
    if got is None:
        return ["disband skipped: the unit cards do not match the army in memory"]
    troops, hero_cards, names = got
    keep, targets = Counter(), []
    for i, n in enumerate(names):
        k = key_of[n]
        if keep[k] < want.get(k, 0):
            keep[k] += 1
        else:
            targets.append(i)
    if Counter(key_of[names[i]] for i in targets) != expect:
        return ["disband skipped: the cards to disband are not the off-template units in memory"]
    pick = [troops[i] for i in targets]
    contiguous = targets == list(range(targets[0], targets[-1] + 1))
    selection = lambda: [i for i, c in enumerate(troops) if card_selected(ui, c)]
    click(ui, pick[0])
    wait.wait_until(lambda: card_selected(ui, pick[0]), 0.5, "first card to disband selected", must=False)
    if len(pick) > 1:
        with held("shift" if contiguous else "ctrl"):
            for c in ([pick[-1]] if contiguous else pick[1:]):
                click(ui, c)
                wait.wait_until(lambda c=c: card_selected(ui, c), 0.5, "card to disband selected", must=False)
    wait.wait_until(lambda: selection() == targets, 0.5, "selection = the cards to disband", must=False)
    sel = selection()
    lord = first(ui, "LandUnit 0", under="main_units_panel")
    others = [c for c in hero_cards + ([lord] if lord else []) if card_selected(ui, c)]
    sel_keys = Counter(key_of.get(card_unit_name(ui, troops[i]), "?") for i in sel)
    if sel != targets or others or sel_keys != expect:
        park()
        return [f"disband skipped: the selection did not match (selected troop cards {sel}, wanted {targets}"
                + (", a lord or hero card was selected" if others else "") + ")"]
    before = Counter(u.key for u in army.units)
    count = lambda: w.u32(army.force_ptr + 0x6C8 + 0xC)            # this force's unit count (bot/sensor/world.py)
    n_before = count()
    if not press_disband(ui, pick[-1]):
        park()
        return ["disband skipped: the disband button or its confirmation did not appear"]
    from bot.sensor.commands import EFFECT_CAP_S   # the game's pace: ends the moment memory shows them gone
    wait.wait_until(lambda: count() <= n_before - len(pick), EFFECT_CAP_S, "disbanded units gone in memory",
                    must=False)
    a2 = next((a for a in armies(w, F) if a.cqi == army.cqi), None)
    after = Counter(u.key for u in a2.units) if a2 else Counter()
    gone, added = before - after, after - before
    park()
    if gone == expect and not added:
        return ["disbanded " + ", ".join(f"{n} {unit_name(k)}" for k, n in gone.items()) + " (checked in memory)"]
    return [f"WARNING: meant to disband {dict(expect)}, memory shows gone {dict(gone)}"
            + (f", added {dict(added)}" if added else "")]


# ------------------------------------------------------------------ recruitment awareness

def eligible(w: World, F: int, need: set[str]) -> dict[str, set[str]]:
    """province -> the needed units it can recruit locally right now, for provinces that are FULLY eligible: they can
    recruit every unit type of the army template (player rule 2026-10-17: a province that can only make some of
    them, e.g. Stormvermin but no Stormfiends yet, is no recruiting province; with none, a ticked army stays put)."""
    from .recruit import sources
    template = set(load_automation()["army_builder"]["template"]["units"])
    can: dict[str, set[str]] = {}
    for unit, where in sources(w).items():
        for p, _r, _b in where:
            can.setdefault(p, set()).add(unit)
    return {p: units & need for p, units in can.items() if template <= units}


def settlement_pos(w: World, F: int) -> dict[str, tuple[float, float]]:
    """Owned region -> map position (its garrison commander stands in the settlement)."""
    out = {}
    for a in armies(w, F, include_garrisons=True):
        if a.garrison and a.general_ptr and a.region:
            out[a.region] = character_pos(w.pm, a.general_ptr)
    return out


def held_settlements(w: World, F: int, pos: dict, except_cqi: int) -> set[str]:
    """Owned settlements another of our field armies stands in (moving there would stack the armies)."""
    spots = [character_pos(w.pm, a.general_ptr) for a in armies(w, F) if a.cqi != except_cqi and a.general_ptr]
    return {k for k, (sx, sy) in pos.items() if any(math.hypot(x - sx, y - sy) < 1.5 for x, y in spots)}


def hops_from(w: World, start: int, limit: int = 25) -> list[tuple[int, int]]:
    """(region object, hops) over the land adjacency graph, breadth first from start."""
    seen = {start: 0}
    dq = deque([start])
    out = []
    while dq:
        r = dq.popleft()
        out.append((r, seen[r]))
        if seen[r] >= limit:
            continue
        for n in w.neighbours(r):
            if n not in seen:
                seen[n] = seen[r] + 1
                dq.append(n)
    return out


def closest_target(w: World, F: int, army, elig: dict[str, set[str]]):
    """(region, province, hops) of the owned settlement nearest the army in a province that can recruit missing
    units: fewest region hops, then straight-line distance (player rule); a province covering more of the missing
    units only breaks an exact tie. Settlements held by another of our armies are skipped."""
    prov, _ = region_provinces()
    own = {w.region_key(r) for r in w.faction_regions(F)}
    pos = settlement_pos(w, F)
    taken = held_settlements(w, F, pos, army.cqi)
    if not army.region_obj:
        return None
    ax, ay = character_pos(w.pm, army.general_ptr)
    found = []
    for r, hops in hops_from(w, army.region_obj):
        k = w.region_key(r)
        p = prov.get(k)
        if k in own and p in elig and k in pos and k not in taken:
            sx, sy = pos[k]
            found.append((hops, math.hypot(sx - ax, sy - ay), -len(elig[p]), k, p))
    if not found:
        return None
    found.sort()
    hops, _, _, k, p = found[0]
    return k, p, hops


# ------------------------------------------------------------------ 3/4. recruit or move

def scroll_into_view(ui: UI, card: int) -> bool:
    """Recruitment pools are horizontal lists that scroll: a card past the clip window still reads as
    visible, but its centre can be off screen (a click there lands on the map). Wheel the list until the
    card sits inside its list_clip: the notches needed at about NOTCH_PX each, then until the cards are still."""
    clip = ui.clip_of(card)
    if clip is None:
        return False
    for _ in range(8):
        cc, cl = ui.comp(card), ui.comp(clip)
        if cl.x <= cc.x and cc.x + cc.w <= cl.x + cl.w:
            return True
        if cc.x > cl.x:
            n = -max(1, math.ceil((cc.x + cc.w - cl.x - cl.w) / NOTCH_PX))
        else:
            n = max(1, math.ceil((cl.x - cc.x) / NOTCH_PX))
        wheel(*cl.center, n)
        wait.stable(lambda: ui.comp(card).x, n=2, timeout=1.0, what="recruitment pool still after the scroll", ui=ui,
                    must=False)
    return False


def treasury(w: World, F: int) -> int:
    return struct.unpack("<i", w.pm.read_bytes(F + 0xD58, 4))[0]


def recruit_local(ui: UI, w: World, F: int, missing: dict[str, int], log) -> list[str]:
    btn = first(ui, "button_recruitment")
    if btn is None:
        return ["recruitment button not found"]
    click(ui, btn)
    pool = wait.appears(ui, "local1", under="recruitment_docker", timeout=2.0, must=False)
    if pool is not None:              # the pool's cards are added over a frame or two
        wait.stable(lambda: tuple(c for c, i, _r in ui.nodes(pool.ptr) if i.endswith("_recruitable")), n=2,
                    timeout=1.0, what="local recruitment pool listed", ui=ui, must=False)
    out = []
    for unit, n in missing.items():
        done = 0
        for _ in range(n):
            card = first(ui, f"{unit}_recruitable", under="local1")
            if card is None:
                break
            if not scroll_into_view(ui, card):
                out.append(f"could not scroll {unit_name(unit)} into view")
                break
            before = treasury(w, F)
            from bot.sensor import commands    # paced by the game: no command = the game refused the click (capacity
            st, _v = commands.act(w.pm, lambda: click(ui, card) and None,   # full, gold); a command = wait for the
                                  lambda: treasury(w, F) < before)          # gold, however long the sync takes
            if st != "done":
                break                          # not taken: local capacity full or not affordable
            done += 1
        if done:
            out.append(f"queued {done} {unit_name(unit)}")
        if done < n:
            out.append(f"{n - done} {unit_name(unit)} left for later turns")
    clear(ui)
    park()
    return out


def move_to(ui: UI, w: World, army, region: str) -> str:
    pos = settlement_pos(w, find_player_faction(w))
    if region not in pos:
        return f"no position for {region}"
    x, y = pos[region]
    label = f"label_settlement:{region}"
    lab, jumped = bring_into_view(w, ui, x, y, label, jump=lambda: jump_row(ui, province_row(ui, province_of(region))))
    if jumped:                       # the jump selected the settlement: select the army again (the camera stays put)
        select_army(ui, army)
        lab = map_label(ui, label)
    if lab is None or not in_safe(lab):
        return f"could not bring {region} on screen"
    p0 = character_pos(w.pm, army.general_ptr)
    click(ui, lab.ptr, right=True)
    wait.wait_until(lambda: character_pos(w.pm, army.general_ptr) != p0, 1.5, "army on the march", must=False)
    park()
    return "ordered to " + region_name(region)


# ------------------------------------------------------------------ 5. Warlock Engineer

INSCRUTABLE_GENIUS = "wh3_dlc29_skill_skv_verminlord_warpseer_unique_4"   # Warpseer skill: engineers recruitable
                                                                           # in the province he stands in, cap +2


def character_skills(w: World, C: int) -> dict[str, int]:
    """skill key -> rank taken, from memory (decompiled has_skill, 9.0.4): details D = [C+0x3F0]; D+0x200 is a
    list (count u32 +4, array +8) of {u32, u32 count +4, entries +8}; entry stride 0x30: [e] -> record whose
    [+8] is the skill key string object, rank byte e+0x10 (0 = not taken)."""
    out = {}
    try:
        S = w.q(C + 0x3F0) + 0x200
        n = w.u32(S + 4)
        arr = w.q(S + 8)
        for i in range(min(n, 64)):
            m, sub = w.u32(arr + 16 * i + 4), w.q(arr + 16 * i + 8)
            for j in range(min(m, 200)):
                e = sub + 0x30 * j
                rank = w.pm.read_bytes(e + 0x10, 1)[0]
                if rank:
                    rec = w.q(e)
                    key = string_object(w.pm, w.q(rec + 8) + 8) if rec else None
                    if key:
                        out[key] = rank
    except Exception:
        pass
    return out


def engineers_fielded(w: World, F: int) -> int:
    """Engineers counting toward the faction's cap, the way the game counts them (decompiled agent_cap_remaining):
    characters whose agent type is the engineer's and whose subtype record has byte +0x1CE set."""
    n = 0
    for c in characters(w, F):
        if c.agent == "engineer":
            try:
                if w.pm.read_bytes(w.q(w.q(c.ptr + 0x3F0) + 0x1F8) + 0x1CE, 1)[0]:
                    n += 1
            except Exception:
                n += 1
    return n


def on_screen_still(ui: UI, ptr: int, what: str, timeout: float = 2.0):
    """A component of a panel that slides in (the Recruit Hero panel comes up from below the screen): wait until it
    is fully on screen and its rectangle has been still for 3 frames. -> Comp or None."""
    W, H = config.RESOLUTION

    def on():
        k = ui.comp(ptr)
        return k.x >= 0 and k.y >= 0 and k.x + k.w <= W and k.y + k.h <= H
    if wait.wait_until(on, timeout, f"{what} on screen", must=False) is None:
        return None
    return wait.stable_rect(ui, ptr, n=3, timeout=timeout, must=False, what=f"{what} still")


def province_of(region: str) -> str | None:
    return region_provinces()[0].get(region)


def select_settlement(ui: UI, w: World, region: str, xy) -> bool:
    """Select our settlement `region`. A province capital: one click on its Provinces row selects it (the province
    panel opens on the capital) without moving the camera. Any other settlement: its map label is clicked, after
    bringing it on screen (bring_into_view)."""
    prov, cap = region_provinces()
    col = f"CcoCampaignSettlement{region}"
    if cap.get(region):
        row = province_row(ui, prov.get(region))
        if row is not None:
            click(ui, row)
            if wait.wait_until(lambda: ui.root_child("settlement_panel") and (lambda c: c and (ui.state(c) or "")
                               .startswith("selected"))(ui.first(col, under="settlement_list")), 2.0,
                               f"{region} selected", must=False):
                return True
            clear(ui)
    label = f"label_settlement:{region}"
    lab, _jumped = bring_into_view(w, ui, *xy, label, jump=lambda: jump_row(ui, province_row(ui, prov.get(region))))
    if lab is None:
        return False
    click(ui, lab.ptr)
    return wait.wait_until(lambda: ui.root_child("settlement_panel") and (lambda c: c and (ui.state(c) or "")
                           .startswith("selected"))(ui.first(col, under="settlement_list")), 2.0,
                           f"{region} selected", must=False) is not None


def recruit_engineer(ui: UI, w: World, F: int, region: str):
    """Recruit a Warlock Engineer at the settlement of `region` through its Recruit Hero panel, which is the game's
    own answer to "can an engineer be recruited here": the engineer tab is inactive (with a "Building required"
    marker) where the province cannot, and the Recruit button is inactive when the faction cap is full.
    Returns (status, log line, the new Character or None); status: "ok", "not_here", "cap", "failed"."""
    before = {c.ptr for c in characters(w, F) if c.subtype == ENGINEER}
    pos = settlement_pos(w, F)
    if region not in pos:
        return "not_here", f"no settlement of ours in {region_name(region)}", None
    clear(ui)
    if not select_settlement(ui, w, region, pos[region]):
        return "failed", f"could not bring {region_name(region)} on screen", None
    b = wait.appears(ui, "button_agents", under="button_group_settlement", timeout=2.0, must=False)
    if b is None:
        clear(ui)
        return "failed", f"hero recruitment button not found at {region_name(region)}", None
    click(ui, b.ptr)
    tab = wait.appears(ui, "engineer", under="agent_parent", timeout=2.0, must=False)
    if tab is None:
        clear(ui)
        return "not_here", f"no Warlock Engineer tab at {region_name(region)}", None
    tab = tab.ptr
    if on_screen_still(ui, tab, "engineer tab") is None:
        clear(ui)
        return "failed", f"the Recruit Hero panel did not come up at {region_name(region)}", None
    wait.stable(lambda: ui.state(tab), n=2, timeout=1.0, what="engineer tab state", ui=ui, must=False)
    if ui.state(tab) == "inactive":
        needs = first(ui, "icon_building_required", under="engineer")
        clear(ui)
        if needs is not None:
            text = re.sub(r"\[\[img:[^\]]*\]\]\[\[/img\]\]", "", card_text(ui, needs).split("Left-click")[0])
            return "not_here", f"{region_name(region)} needs " + " or ".join(
                x.strip() for x in text.splitlines()[1:] if x.strip()), None
        return "cap", "engineer tab inactive", None
    click(ui, tab)
    # the panel's "<fielded> / <cap>" is the selected hero type's: kept for the tick boxes (refill_check)
    if wait.wait_until(lambda: (ui.state(tab) or "").startswith("selected"), 1.0, "engineer tab selected", must=False):
        shown = first(ui, "dy_agent_cap", under="character_panel")
        m = re.search(r"(\d+)\s*/\s*(\d+)", (ui.text(shown) or "") if shown else "")
        if m:
            save_caps(engineer_cap=int(m.group(2)))
    got = wait.wait_until(lambda: (lambda a, b: (a, b) if a and b else None)(
        first(ui, "button_wh3", under="general_candidate_0_"), first(ui, "button_confirm")), 2.0,
        "Engineer candidate offered", must=False)
    if got is None:
        clear(ui)
        return "cap", "no Engineer candidate offered", None
    cand, conf = got
    st0 = ui.state(conf)
    click(ui, cand)
    wait.wait_until(lambda: (ui.state(cand) or "").startswith("selected") or ui.state(conf) != st0, 0.5,
                    "Engineer candidate taken", must=False)
    wait.stable(lambda: ui.state(conf), n=2, timeout=1.0, what="Recruit button state", ui=ui, must=False)
    if ui.state(conf) == "inactive":
        clear(ui)
        return "cap", "Recruit button inactive", None
    n0 = w.u32(F + 0xF24)
    from bot.sensor import commands             # paced by the game: the command, then the new character in memory
    commands.act(w.pm, lambda: click(ui, conf) and None, lambda: w.u32(F + 0xF24) != n0)
    clear(ui)
    park()
    new = [c for c in characters(w, F) if c.subtype == ENGINEER and c.ptr not in before]
    if not new:
        return "failed", f"Engineer recruitment at {region_name(region)} did not go through", None
    return "ok", f"recruited Warlock Engineer {new[0].name} at {region_name(region)}", new[0]


def engineer_candidates(w: World, F: int, army) -> list[str]:
    """Owned settlements whose province can recruit a Warlock Engineer, nearest the army first (region hops, then
    straight-line distance): provinces with an enabling building (assist/recruit.py), and the province any
    Verminlord Warpseer with Inscrutable Genius stands in (the army's own lord included)."""
    from .recruit import sources
    own = {w.region_key(r) for r in w.faction_regions(F)}
    prov, _ = region_provinces()
    regions = {r for _, r, _ in sources(w).get(ENGINEER, [])}
    for a in armies(w, F):
        if a.general_ptr and a.region in own and INSCRUTABLE_GENIUS in character_skills(w, a.general_ptr):
            # the skill opens the whole province, not only his settlement: 2026-10-18, Chant in Karak Ziflin (a minor
            # settlement without a garrison commander, so no map position) left Blackstone Post untried
            regions |= {r for r in own if prov.get(r) == prov.get(a.region)}
    if not regions or not army.region_obj:
        return sorted(regions)
    pos = settlement_pos(w, F)
    ax, ay = character_pos(w.pm, army.general_ptr)
    order = {}
    for r, hops in hops_from(w, army.region_obj):
        k = w.region_key(r)
        if k in regions and k not in order:
            sx, sy = pos.get(k, (ax, ay))
            order[k] = (hops, math.hypot(sx - ax, sy - ay))
    return sorted(regions, key=lambda k: order.get(k, (999, 0.0)))


def get_engineer(ui: UI, w: World, F: int, army):
    """Recruit this army's Warlock Engineer at the nearest settlement that can, wherever the army is.
    Returns (log line, the new Character or None). Nothing is recruited while the faction cap is full."""
    tried = []
    for region in engineer_candidates(w, F, army):
        status, msg, new = recruit_engineer(ui, w, F, region)
        if status == "ok":
            return msg, new
        if status == "cap":
            n = engineers_fielded(w, F)
            save_caps(engineer_cap=n)
            return f"no Warlock Engineer yet: cap {n}/{n} (raised by the Verminlord Warpseer skill Inscrutable Genius)", None
        tried.append(msg)
        if status == "failed":
            break
    if not tried:
        return "no Warlock Engineer yet: no province can recruit one (needs a Construction Cavern)", None
    return "no Warlock Engineer yet: " + "; ".join(tried), None

# ------------------------------------------------------------------ caps the game only shows in its panels

def load_caps() -> dict:
    """What the panels last showed, for this campaign's faction: {"engineer_cap": n, "supply_lines_pct": p}."""
    from .army import _faction
    try:
        return json.loads(CAPS.read_text(encoding="utf-8")).get(_faction(), {})
    except (OSError, ValueError, AttributeError):
        return {}


def save_caps(**values) -> None:
    from .army import _faction
    try:
        d = json.loads(CAPS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d.setdefault(_faction(), {}).update(values)
    tmp = CAPS.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
    from tools.fileio import replace as _replace
    _replace(tmp, CAPS)


def free_engineer_slots(w: World, F: int) -> int | None:
    """Engineers the cap still allows (the cap as the Recruit Hero panel last showed it); None: never read yet."""
    cap = load_caps().get("engineer_cap")
    return None if cap is None else cap - engineers_fielded(w, F)


def refill_check(w: World, F: int, army, d, elig_any: bool | None = None, slots: int | None | str = "read",
                 claims: dict[int, int] | None = None) -> tuple[bool, str]:
    """(the army can be ticked for a refill, why not). Player rule 2026-10-18: only an army missing template units
    (troops or its Warlock Engineer) can be ticked, and only while the refill is possible: a province recruits the
    whole template (for missing troops), and an engineer is free or the engineer cap has room (for a missing
    engineer; a cap never read yet does not block). elig_any / slots / claims: precomputed for many armies."""
    from .army import load_automation
    troops = bool(d.missing)
    eng = d.heroes_missing.get(ENGINEER, 0) > 0
    if not troops and not eng:
        return False, "nothing missing: tick an army once it has lost units"
    if troops:
        if elig_any is None:
            elig_any = bool(eligible(w, F, set(load_automation()["army_builder"]["template"]["units"])))
        if not elig_any:
            return False, "cannot refill: no province can recruit the whole template yet"
    if eng:
        claims = _load_claims() if claims is None else claims
        free = any(c.embedded_force == 0 and c.subtype == ENGINEER and claims.get(w.u32(c.ptr + 0x110), army.cqi)
                   == army.cqi for c in characters(w, F))
        slots = free_engineer_slots(w, F) if slots == "read" else slots
        if not free and slots is not None and slots <= 0:
            return False, "cannot refill: no Warlock Engineer free and the engineer cap is full"
    return True, ""


def _load_claims() -> dict[int, int]:
    try:
        return {int(k): int(v) for k, v in json.loads(CLAIMS.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError):
        return {}


def _save_claims(claims: dict[int, int]) -> None:
    tmp = CLAIMS.with_suffix(".tmp")
    tmp.write_text(json.dumps({str(k): v for k, v in claims.items()}, indent=1), encoding="utf-8")
    from tools.fileio import replace as _replace
    _replace(tmp, CLAIMS)


def assign_engineers(w: World, F: int, acting: list) -> dict[int, list]:
    """army cqi -> the free Warlock Engineers that count as its engineer. An engineer keeps the army it was given
    while that army still lacks one; the others go to the armies still lacking one, closest first."""
    free = {w.u32(c.ptr + 0x110): c for c in characters(w, F) if c.embedded_force == 0 and c.subtype == ENGINEER}
    need = {a.cqi: delta(a, []).heroes_missing.get(ENGINEER, 0) for a in acting}
    out: dict[int, list] = {a.cqi: [] for a in acting}
    claims: dict[int, int] = {}
    for hid, cqi in _load_claims().items():
        if hid in free and cqi in need and len(out[cqi]) < need[cqi]:
            claims[hid] = cqi
            out[cqi].append(free[hid])
    for a in acting:
        ax, ay = character_pos(w.pm, a.general_ptr)
        while len(out[a.cqi]) < need[a.cqi]:
            pool = [(hid, c) for hid, c in free.items() if hid not in claims]
            if not pool:
                break

            def dist(t):
                hx, hy = character_pos(w.pm, t[1].ptr)
                return math.hypot(hx - ax, hy - ay)
            hid, c = min(pool, key=dist)
            claims[hid] = a.cqi
            out[a.cqi].append(c)
    _save_claims(claims)
    return out


def claim(w: World, c, cqi: int) -> None:
    claims = _load_claims()
    claims[w.u32(c.ptr + 0x110)] = cqi
    _save_claims(claims)


def walk_engineer(ui: UI, w: World, F: int, hero, army, log) -> str:
    """Send a free engineer into the army (every turn until it joins: the army may have moved)."""
    name = hero.name
    mv = hero_movement(w, hero.ptr)
    if mv is not None and mv <= 0.01:
        return f"engineer {name} has no movement left this turn (just recruited?); walks to the army next turn"
    if len(army.units) + len(army.queued) >= FULL:
        return f"army is full ({FULL}/{FULL}): engineer {name} cannot join; make room"
    lord = next((c for c in characters(w, F) if c.ptr == army.general_ptr), None)
    if lord is None:
        return f"lord of {army.general_name} not found"
    wait_until_stopped(w, lord.ptr)                # an army ordered to march this pass: its flag is still moving
    p0 = character_pos(w.pm, hero.ptr)
    ap0, _, _, mx = struct.unpack("<4i", w.pm.read_bytes(hero.ptr + 0x30, 16))    # left, ..., per-turn max
    msg = move_into_army(hero, lord, log, ui=ui)
    if "on the way" not in msg:
        return msg
    p1 = wait_until_stopped(w, hero.ptr)          # the hero is still walking: wait until he stops (or joins)
    if any(c.ptr == hero.ptr and c.embedded_force for c in characters(w, F)):
        return f"{name} joined {army.general_name}'s army"    # the embed lands when the walk ends
    ap1 = struct.unpack("<i", w.pm.read_bytes(hero.ptr + 0x30, 4))[0]
    lx, ly = character_pos(w.pm, army.general_ptr)
    used = (ap0 - ap1) / mx if mx > 0 else 0
    moved = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    left = math.hypot(lx - p1[0], ly - p1[1])
    eta = f" (about {max(1, math.ceil(left / (moved / used)))} more turns)" if used > 0.05 and moved > 0.5 else ""
    return f"engineer {name} walking to {army.general_name}{eta}"


# ------------------------------------------------------------------ the step

def build_one(ui: UI, w: World, F: int, army, mine: list, log, verify: bool = False):
    """One ticked army. mine: the free engineers that count as its engineer. Returns (log lines, the engineer
    recruited for it this turn or None). Everything is decided from memory first; the army is selected (a single
    click on its Lords & Heroes row, no camera move) only when a disband, a recruitment or a move order follows, so an
    army that matches the template costs no input at all."""
    name = army.general_name
    out, recruited = [], None
    prov, _ = region_provinces()
    own = {w.region_key(r) for r in w.faction_regions(F)}
    here = prov.get(army.region or "") if army.region in own else None
    for c in extra_heroes(w, F, army):
        out.append(f"extra hero {c.name} in {name}: remove it yourself")
    d0 = delta(army, [])
    # Player rule: never strip an army away from its recruiting province (a lone lord gets attacked on the
    # march). Off-template troops are disbanded only once the army stands in a province that can recruit its
    # missing units locally, right before recruiting the replacements.
    if d0.disband:
        if not d0.missing or here in eligible(w, F, set(d0.missing)):
            if not select_army(ui, army):
                return [f"{name}: could not select the army"], None
            out += disband(ui, w, F, army, log)
            army = next((a for a in armies(w, F) if a.cqi == army.cqi), army)
        else:
            out.append("keeping off-template units until the army reaches a recruiting province")
    d = delta(army, [])
    missing = dict(d.missing)
    if missing:
        elig = eligible(w, F, set(missing))
        if here in elig:
            if not select_army(ui, army):
                return [f"{name}: could not select the army"], None
            out += recruit_local(ui, w, F, {u: n for u, n in missing.items() if u in elig[here]}, log)
        else:
            tgt = closest_target(w, F, army, elig)
            if tgt is None:
                out.append("no province can recruit the whole template yet (it needs every unit's building); "
                           "the army stays where it is")
            else:
                region, province, hops = tgt
                if not verify:                 # a verification run does not order the march again
                    if not select_army(ui, army):
                        return [f"{name}: could not select the army"], None
                    out.append(move_to(ui, w, army, region) + f" ({hops} regions away)")
    # Engineer (player rule 2026-10-16): never a reason to move the army or to pick a province. Recruited as soon
    # as the faction cap allows, at the settlement nearest the army that can recruit one, then walked to the army.
    if d.heroes_missing.get(ENGINEER, 0) > len(mine):
        msg, recruited = get_engineer(ui, w, F, army)
        out.append(msg)
        if recruited is not None:
            claim(w, recruited, army.cqi)          # at once: it is this army's even if a later step fails
    army = next((a for a in armies(w, F) if a.cqi == army.cqi), army)
    if army.queued:
        out.append(f"{len(army.queued)} units in recruitment")
    for c in ([] if verify else mine + ([recruited] if recruited else [])):   # walks: ordered by the first run
        out.append(walk_engineer(ui, w, F, c, army, log))
    return ([f"{name}: {x}" for x in out] if out else [f"{name}: matches template"]), recruited


def run(log=print, verify: bool = False) -> str:
    """verify: the runner's verification run (assist/runner.py): only disbands, recruitment and engineer recruitment
    are redone if they did not happen; march and walk orders are not issued again."""
    ticked = enabled_armies()
    w = World()
    F = find_player_faction(w)
    if F is None:
        return "player faction not found"
    ui = UI(w.s)
    ui.find_root()
    out, acting = [], []
    present = armies(w, F)
    for a in present:
        ok, why = tick_for(a, ticked)
        if ok:
            acting.append(a)
        elif why:
            out.append(f"{a.general_name}: {why}")
    gone = [e.get("name") or str(cqi) for cqi, e in ticked.items() if cqi not in {a.cqi for a in present}]
    if gone:
        out.append("ticked army not in this campaign: " + ", ".join(gone))
    with game_focus():
        # a new army first (player rule 2026-10-18), so it is recruited in this same pass; never on a verification run
        if not verify:
            from .new_army import create
            try:
                lines, new = create(ui, w, F, log)
            except Exception as ex:
                import traceback
                traceback.print_exc()
                lines, new = [f"new army: ERROR {ex}"], None
            out += lines
            if new is not None:
                acting.append(new)
        if not acting:
            return "; ".join(out) or "no ticked army here"
        mine = assign_engineers(w, F, acting)
        for a in acting:
            try:
                lines, _new = build_one(ui, w, F, a, mine.get(a.cqi, []), log, verify=verify)
            except Exception as ex:                   # one army's failure must not skip the others
                import traceback
                traceback.print_exc()
                lines = [f"{a.general_name}: ERROR {ex}"]
            out += lines
    out += untick_refilled(w, F, acting)
    return "; ".join(out)


def untick_refilled(w: World, F: int, acting: list) -> list[str]:
    """A tick means "refill once" (player rule 2026-10-18): it is cleared once the army has every template unit
    (queued ones count) and its engineer has joined."""
    out = []
    now = {a.cqi: a for a in armies(w, F)}
    for a in acting:
        a2 = now.get(a.cqi)
        d = delta(a2, []) if a2 else None
        if d is not None and not d.missing and not d.heroes_missing and not d.disband:
            set_enabled(a2.cqi, a2.general_name, False, a2.general_id)
            out.append(f"{a2.general_name}: refilled, tick cleared")
    return out
