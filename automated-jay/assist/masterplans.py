"""Thanquol's Masterplans (player request, 2026-10-18): Steal-Take plans and the Clan Scruten Secrets shop.

Every free Underling is sent on a Steal-Take; each running Steal-Take is completed when waiting another turn is worth
less than completing now; Secrets are bought in strategy/masterplans.json "shop" "order". Kill-Stab plans are the
player's: the step never starts, completes or abandons one. It runs at Build & End Turn only, so an Underling the
player sends on a Kill-Stab during the turn is never taken first.
Single player and multiplayer are the same to it: unlocks (story in single player, turns in multiplayer) are never
assumed; the panel shows what is open each time (HUD button, locked/free/resting Underlings, inactive shop lines).

When to complete a Steal-Take (the game's numbers, 9.0.4):
  - At maximum Alarm (4, campaign variable chaotic_plans_alarm_plan_fail_threshold) the plan pays 25% of its loot
    (chaotic_plans_failed_economic_plan_rewards_pct = 2500), or, if abandoned then, all of it through a mission to
    conquer the region within 10 turns.
  - Each turn there is a Risk% chance of one Complication, which raises Alarm by 0, 1 or 2; from Alarm a, the chance
    that it reaches 4 is q(a): 0 below 2, about 0.15 at 2, about 0.99 at 3 (the Steal-Take Complication pools).
  - With V the loot so far and G the loot the next turn adds on average, waiting is worth
    (1 - R q)(V + G) + R q 0.25 V against V for completing: wait while R q < G / (G + 0.75 V). Risk only rises and
    the pot only grows, so this one-turn test is the optimal rule.
  Loot is weighed in Warpstone (gold divided by steal_take.gold_per_warpstone, food not counted). G is read from the
  board: the draws next turn times the sum, over the cards still in the bag, of each card's draw chance times its
  value (game tables; a card worth a share of the region's income is valued with the income the drawn cards show).

UI (9.0.4, found 2026-10-18 with a live plan): panel dlc29_skv_chaotic_plans; main page schemers_list (one card per
Underling, a locked one has a "locked" child, a busy one a holder/plan_type child) with new_plan_button (free) or
view_plan_button (busy) under it for the selected card; active_plans_list holds
CcoCampaignChaoticPlan<plan key><faction><region> per running plan (a click opens its board). Setup:
economy_plan_button, then a settlement's name label on the map (3d_ui_parent label_settlement:<region>) is the target
(dy_settlement_target shows it), establish_plan_button starts it (50 Warpstone). Board: red_token_counter "60%" (Risk),
bar_fill_elite (Alarm: its height over the 197 px bar, hidden at 0), treasury_counter / warpstone_counter dy_value
(loot), token_draw_counter (draws next turn), bag chips CcoChaoticPlanTokenRecord<token> with dy_chance,
trigger_plan_button (Complete) and abandon_button. Shop: shop_button_toggle; tabs
CcoChaoticPlanShopCategoryRecordwh3_dlc29_skv_shop_<tab>; lines CcoCampaignChaoticPlanShopObjectChain<chain> (state
"inactive" while locked); the selected line's next level is described on the right, with upgrades_list naming the
levels after it, and button_purchase buys it. button_close goes back one page (from the main page it closes the panel).
"""
from __future__ import annotations
import json
import re
import time
from collections import defaultdict
from datetime import datetime
from functools import lru_cache

from bot import config

SCRUTEN = "wh3_dlc29_skv_clan_scruten"
PANEL = "dlc29_skv_chaotic_plans"
HUD_BUTTON = "button_chaotic_plans"
ECONOMIC = "wh3_dlc29_economic_plan"
PLAN_ID = "CcoCampaignChaoticPlan"
ALARM_BAR_PX = 197.0          # bar_fill_elite's full height (dlc29_skv_chaotic_plans_economy_board.twui.xml)
ALARM_MAX = 4
STRATEGY = config.STRATEGY_DIR / "masterplans.json"
LOG = config.RUNS_DIR / "masterplans.jsonl"


def settings() -> dict:
    try:
        return json.load(open(STRATEGY, encoding="utf-8"))
    except Exception:
        return {}


# ------------------------------------------------------------------ game data: card values, shop chains
@lru_cache(maxsize=1)
def card_values() -> dict[str, dict[str, float]]:
    """token -> {"gold", "warpstone", "gold_pct", "warpstone_pct"}: flat loot, and loot as % of the region's income."""
    from . import gamedata as gd
    pays = defaultdict(list)
    for r in gd._load("chaotic_plan_tokens_to_payloads_junctions_tables"):
        pays[r["token"]].append(r["campaign_payload"])
    basic = defaultdict(list)
    for r in gd._load("campaign_payload_basic_value_components_tables"):
        basic[r["payload"]].append((r["component_type"], r["value"]))
    trans = {r["payload"]: r["resource_transaction"] for r in gd._load("campaign_payload_resource_transactions_tables")}
    costs = defaultdict(list)
    for r in gd._load("resource_cost_pooled_resource_junctions_tables"):
        costs[r["resource_cost"]].append((r["pooled_resource_factor"], r["amount"]))
    out = {}
    for tok, ps in pays.items():
        v = {"gold": 0.0, "warpstone": 0.0, "gold_pct": 0.0, "warpstone_pct": 0.0}
        for p in ps:
            for kind, value in basic.get(p, ()):
                if kind == "treasury_change":
                    v["gold"] += value
                elif kind == "chaotic_plan_modify_treasury_reward_gdp_percentage":
                    v["gold_pct"] += value / 100.0
                elif kind == "chaotic_plan_modify_warpstone_reward_gdp_percentage":
                    v["warpstone_pct"] += value / 100.0
            for factor, amount in costs.get(trans.get(p, ""), ()):
                if factor == "wh3_dlc29_warpstone_factor_plan":
                    v["warpstone"] += amount
        if any(v.values()):
            out[tok] = v
    return out


@lru_cache(maxsize=1)
def shop_chains() -> dict[str, list[str]]:
    """shop chain -> its levels' tokens, in order."""
    from . import gamedata as gd
    objs = {r["key"]: r["token"] for r in gd._load("chaotic_plan_shop_category_objects_tables")}
    ch = defaultdict(list)
    for r in gd._load("chaotic_plan_shop_category_chain_to_object_junctions_tables"):
        if r["category_object"] in objs:
            ch[r["category_chain"]].append((r["order"], objs[r["category_object"]]))
    return {c: [t for _o, t in sorted(v)] for c, v in ch.items()}


@lru_cache(maxsize=1)
def shop_tabs() -> dict[str, str]:
    """shop chain -> its category (tab) key."""
    from . import gamedata as gd
    return {r["chain"]: r["category"] for r in gd._load("chaotic_plan_shop_category_to_object_chain_junctions_tables")}


# ------------------------------------------------------------------ the completion rule (pure)
INCOME_RE = re.compile(r"(\d+(?:\.\d+)?)%+ of the region's income.*?\(\+?(-?\d+)\)", re.S)


def region_income(effect_texts: list[str]) -> float | None:
    """The region's income from a drawn card's effect line ("10% of the region's income ... (+16)" -> 160)."""
    for t in effect_texts:
        m = INCOME_RE.search(t or "")
        if m and float(m.group(1)) > 0:
            return float(m.group(2)) * 100.0 / float(m.group(1))
    return None


def card_worth(token: str, income: float | None, gold_per_warpstone: float) -> float | None:
    v = card_values().get(token)
    if v is None:
        return None
    if (v["gold_pct"] or v["warpstone_pct"]) and income is None:
        return None
    inc = income or 0.0
    gold = v["gold"] + v["gold_pct"] / 100.0 * inc
    ws = v["warpstone"] + v["warpstone_pct"] / 100.0 * inc
    return ws + gold / gold_per_warpstone


def expected_gain(board: dict, cfg: dict) -> float:
    """G: the loot the next turn adds on average, in Warpstone."""
    gpw = cfg.get("gold_per_warpstone", 10)
    income = region_income(board.get("effects", []))
    pot = board["warpstone"] + board["gold"] / gpw
    per_card_avg = pot / board["drawn"] if board.get("drawn") else 0.0
    g = 0.0
    for token, chance in board.get("bag", []):
        w = card_worth(token, income, gpw)
        g += chance / 100.0 * (per_card_avg if w is None else w)
    return board.get("draws", 2) * g


def decide(board: dict, cfg: dict) -> tuple[str, str]:
    """("wait" | "complete" | "abandon", why) for a Steal-Take board."""
    if not board["can_complete"]:
        return "wait", "not ready to complete yet"
    gpw = cfg.get("gold_per_warpstone", 10)
    pay = cfg.get("max_alarm_pay", 0.25)
    if board["alarm"] >= ALARM_MAX:
        how = cfg.get("at_max_alarm", "complete")
        return ("abandon" if how == "abandon" else "complete"), "Alarm is at its maximum"
    V = board["warpstone"] + board["gold"] / gpw
    G = expected_gain(board, cfg)
    qs = cfg.get("q_by_alarm", [0.0, 0.0, 0.15, 0.99])
    q = qs[min(board["alarm"], len(qs) - 1)]
    rq = board["risk"] / 100.0 * q
    if V <= 0:
        return "wait", "nothing gathered yet"
    limit = G / (G + (1 - pay) * V) if G > 0 else 0.0
    why = f"Risk {board['risk']:.0f}% x q {q:.2f} = {rq:.2f} vs {limit:.2f} (loot {V:.0f}, next turn +{G:.0f})"
    return ("wait" if rq < limit else "complete"), why


# ------------------------------------------------------------------ UI helpers
def _txt(ui, c) -> str:
    return re.sub(r"\[\[[^\]]*\]\]", "", ui.text(c) or "").strip() if c else ""


def _num(s: str) -> float:
    m = re.search(r"-?\d+(?:\.\d+)?", (s or "").replace(",", ""))
    return float(m.group(0)) if m else 0.0


def _under(ui, cid: str, under) -> int | None:
    return ui.first(cid, under=under)


def _main_page(ui) -> bool:
    return bool(ui.root_child(PANEL) and _under(ui, "schemers_list", PANEL))


def open_main(ui) -> bool:
    """The panel open on its main page (Underlings, active plans)."""
    from tools import wait
    from tools.ui import click
    for _ in range(5):
        if not ui.root_child(PANEL):
            b = ui.cached(HUD_BUTTON) or ui.first(HUD_BUTTON)
            if b is None or not (ui.state(b) or "").startswith("active"):
                return False
            click(ui, b)
            if not wait.wait_until(lambda: ui.root_child(PANEL), 4.0, "Masterplans panel", must=False):
                return False
            wait.wait_until(lambda: _under(ui, "button_close", PANEL), 3.0, "Masterplans panel shown", must=False)
        if wait.wait_until(lambda: _main_page(ui), 1.5, "Masterplans main page", must=False):
            # the active plans fill in a moment after the page shows
            wait.stable(lambda: len(active_plans(ui)), n=4, timeout=2.0, what="active plans listed", ui=ui, must=False)
            time.sleep(0.3)
            return True
        x = _under(ui, "button_close", PANEL)          # a board, the setup or the shop: one page back
        if x is None:
            return False
        click(ui, x)
        time.sleep(0.6)
    return _main_page(ui)


def close_panel(ui) -> None:
    from tools import wait
    from tools.ui import click
    for _ in range(5):
        if not ui.root_child(PANEL):
            return
        x = _under(ui, "button_close", PANEL)
        if x is None:
            return
        click(ui, x)
        wait.wait_until(lambda: not ui.root_child(PANEL) or _main_page(ui), 2.0, "page back", must=False)
    wait.wait_until(lambda: not ui.root_child(PANEL), 3.0, "Masterplans panel closed", must=False)


def warpstone(ui) -> int:
    c = _under(ui, "warpstone_effect", PANEL)
    return int(_num(_txt(ui, c))) if c else 0


def active_plans(ui) -> list[tuple[int, str, str]]:
    """(component, plan key, region key) of every running plan."""
    lst = _under(ui, "active_plans_list", PANEL)
    out = []
    for c in ui.children(lst) if lst else []:
        i = ui.id(c) or ""
        if not i.startswith(PLAN_ID):
            continue
        rest = i[len(PLAN_ID):]
        plan = rest.split(SCRUTEN)[0]
        region = rest.split(SCRUTEN)[-1] if SCRUTEN in rest else ""
        out.append((c, plan, region))
    return out


def read_board(ui) -> dict | None:
    board = _under(ui, "chaotic_plans_plan_board", PANEL)
    if board is None:
        return None
    risk = _num(_txt(ui, _under(ui, "red_token_counter", board)))
    fill = _under(ui, "bar_fill_elite", board)
    alarm = int(round(ui.comp(fill).h / ALARM_BAR_PX * ALARM_MAX)) if fill and ui.visible(fill) else 0
    tc, wc = _under(ui, "treasury_counter", board), _under(ui, "warpstone_counter", board)
    gold = _num(_txt(ui, ui.child(tc, "dy_value"))) if tc else 0.0
    ws = _num(_txt(ui, ui.child(wc, "dy_value"))) if wc else 0.0
    draws = int(_num(_txt(ui, _under(ui, "token_draw_counter", board))) or 2)
    bag = []
    chips = _under(ui, "bag_content_subpanel", board)
    for c, i, _raw in ui.nodes(chips) if chips else ():
        if i.startswith("CcoChaoticPlanTokenRecord"):
            ch = _under(ui, "dy_chance", c)
            bag.append((i[len("CcoChaoticPlanTokenRecord"):], _num(_txt(ui, ch))))
    drawn = sum(1 for _c, i, _r in ui.nodes(_under(ui, "chips_holder", board) or board)
                if i.startswith("CcoCampaignChaoticPlanToken"))
    effects = []
    el = _under(ui, "chip_effects_list", board)
    for c, i, _raw in ui.nodes(el) if el else ():
        if i.startswith("CcoCampaignPayloadInfoEntry"):
            effects.append(_txt(ui, c))
    trig = _under(ui, "trigger_plan_button", board)
    return {"risk": risk, "alarm": alarm, "gold": gold, "warpstone": ws, "draws": draws, "bag": bag, "drawn": drawn,
            "effects": effects, "can_complete": bool(trig) and (ui.state(trig) or "").startswith("active")}


def _log(entry: dict) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), **entry}) + "\n")
    except OSError:
        pass


def _confirm(ui) -> None:
    """Accept a confirmation the game may show (a prompt with a tick)."""
    from tools import wait
    from tools.ui import click
    box = wait.wait_until(lambda: ui.root_child("dialogue_box"), 1.5, "confirmation", must=False)
    if not box:
        return
    for b in ("button_tick", "button_accept", "button_ok"):
        t = ui.first(b, under="dialogue_box")
        if t is not None:
            click(ui, t)
            wait.wait_until(lambda: not ui.root_child("dialogue_box"), 2.0, "confirmation closed", must=False)
            return


# ------------------------------------------------------------------ 1. running Steal-Takes
def manage_plans(ui, cfg: dict, turn) -> list[str]:
    from tools import wait
    from tools.ui import click
    from . import gamedata as gd
    out = []
    for _c, plan, region in [p for p in active_plans(ui) if p[1] == ECONOMIC]:
        place = gd.place_name(region)
        item = next((c for c, p, r in active_plans(ui) if p == plan and r == region), None)
        if item is None:
            continue
        click(ui, item)
        if not wait.wait_until(lambda: read_board(ui), 3.0, f"{place} board", must=False):
            out.append(f"{place}: its plan did not open")
            open_main(ui)
            continue
        time.sleep(0.4)
        b = read_board(ui)
        act, why = decide(b, cfg)
        _log({"turn": turn, "region": region, "board": b, "decision": act, "why": why})
        if act == "wait":
            out.append(f"Steal-Take {place}: wait ({why})")
        else:
            btn = _under(ui, "trigger_plan_button" if act == "complete" else "abandon_button", PANEL)
            before = len(active_plans(ui))
            click(ui, btn)
            _confirm(ui)
            gone = wait.wait_until(lambda: len(active_plans(ui)) < before, 6.0, "plan finished", must=False)
            _confirm(ui)
            loot = f"{b['gold']:.0f} gold, {b['warpstone']:.0f} Warpstone"
            out.append(f"Steal-Take {place}: {'completed' if act == 'complete' else 'abandoned'} ({loot}; {why})"
                       + ("" if gone else " - NOT confirmed, check the plan"))
        open_main(ui)
    return out


# ------------------------------------------------------------------ 2. new Steal-Takes
def _region_objects(w, F: int, limit: int = 1500) -> dict[str, int]:
    """Region key -> region object for the regions around ours (walked through the neighbour graph)."""
    seen: dict[str, int] = {}
    front = list(w.faction_regions(F))
    for r in front:
        k = w.region_key(r)
        if k:
            seen[k] = r
    while front and len(seen) < limit:
        r = front.pop(0)
        for n in w.neighbours(r):
            k = w.region_key(n)
            if k and k not in seen:
                seen[k] = n
                front.append(n)
    return seen


def near_provinces(province_of: dict[str, str], neighbours_of: dict[str, list[str]], own: set[str]) -> set[str]:
    """Our provinces (any region of them held) and every province bordering one of them (a region of it is a
    neighbour of a region in ours)."""
    ours = {province_of.get(k, k) for k in own}
    near = set(ours)
    for k, ns in neighbours_of.items():
        if province_of.get(k, k) in ours:
            near.update(province_of.get(n, n) for n in ns if n and n != "?")
    return near


def _near_provinces(w, F: int) -> set[str]:
    from bot.sensor.world import snapshot
    snap = snapshot(w)
    if snap is None:
        return set()
    return near_provinces(snap.province_of, snap.neighbours_of, set(snap.own))


def _targets(ui, w, F: int, busy: set[str], cfg: dict, avoid_rects) -> list[tuple[float, str, int]]:
    """(score, region, label) of every foreign settlement whose label is on screen, best first: higher settlement
    level first (loot is a share of the region's income), major settlements before minor ones, and (by default)
    factions we are not at war with first. Settlements on a Masterplans cooldown or already targeted are left out,
    and (skip_near_provinces) so is every settlement in one of our provinces or a province bordering one."""
    regs = _region_objects(w, F)
    near = _near_provinces(w, F) if cfg.get("skip_near_provinces", True) else set()
    if near:
        from bot.sensor.world import region_provinces
        prov = region_provinces()[0]
    wars = set(w.wars(F))
    parent = ui.root_child("3d_ui_parent")
    out = []
    for c in ui.children(parent) if parent else []:
        i = ui.id(c) or ""
        if not i.startswith("label_settlement:") or not ui.visible(c):
            continue
        region = i.split(":", 1)[1]
        r = regs.get(region)
        if r is None or region in busy:
            continue
        if near and prov.get(region, region) in near:
            continue                                           # our province or one bordering ours
        owner = w.region_owner(r)
        if not owner or owner == F:
            continue
        ids = {ii: x for x, ii, _r in ui.nodes(c)}           # visible components only
        if "dlc29_chaotic_plans_cooldown_counter" in ids:
            continue                                           # on high alert after a recent Masterplan
        name = ids.get("dy_name")
        if name is None:
            continue
        k = ui.comp(name)
        if not (0 < k.x and k.x + k.w < 1920 and 60 < k.y and k.y + k.h < 1000):
            continue
        cx, cy = k.x + k.w / 2, k.y + k.h / 2
        if any(a.x <= cx <= a.x + a.w and a.y <= cy <= a.y + a.h for a in avoid_rects):
            continue
        slots = w.slots(r)
        main = slots[0] if slots else None
        level = (main.level or 0) if main else 0
        major = bool(main and main.building and "major" in main.building)
        score = level * 10 + (5 if major else 0)
        if cfg.get("prefer_not_at_war", True) and owner not in wars:
            score += 100
        out.append((score, region, name))
    return sorted(out, key=lambda t: -t[0])


def start_plans(ui, cfg: dict, dry_run: bool = False) -> list[str]:
    """dry_run: pick the Underling and the target, then back out without starting (for testing)."""
    from tools import wait
    from tools.ui import click, click_at, move_to
    from bot.sensor.world import World, find_player_faction
    from . import gamedata as gd
    w = World(ui.s)
    F = find_player_faction(w)
    out = []
    lst = _under(ui, "schemers_list", PANEL)
    cards = list(ui.children(lst)) if lst else []
    for idx in range(len(cards)):
        if not open_main(ui):
            break
        lst = _under(ui, "schemers_list", PANEL)
        cards = list(ui.children(lst)) if lst else []
        if idx >= len(cards):
            break
        card = cards[idx]
        if ui.child(card, "locked") is not None and ui.visible(ui.child(card, "locked")):
            continue
        hold = ui.child(card, "holder")
        if hold is not None and ui.child(hold, "plan_type", visible_only=True) is not None:
            continue                                           # on a plan
        click(ui, card)
        time.sleep(0.5)
        who = _txt(ui, _under(ui, "dy_name", "schemer_details")) or f"Underling {idx + 1}"
        new = wait.wait_until(lambda: _under(ui, "new_plan_button", PANEL), 1.5, "New Masterplan", must=False)
        if new is None or not (ui.state(new) or "").startswith("active"):
            continue                                           # busy, or resting after a plan
        if warpstone(ui) < 50:
            out.append(f"{who}: no Steal-Take started (needs 50 Warpstone)")
            break
        click(ui, new)
        eco = wait.wait_until(lambda: _under(ui, "economy_plan_button", PANEL), 3.0, "plan types", must=False)
        if eco is None or (ui.state(eco) or "").startswith("inactive"):
            out.append(f"{who}: Steal-Take is not available")
            continue
        click(ui, eco)
        time.sleep(0.8)
        avoid = [ui.comp(x) for x in (_under(ui, n, PANEL) for n in
                                      ("plan_type_holder", "target_holder", "bottom_bar", "lord_info")) if x]
        busy = {r for _c, _p, r in active_plans(ui)}
        started = False
        for score, region, label in _targets(ui, w, F, busy, cfg, avoid)[:6]:
            k = ui.comp(label)
            click_at(int(k.x + k.w / 2), int(k.y + k.h / 2))
            place = gd.place_name(region)
            shown = wait.wait_until(lambda: place in _txt(ui, _under(ui, "dy_settlement_target", PANEL)), 1.5,
                                    f"{place} targeted", must=False)
            est = _under(ui, "establish_plan_button", PANEL)
            if not shown or est is None or not (ui.state(est) or "").startswith("active"):
                continue
            if dry_run:
                out.append(f"{who}: would start a Steal-Take on {place} (score {score})")
                started = True
                break
            before = warpstone(ui)
            click(ui, est)
            _confirm(ui)
            if wait.wait_until(lambda: _under(ui, "chaotic_plans_plan_board", PANEL) or warpstone(ui) < before, 4.0,
                               "plan started", must=False):
                out.append(f"{who}: Steal-Take started on {place}")
                _log({"started": region, "underling": who})
                started = True
            break
        if not started:
            out.append(f"{who}: no Steal-Take target found on screen")
        move_to(960, 1070)
    return out


# ------------------------------------------------------------------ 3. the Secrets shop
def _open_shop(ui) -> bool:
    from tools import wait
    from tools.ui import click
    if _under(ui, "dlc29_skv_token_shop", PANEL):
        return True
    if not open_main(ui):
        return False
    b = _under(ui, "shop_button_toggle", PANEL)
    if b is None:
        return False
    click(ui, b)
    return bool(wait.wait_until(lambda: _under(ui, "dlc29_skv_token_shop", PANEL), 3.0, "Secrets shop", must=False))


def _line_status(ui, chain: str) -> tuple[int | None, int | None]:
    """(levels owned, cost of the next) of the selected shop line, from the description on the right: the next level
    is described, upgrades_list names the levels after it. (None, None) when it cannot be read."""
    levels = shop_chains().get(chain, [])
    info = _under(ui, "info_container", PANEL)
    if not levels or info is None:
        return None, None
    after = [i for _c, i, _r in ui.nodes(_under(ui, "upgrades_list", info) or info)
             if i.startswith("CcoChaoticPlanTokenRecord")] if _under(ui, "upgrades_list", info) else []
    btn = _under(ui, "button_purchase", info)
    cost = _num(_txt(ui, _under(ui, "dy_text", btn))) if btn else 0
    owned = len(levels) - 1 - len(after)
    if btn is None or not ui.visible(btn):
        return len(levels), None                     # nothing left to buy
    return max(0, owned), int(cost) if cost else None


def buy_secrets(ui, cfg: dict) -> list[str]:
    from tools import wait
    from tools.ui import click
    from .build import _scroll_into_clip
    keep = int(cfg.get("keep_warpstone", 50))
    out = []
    if not _open_shop(ui):
        return ["the Secrets shop did not open"]
    for entry in cfg.get("order", []):
        chain, want = entry["chain"], int(entry.get("levels", 1))
        name = entry.get("_what", chain).split(" / ")[0]
        tab_key = shop_tabs().get(chain)
        if tab_key is None:
            continue
        for _ in range(want):                        # one level per round
            tab = _under(ui, f"CcoChaoticPlanShopCategoryRecord{tab_key}", PANEL)
            if tab is None or (ui.state(tab) or "").startswith("inactive"):
                break                                # that Underling is not unlocked
            if not (ui.state(tab) or "").startswith("selected"):
                click(ui, tab)
                wait.wait_until(lambda: (ui.state(tab) or "").startswith("selected"), 2.0, "shop tab", must=False)
            line = wait.wait_until(lambda: _under(ui, f"CcoCampaignChaoticPlanShopObjectChain{chain}", PANEL), 2.0,
                                   f"{chain} listed", must=False)
            if line is None or (ui.state(line) or "").startswith("inactive"):
                break                                # locked: too few purchases in that shop yet
            if not _scroll_into_clip(ui, line, "Secrets list"):
                break
            if not (ui.state(line) or "").startswith("selected"):
                click(ui, ui.child(line, "button_wh3") or line)
                wait.wait_until(lambda: (ui.state(line) or "").startswith("selected"), 2.0, "line selected", must=False)
                time.sleep(0.3)
            owned, cost = _line_status(ui, chain)
            if owned is None or owned >= want:
                break
            names = entry.get("_what", chain).split(" / ")
            level = names[owned] if owned < len(names) else name
            have = warpstone(ui)
            if cost is None or have - cost < keep:
                out.append(f"saving for {level} ({cost} Warpstone, have {have}, keeping {keep})")
                return out                           # strict order: nothing below is bought before it
            click(ui, _under(ui, "button_purchase", PANEL))
            _confirm(ui)
            if not wait.wait_until(lambda: warpstone(ui) <= have - cost, 3.0, "purchase registered", must=False):
                out.append(f"{level}: the purchase did not register")
                return out
            out.append(f"bought {level} ({cost} Warpstone)")
            _log({"bought": chain, "level": owned + 1, "cost": cost})
            time.sleep(0.4)
    if not out:
        out.append("nothing on the list left to buy")
    return out


# ------------------------------------------------------------------ the step
def run(log=print, verify: bool = False) -> str:
    from bot.focus import game_focus
    from bot.sensor.ui import UI
    from bot.sensor.world import World, find_player_faction
    w = World()
    F = find_player_faction(w)
    if F is None:
        return "player faction not found"
    if w.faction_name(F) != SCRUTEN:
        return "no Masterplans (Thanquol's Clan Scruten only)"
    if verify:
        return "nothing to verify"                   # every action is confirmed on screen as it happens
    cfg = settings()
    st, shop = cfg.get("steal_take", {}), cfg.get("shop", {})
    if not st.get("enabled", True) and not shop.get("enabled", True):
        return "off (strategy/masterplans.json)"
    ui = UI(w.s)
    ui.find_root()
    b = ui.cached(HUD_BUTTON) or ui.first(HUD_BUTTON)
    if b is None or not (ui.state(b) or "").startswith("active"):
        return "Masterplans are not unlocked yet"
    turn = w.s.read().turn
    out = []
    with game_focus():
        try:
            if not open_main(ui):
                return "the Masterplans panel did not open"
            if st.get("enabled", True):
                out += manage_plans(ui, st, turn)
                out += start_plans(ui, st)
            if shop.get("enabled", True):
                out += buy_secrets(ui, shop)
        finally:
            close_panel(ui)
    return "; ".join(out) or "nothing to do"
