"""Rites and commandments (player build, 2026-10-17).

Commandments: every complete province is permanently on Exploitative Planning, except that the Dominating Scheme
needs Expansionist Planning first: on a fresh campaign (no complete province has a commandment yet) the first
complete province gets Expansionist Planning, and keeps it until the rite has been cast once (its cooldown runs in
memory); then it switches to Exploitative Planning like every other. After that there is always an Exploitative
province, so the Expansionist phase never comes back.
Rite: The Dominating Scheme is cast whenever it is off cooldown and affordable, before buildings and the army builder
spend the gold (player rule). After Horned One's Approval the rite is its Verminlord version, and every cast opens a
dilemma: it is answered with "A Verminlord Warpseer" (player rule; every other dilemma stays the player's).

Memory (9.0.4, found 2026-10-17 from the game's own Lua bindings):
  rites         ritual manager R = [faction + 0x1B58]; entries u32 R+0xBC, array R+0xC0, stride 0x28;
                entry+0x08 = ritual record (key: string object [record+0x60]), entry+0x10 = cooldown left (turns)
  commandments  the faction's provinces: array [faction + 0xF80] (pointers to pointers), count u32 faction+0xF7C;
                FP+0xE0 = a region it owns; picked ("incoming") commandment: byte FP+0x458, record [FP+0x410];
                active commandment: byte FP+0x4A8, record [FP+0x460]; key = string object at record+8.
                A picked commandment becomes active later, so a pick is confirmed on the "picked" pair.
UI:
  rites         HUD button_rituals -> rituals_panel; card context_rituals_list/CcoCampaignRitual51<ritual key> with
                action/button_perform (active when it can be cast), cost/dy_gold_cost, tx_frame/dy_unlock_requirements;
                closed with button_ok. Casting asks nothing more.
  dilemma       root "events": ...CcoCdirEventsDilemmaChoiceDetailRecordwh3_dlc29_ascendancy_summon_verminlord<N>/
                choice_button, N = FIRST..FIFTH; THIRD is A Verminlord Warpseer. One click closes it.
  commandments  select the province (its Provinces list row); the HUD's stack_incentives then shows its slot
                (button_<commandment key>, or button_default when none). Hovering the slot opens the list (a hover
                popup: the cursor must travel inside it); clicking a commandment picks it.
"""
from __future__ import annotations
import re
import struct
import time

from bot.focus import game_focus
from bot.sensor.ui import UI
from bot.sensor.world import World, find_player_faction, region_provinces, string_object
from tools import wait
from tools.ui import click, move_path, move_to
from . import gamedata as gd

EXPLOITATIVE = "wh2_main_edict_skv_devious_planning"      # "Exploitative Planning"
EXPANSIONIST = "wh2_main_edict_skv_expansionist_planning"
RITE = "wh2_main_ritual_skv_ascendancy"                   # The Dominating Scheme
RITE_VERMINLORD = "wh3_main_ritual_skv_ascendancy_verminlord"   # its version after Horned One's Approval
VERMINLORD_DILEMMA = "wh3_dlc29_ascendancy_summon_verminlord"
WARPSEER_CHOICE = "THIRD"                                  # "A Verminlord Warpseer"
RITES = (RITE_VERMINLORD, RITE)


# ------------------------------------------------------------------ memory
def _q(w: World, a: int) -> int:
    try:
        return w.q(a)
    except Exception:
        return 0


def _observe(w, F: int, key: str, **fields) -> None:
    """What the Rites panel showed next to what memory held, each time the Dominating Scheme's card is read or it is
    cast (2026-10-19: the data to replace the card's cost and lock with memory reads): runs/rites_observe.jsonl."""
    import json
    from bot import config
    try:
        line = {"t": round(time.time(), 1), "turn": w.s.read().turn, "rite": key,
                "treasury": w.s.read().treasury, "cooldowns": rite_cooldowns(w, F), **fields}
        with open(config.RUNS_DIR / "rites_observe.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except Exception:
        pass


def rite_cost(w: World, F: int, key: str) -> int | None:
    """A rite's gold cost from memory: its ritual record's resource transaction [rec+0x80], treasury change i32
    +0x50 (negative: a cost), the field the UI context TreasuryCost reads (FUN_141ef0f64, 9.0.4, 2026-10-19).
    Checked: the Dominating Scheme -3000, as resource_costs_tables and as the game charged on turn 24. None when
    the rite is not found."""
    R = _q(w, F + 0x1B58)
    if not R:
        return None
    n, arr = w.u32(R + 0xBC), _q(w, R + 0xC0)
    for i in range(min(n, 400)):
        rec = _q(w, arr + 0x28 * i + 8)
        try:
            if string_object(w.pm, _q(w, rec + 0x60)) == key:
                T = _q(w, rec + 0x80)
                return -struct.unpack("<i", w.pm.read_bytes(T + 0x50, 4))[0] if T else None
        except Exception:
            continue
    return None


def rite_cooldowns(w: World, F: int) -> dict[str, int]:
    """Cooldown left (turns) of every rite the faction has, by ritual key."""
    out = {}
    R = _q(w, F + 0x1B58)
    if not R:
        return out
    n, arr = w.u32(R + 0xBC), _q(w, R + 0xC0)
    for i in range(min(n, 400)):
        e = arr + 0x28 * i
        rec = _q(w, e + 8)
        try:
            key = string_object(w.pm, _q(w, rec + 0x60))
            if key:
                out[key] = w.u32(e + 0x10)
        except Exception:
            pass
    return out


def provinces(w: World, F: int) -> list[dict]:
    """The faction's provinces: {province, complete, picked, active}. Complete = every region of the province (game
    data) is the player's (memory)."""
    prov, _ = region_provinces()
    owned = {w.region_key(r) for r in w.faction_regions(F)}
    regions_of: dict[str, list[str]] = {}
    for r, p in prov.items():
        regions_of.setdefault(p, []).append(r)

    def key(flag_off: int, rec_off: int, FP: int):
        try:
            if w.pm.read_bytes(FP + flag_off, 1)[0]:
                return string_object(w.pm, _q(w, FP + rec_off) + 8)
        except Exception:
            pass
        return None
    out = []
    n, arr = w.u32(F + 0xF7C), _q(w, F + 0xF80)
    for i in range(min(n, 400)):
        FP = _q(w, _q(w, arr + 8 * i))
        reg = _q(w, FP + 0xE0)
        p = prov.get(w.region_key(reg)) if reg else None
        if not p:
            continue
        out.append({"province": p, "complete": all(r in owned for r in regions_of.get(p, [])),
                    "picked": key(0x458, 0x410, FP), "active": key(0x4A8, 0x460, FP)})
    return out


def wanted_commandments(provs: list[dict], cooldowns: dict[str, int]) -> dict[str, str]:
    """Province -> the commandment it should have picked (the player's rules above)."""
    complete = [p for p in provs if p["complete"]]
    cast = any(cooldowns.get(k, 0) > 0 for k in RITES)
    on_expansionist = [p for p in complete if EXPANSIONIST in (p["picked"], p["active"])]
    fresh = not any(p["picked"] or p["active"] for p in complete)
    want = {p["province"]: EXPLOITATIVE for p in complete}
    if on_expansionist and not cast:
        want[on_expansionist[0]["province"]] = EXPANSIONIST           # keep it until the first cast
    elif fresh and complete and not cast:
        want[complete[0]["province"]] = EXPANSIONIST                  # fresh campaign: the unlock comes first
    return want


def rite_waits(provs: list[dict], cooldowns: dict[str, int]) -> str | None:
    """Why the Dominating Scheme cannot be cast yet, from memory, or None when it can be tried. Player report
    2026-10-18 (Thanquol, turn 1, no complete province): the Rites panel showed Perform Rite active although the rite
    was still locked, and the click did nothing. The game's scripts unlock it once Expansionist Planning has been in
    effect over a province (a commandment needs a complete province; a pick takes effect a turn later). The rite's
    entry carries no lock flag, so: unlocked = Expansionist Planning in effect somewhere, or the rite was cast before
    (its cooldown runs, or a province is on Exploitative Planning, which wanted_commandments only allows after the
    first cast)."""
    complete = [p for p in provs if p["complete"]]
    if not complete:
        return "Dominating Scheme waits: no complete province yet (it unlocks through a commandment)"
    if any(cooldowns.get(k, 0) > 0 for k in RITES):
        return None
    if any(p["active"] == EXPANSIONIST for p in complete):
        return None
    if any(EXPLOITATIVE in (p["picked"], p["active"]) for p in complete):
        return None
    on = next((p for p in complete if p["picked"] == EXPANSIONIST), None)
    if on:
        place = gd.loc().get(f"provinces_onscreen_{on['province']}", on["province"])
        return f"Dominating Scheme waits: Expansionist Planning in {place} takes effect next turn"
    return "Dominating Scheme waits: Expansionist Planning has to be in effect over a province first"


def fingerprint(w: World, F: int) -> tuple:
    """What this step changes (for the runner's verification run)."""
    cd = rite_cooldowns(w, F)
    return (w.s.read().treasury, tuple(cd.get(k, 0) for k in RITES),
            tuple(sorted((p["province"], p["picked"] or "") for p in provinces(w, F))))


# ------------------------------------------------------------------ commandments (UI)
def _stack_button(ui: UI, name: str):
    st = ui.first("stack_incentives")
    return ui.first(name, under=st) if st else None


def _on_screen(ui: UI, ptr) -> bool:
    if not ptr:
        return False
    x, y = ui.comp(ptr).center
    return 0 <= x < 1920 and 0 <= y < 1080


def pick_commandment(ui: UI, w: World, F: int, province: str, key: str) -> str | None:
    """Pick `key` for `province`; confirmed when memory shows it picked. None when done, else what went wrong."""
    from .build import _scroll_into_clip
    tab = ui.cached("tab_regions", under="bar_small_top")
    if tab is not None and not (ui.state(tab) or "").startswith("selected"):
        click(ui, tab)
    row = wait.wait_until(lambda: ui.first(f"row_entry_{province}"), 2.0, f"row_entry_{province} listed", must=False)
    if row is None or not _scroll_into_clip(ui, row, "Provinces list"):
        return "province not in the Provinces list"
    click(ui, row)                                      # selects the province: the HUD's commandment slot follows it
    current = next((p["picked"] for p in provinces(w, F) if p["province"] == province), None)
    slot_name = f"button_{current}" if current else "button_default"
    slot = wait.wait_until(lambda: (lambda b: b if _on_screen(ui, b) else None)(_stack_button(ui, slot_name)), 3.0,
                           f"{province}'s commandment slot", must=False)
    if slot is None:
        return "its commandment slot did not show"
    sx, sy = ui.comp(slot).center
    move_to(sx, sy)                                     # hovering the slot opens the list
    target = wait.wait_until(lambda: (lambda b: b if _on_screen(ui, b) else None)(_stack_button(ui, f"button_{key}")),
                             1.5, "commandment list open", must=False)
    if target is None:
        click(ui, slot)
        target = wait.wait_until(lambda: (lambda b: b if _on_screen(ui, b) else None)(
            _stack_button(ui, f"button_{key}")), 2.0, "commandment list open", must=False)
    if target is None:
        return "the commandment list did not open"
    wait.stable_rect(ui, target, n=3, timeout=2.0, must=False, what="commandment list still")
    tx, ty = ui.comp(target).center
    move_path([(sx + (tx - sx) * f // 4, sy + (ty - sy) * f // 4) for f in (1, 2, 3)] + [(tx, ty)])
    from bot.sensor import commands             # paced by the game: the command, then the pick in memory
    st, _v = commands.act(w.pm, lambda: click(ui, target) and None,
                          lambda: any(p["province"] == province and p["picked"] == key for p in provinces(w, F)))
    return None if st == "done" else f"the pick did not register ({commands.WHY.get(st) or st})"


# ------------------------------------------------------------------ rite (UI)
def _rite_card(ui: UI, panel: int, key: str):
    """The rite's card: CcoCampaignRitual<n><key>, n a per-faction number (51 for Clan Skryre, 107 for Clan Scruten,
    2026-10-17)."""
    pat = re.compile(r"CcoCampaignRitual\d+" + re.escape(key) + "$")
    return next((c for c, ids in ui.walk(panel) if pat.match(ids[-1])), None)


def answer_verminlord_dilemma(ui: UI, timeout: float = 3.0) -> str:
    """The Verminlord version's dilemma -> A Verminlord Warpseer. -> "taken", "none" (no such dilemma came) or
    "failed" (it is still open: the player has to choose).
    2026-10-17, seen on every cast: the dilemma shows up ~50 ms after Perform Rite while it is still animating in and
    the "Rite Performed!" banner (root rite_performed) plays over it; a click then lands nowhere. So: wait for the
    banner to go, for the Warpseer button to keep the same rectangle for several frames, click with the hover
    confirmed, and check the dilemma really closed; again if not."""
    def choice():
        ev = ui.root_child("events")
        if not ev:
            return None
        card = next((c for c, ids in ui.walk(ev) if ids[-1].endswith(VERMINLORD_DILEMMA + WARPSEER_CHOICE)), None)
        btn = ui.first("choice_button", under=card) if card else None
        return (ev, btn) if btn else None
    if not wait.wait_until(choice, timeout, "Verminlord dilemma", must=False):
        return "none"
    wait.wait_until(lambda: not ui.root_child("rite_performed"), 5.0, "Rite Performed! banner gone", must=False)
    for _ in range(4):
        hit = choice()
        if not hit:
            return "taken"                              # (closed by the previous click)
        ev, btn = hit
        wait.stable_rect(ui, btn, n=6, timeout=2.5, must=False, what="Warpseer choice still")
        click(ui, btn)
        if wait.gone(ui, ev, timeout=1.5, must=False, what="Verminlord dilemma closed"):
            return "taken"
    return "taken" if not choice() else "failed"


def cast_rite(ui: UI, w: World, F: int) -> str:
    cd = rite_cooldowns(w, F)
    have = [k for k in RITES if k in cd]
    if not have:
        return "the Dominating Scheme is not in your rites"
    if any(cd[k] > 0 for k in have):
        return f"Dominating Scheme on cooldown ({max(cd[k] for k in have)} turns)"
    why = rite_waits(provinces(w, F), cd)              # memory first: no panel opened for a rite still locked
    if why:
        return why
    b = ui.cached("button_rituals", under="hud_campaign") or ui.first("button_rituals")
    if b is None:
        return "Rites button not found"
    click(ui, b)
    panel = wait.wait_until(lambda: ui.root_child("rituals_panel"), 3.0, "Rites panel", must=False)
    if not panel:
        return "the Rites panel did not open"
    try:
        card = wait.wait_until(lambda: next((c for k in RITES for c in [_rite_card(ui, panel, k)] if c), None), 2.0,
                               "Dominating Scheme card", must=False)
        if card is None:
            return "the Dominating Scheme is not shown in the Rites panel"
        key = next(k for k in RITES if _rite_card(ui, panel, k) == card)
        cost_c = ui.first("dy_gold_cost", under=card)
        card_cost = int(re.sub(r"\D", "", ui.text(cost_c) or "") or 0) if cost_c else 0
        mem_cost = rite_cost(w, F, key)                 # memory first (2026-10-19); the card only as fallback
        cost = mem_cost if mem_cost is not None else card_cost
        gold = w.s.read().treasury or 0
        if cost and gold < cost:
            return f"Dominating Scheme needs {cost} gold (have {gold})"
        btn = ui.first("button_perform", under=card)
        req = ui.first("dy_unlock_requirements", under=card)
        req_text = re.sub(r"\[\[[^\]]*\]\]", "", ui.text(req) or "").strip().replace("\n", " ") if req else ""
        _observe(w, F, key, card_cost=card_cost, memory_cost=mem_cost, button=(ui.state(btn) if btn else None),
                 requirements=req_text, gold=gold, when="card read")
        if btn is None or (ui.state(btn) or "") != "active":
            return f"Dominating Scheme cannot be cast: {req_text or 'requirements not met'}"
        from bot.sensor import commands         # paced by the game: the command, then the cooldown in memory
        st, _v = commands.act(w.pm, lambda: click(ui, btn) and None, lambda: rite_cooldowns(w, F).get(key, 0) > 0)
        if st != "done":
            return f"Perform Rite did not register ({commands.WHY.get(st) or st})"
        spent = gold - (w.s.read().treasury or 0)
        _observe(w, F, key, card_cost=card_cost, memory_cost=mem_cost, spent=spent,
                 cooldown=rite_cooldowns(w, F).get(key), when="cast")
        out = f"cast the Dominating Scheme ({spent} gold)"
        if key == RITE_VERMINLORD:
            how = answer_verminlord_dilemma(ui)
            out += {"taken": "; Verminlord Warpseer chosen",
                    "none": "; no Verminlord choice appeared",
                    "failed": "; the Verminlord choice is still open: choose the Warpseer yourself"}[how]
        return out
    finally:
        ok = ui.root_child("rituals_panel")
        if ok:
            close = ui.first("button_ok", under=ok)
            if close:
                click(ui, close)
                wait.gone(ui, ok, timeout=2.0, must=False, what="Rites panel closed")


# ------------------------------------------------------------------ the step
def run(log=print) -> str:
    w = World()
    F = find_player_faction(w)
    if F is None:
        return "player faction not found"
    ui = UI(w.s)
    ui.find_root()
    out = []
    with game_focus():
        # 1. commandments (the rite's requirement comes first)
        provs = provinces(w, F)
        want = wanted_commandments(provs, rite_cooldowns(w, F))
        picked = {p["province"]: p["picked"] for p in provs}
        changed = False
        for province, key in want.items():
            if picked.get(province) == key:
                continue
            problem = pick_commandment(ui, w, F, province, key)
            name = gd.loc().get(f"provincial_initiative_records_localised_name_{key}", key)
            place = gd.loc().get(f"provinces_onscreen_{province}", province)
            out.append(f"{place}: {name}" if problem is None else f"{place}: {name} not picked ({problem})")
            changed = True
        if changed:
            from .army_builder import clear
            clear(ui)
        # 2. the rite, before buildings and the army builder spend the gold
        out.append(cast_rite(ui, w, F))
    return "; ".join(out)
