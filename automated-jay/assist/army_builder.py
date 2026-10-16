"""Army builder: make each ticked army match the template, one turn-start pass at a time.

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
import time
from collections import Counter, deque

from bot import config
from bot.focus import game_focus
from bot.sensor.camera import character_pos
from bot.sensor.ui import UI
from bot.sensor.world import World, armies, characters, find_player_faction, region_provinces, string_object
from tools.ui import click_at, held, move_to as move_cursor, press, wheel
from . import gamedata as gd
from .army import delta, enabled_armies, load_automation, tick_for, unit_name
from .heroes import _double_click, hero_movement, move_into_army, open_lords_list, pan_until_visible

PARK = (1700, 760)
ENGINEER = "wh2_main_skv_warlock_engineer"
CLAIMS = config.RUNS_DIR / "engineer_claims.json"     # engineer character id -> army cqi it walks to
FULL = 20                                             # units per army, lord and heroes included


def region_name(k: str) -> str:
    return gd.loc().get("regions_onscreen_" + k, k)


# ------------------------------------------------------------------ small UI helpers

def first(ui: UI, cid: str, under: str | None = None):
    """First visible component with this id (optionally below a component with id `under`): UI.first."""
    return ui.first(cid, under=under)


def clear(ui: UI) -> None:
    """Close the escape menu if open; otherwise press Escape once only when a panel or selection is open
    (Escape with nothing selected opens the game menu)."""
    from . import popups
    open_ = [cid for _, cid in popups.scan(ui)]
    if "esc_menu" in open_:
        b = first(ui, "button_resume")
        if b:
            click_at(*ui.comp(b).center)
            time.sleep(0.6)
        return
    busy = first(ui, "main_units_panel") or first(ui, "recruitment_docker") or first(ui, "settlement_panel") \
        or first(ui, "character_panel")
    if busy:
        press("esc")
        time.sleep(0.4)
        if "esc_menu" in [cid for _, cid in popups.scan(ui)]:
            b = first(ui, "button_resume")
            if b:
                click_at(*ui.comp(b).center)
                time.sleep(0.6)


def park() -> None:
    move_cursor(*PARK)
    time.sleep(0.3)


def select_army(ui: UI, general_id: int) -> bool:
    """Select a lord's army by double-clicking his Lords & Heroes row (also centres the camera)."""
    clear(ui)
    open_lords_list()
    row = first(ui, f"character_row_{general_id}")
    if row is None:
        return False
    _double_click(*ui.comp(row).center)
    park()
    return first(ui, "units", under="main_units_panel") is not None


def unit_cards(ui: UI) -> tuple[list, list]:
    """(troop cards in display order excluding the lord, hero cards) from the selected army's panel."""
    troops, heroes = [], []
    for c, ids in ui.walk():
        if "main_units_panel" not in ids:
            continue
        n = ids[-1]
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
    t = first(ui, "button_tick", under="dialogue_box") or first(ui, "button_tick", under="popup_message_box")
    if t is None:
        return False
    click_at(*ui.comp(t).center)
    time.sleep(1.2)
    return True


def press_disband(ui: UI, over_card: int) -> bool:
    k = ui.comp(over_card)
    move_cursor(k.center[0], int(k.y) + 10)         # the unit button group appears above the card
    time.sleep(0.6)
    b = first(ui, "button_disband")
    if b is None:
        return False
    click_at(*ui.comp(b).center)
    time.sleep(1.0)
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
    troops, hero_cards = unit_cards(ui)
    names = [card_unit_name(ui, c) for c in troops]
    if len(troops) != len(troop_keys) or Counter(names) != Counter(unit_name(k) for k in troop_keys):
        return ["disband skipped: the unit cards do not match the army in memory"]
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
    click_at(*ui.comp(pick[0]).center)
    time.sleep(0.3)
    if len(pick) > 1:
        with held("shift" if contiguous else "ctrl"):
            time.sleep(0.08)
            for c in ([pick[-1]] if contiguous else pick[1:]):
                click_at(*ui.comp(c).center)
                time.sleep(0.1)
    time.sleep(0.4)
    sel = [i for i, c in enumerate(troops) if card_selected(ui, c)]
    lord = first(ui, "LandUnit 0", under="main_units_panel")
    others = [c for c in hero_cards + ([lord] if lord else []) if card_selected(ui, c)]
    sel_keys = Counter(key_of.get(card_unit_name(ui, troops[i]), "?") for i in sel)
    if sel != targets or others or sel_keys != expect:
        park()
        return [f"disband skipped: the selection did not match (selected troop cards {sel}, wanted {targets}"
                + (", a lord or hero card was selected" if others else "") + ")"]
    before = Counter(u.key for u in army.units)
    if not press_disband(ui, pick[-1]):
        park()
        return ["disband skipped: the disband button or its confirmation did not appear"]
    after = before
    for _ in range(12):
        time.sleep(0.4)
        a2 = next((a for a in armies(w, F) if a.cqi == army.cqi), None)
        after = Counter(u.key for u in a2.units) if a2 else Counter()
        if after != before:
            time.sleep(0.5)
            a2 = next((a for a in armies(w, F) if a.cqi == army.cqi), None)
            after = Counter(u.key for u in a2.units) if a2 else Counter()
            break
    gone, added = before - after, after - before
    park()
    if gone == expect and not added:
        return ["disbanded " + ", ".join(f"{n} {unit_name(k)}" for k, n in gone.items()) + " (checked in memory)"]
    return [f"WARNING: meant to disband {dict(expect)}, memory shows gone {dict(gone)}"
            + (f", added {dict(added)}" if added else "")]


# ------------------------------------------------------------------ recruitment awareness

def eligible(w: World, F: int, need: set[str]) -> dict[str, set[str]]:
    """province -> the needed units it can recruit locally right now."""
    from .recruit import sources
    out: dict[str, set[str]] = {}
    for unit, where in sources(w).items():
        if unit not in need:
            continue
        for p, _r, _b in where:
            out.setdefault(p, set()).add(unit)
    return out


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
    card sits inside its list_clip; each notch moves the cards about 82 px."""
    clip, c = None, card
    for _ in range(12):
        c = ui.parent(c)
        if not c:
            break
        if ui.id(c) == "list_clip":
            clip = c
            break
    if clip is None:
        return False
    for _ in range(40):
        cc, cl = ui.comp(card), ui.comp(clip)
        if cl.x <= cc.x and cc.x + cc.w <= cl.x + cl.w:
            return True
        wheel(*cl.center, -1 if cc.x > cl.x else 1, pause=0.15)
    return False


def recruit_local(ui: UI, w: World, missing: dict[str, int], log) -> list[str]:
    btn = first(ui, "button_recruitment")
    if btn is None:
        return ["recruitment button not found"]
    click_at(*ui.comp(btn).center)
    time.sleep(1.2)
    park()
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
            before = w.s.read().treasury
            click_at(*ui.comp(card).center)
            time.sleep(0.5)
            if (w.s.read().treasury or 0) >= (before or 0):
                break                          # not taken: local capacity full or not affordable
            done += 1
        if done:
            out.append(f"queued {done} {unit_name(unit)}")
        if done < n:
            out.append(f"{n - done} {unit_name(unit)} left for later turns")
    clear(ui)
    return out


def move_to(ui: UI, w: World, army, region: str) -> str:
    pos = settlement_pos(w, find_player_faction(w))
    if region not in pos:
        return f"no position for {region}"
    x, y = pos[region]
    lab = pan_until_visible(w, ui, x, y, f"label_settlement:{region}")
    if lab is None:
        return f"could not bring {region} on screen"
    click_at(*lab.center, right=True)
    time.sleep(1.5)
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
    lab = pan_until_visible(w, ui, *pos[region], f"label_settlement:{region}")
    if lab is None:
        return "failed", f"could not bring {region_name(region)} on screen", None
    click_at(*lab.center)
    time.sleep(1.2)
    b = first(ui, "button_agents")
    if b is None:
        clear(ui)
        return "failed", f"hero recruitment button not found at {region_name(region)}", None
    click_at(*ui.comp(b).center)
    time.sleep(1.2)
    tab = first(ui, "engineer", under="agent_parent")
    if tab is None:
        clear(ui)
        return "not_here", f"no Warlock Engineer tab at {region_name(region)}", None
    if ui.state(tab) == "inactive":
        needs = first(ui, "icon_building_required", under="engineer")
        clear(ui)
        if needs is not None:
            text = re.sub(r"\[\[img:[^\]]*\]\]\[\[/img\]\]", "", card_text(ui, needs).split("Left-click")[0])
            return "not_here", f"{region_name(region)} needs " + " or ".join(
                x.strip() for x in text.splitlines()[1:] if x.strip()), None
        return "cap", "engineer tab inactive", None
    click_at(*ui.comp(tab).center)
    time.sleep(0.8)
    cand = first(ui, "button_wh3", under="general_candidate_0_")
    conf = first(ui, "button_confirm")
    if cand is None or conf is None:
        clear(ui)
        return "cap", "no Engineer candidate offered", None
    click_at(*ui.comp(cand).center)
    time.sleep(0.5)
    if ui.state(conf) == "inactive":
        clear(ui)
        return "cap", "Recruit button inactive", None
    click_at(*ui.comp(conf).center)
    time.sleep(1.5)
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
    regions = {r for _, r, _ in sources(w).get(ENGINEER, [])}
    for a in armies(w, F):
        if a.general_ptr and a.region in own and INSCRUTABLE_GENIUS in character_skills(w, a.general_ptr):
            regions.add(a.region)
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
            return f"no Warlock Engineer yet: cap {n}/{n} (raised by the Verminlord Warpseer skill Inscrutable Genius)", None
        tried.append(msg)
        if status == "failed":
            break
    if not tried:
        return "no Warlock Engineer yet: no province can recruit one (needs a Construction Cavern)", None
    return "no Warlock Engineer yet: " + "; ".join(tried), None

def _load_claims() -> dict[int, int]:
    try:
        return {int(k): int(v) for k, v in json.loads(CLAIMS.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError):
        return {}


def _save_claims(claims: dict[int, int]) -> None:
    tmp = CLAIMS.with_suffix(".tmp")
    tmp.write_text(json.dumps({str(k): v for k, v in claims.items()}, indent=1), encoding="utf-8")
    tmp.replace(CLAIMS)


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


def walk_engineer(w: World, F: int, hero, army, log) -> str:
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
    p0 = character_pos(w.pm, hero.ptr)
    ap0, _, _, mx = struct.unpack("<4i", w.pm.read_bytes(hero.ptr + 0x30, 16))    # left, ..., per-turn max
    msg = move_into_army(hero, lord, log)
    if "on the way" not in msg:
        return msg
    p1, end = character_pos(w.pm, hero.ptr), time.monotonic() + 10
    while time.monotonic() < end:                 # the hero is still walking: wait until he stops
        time.sleep(0.8)
        p = character_pos(w.pm, hero.ptr)
        if p == p1:
            break
        p1 = p
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

def build_one(ui: UI, w: World, F: int, army, mine: list, log):
    """One ticked army. mine: the free engineers that count as its engineer. Returns (log lines, the engineer
    recruited for it this turn or None)."""
    name = army.general_name
    out, recruited = [], None
    if not select_army(ui, army.general_id):
        return [f"{name}: could not select the army"], None
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
            out += disband(ui, w, F, army, log)
            army = next((a for a in armies(w, F) if a.cqi == army.cqi), army)
        else:
            out.append("keeping off-template units until the army reaches a recruiting province")
    d = delta(army, [])
    missing = dict(d.missing)
    if missing:
        elig = eligible(w, F, set(missing))
        if here in elig:
            select_army(ui, army.general_id)
            out += recruit_local(ui, w, {u: n for u, n in missing.items() if u in elig[here]}, log)
        else:
            tgt = closest_target(w, F, army, elig)
            if tgt is None:
                out.append("no free settlement in a province that can recruit the missing units")
            else:
                region, province, hops = tgt
                select_army(ui, army.general_id)
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
    for c in mine + ([recruited] if recruited else []):
        out.append(walk_engineer(w, F, c, army, log))
    return ([f"{name}: {x}" for x in out] if out else [f"{name}: matches template"]), recruited


def run(log=print) -> str:
    ticked = enabled_armies()
    if not ticked:
        return "no army ticked"
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
    if not acting:
        return "; ".join(out) or "no ticked army here"
    mine = assign_engineers(w, F, acting)
    with game_focus():
        for a in acting:
            try:
                lines, _new = build_one(ui, w, F, a, mine.get(a.cqi, []), log)
            except Exception as ex:                   # one army's failure must not skip the others
                import traceback
                traceback.print_exc()
                lines = [f"{a.general_name}: ERROR {ex}"]
            out += lines
        park()
    return "; ".join(out)
