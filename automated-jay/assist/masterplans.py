"""Thanquol's Masterplans (player request, 2026-10-18): Steal-Take plans and the Clan Scruten Secrets shop.

Every free Underling is sent on a Steal-Take; each running Steal-Take is completed when waiting another turn is worth
less than completing now; Secrets are bought in strategy/masterplans.json "shop" "order". Kill-Stab plans are the
player's: the step never starts, completes or abandons one. It runs at Build & End Turn only, so an Underling the
player sends on a Kill-Stab during the turn is never taken first.

Everything it decides on is read from memory (bot/sensor/masterplans.py; player rule 2026-10-18, CLAUDE.md): the
plans and their Risk, Alarm, loot, card pool and draws, the region's income, which Underlings are unlocked, free,
resting or besieging, settlement cooldowns, which plan types are unlocked, Warpstone and the Secrets owned. Single
player and multiplayer are the same to it: unlocks (story in single player, turns in multiplayer) are read, never
assumed. The panel is opened only when there is something to click, and the UI tree only finds what to click and
confirms the click took; each action's result is confirmed in memory (plan gone, plan started, Warpstone spent).

When to complete a Steal-Take (the game's numbers, 9.0.4):
  - At maximum Alarm (4, campaign variable chaotic_plans_alarm_plan_fail_threshold) the plan pays 25% of its loot
    (chaotic_plans_failed_economic_plan_rewards_pct = 2500), or, if abandoned then, all of it through a mission to
    conquer the region within 10 turns.
  - Each turn there is a Risk% chance of one Complication, which raises Alarm by 0, 1 or 2; from Alarm a, the chance
    that it reaches 4 is q(a): 0 below 2, about 0.15 at 2, about 0.99 at 3 (the Steal-Take Complication pools).
  - With V the loot so far and G the loot the next turn adds on average, waiting is worth
    (1 - R q)(V + G) + R q 0.25 V against V for completing: wait while R q < G / (G + 0.75 V). Risk only rises and
    the pot only grows, so this one-turn test is the optimal rule.
  Loot is weighed in Warpstone (gold divided by steal_take.gold_per_warpstone, food not counted). G = the draws next
  turn times the sum, over the cards still drawable, of each card's draw chance times its value (game tables; a card
  worth a share of the region's income is valued with the region's income, region:gdp()).

UI, for the clicks only (9.0.4, found 2026-10-18 with a live plan): panel dlc29_skv_chaotic_plans; main page
schemers_list (one card per Underling; the selected one's name in schemer_details dy_name) with new_plan_button
under it; active_plans_list holds CcoCampaignChaoticPlan<plan key><faction><region> per running plan (a click opens
its board). Setup: economy_plan_button, then a settlement's name label on the map (3d_ui_parent
label_settlement:<region>) is the target (dy_settlement_target shows it), establish_plan_button starts it (50
Warpstone). Board: trigger_plan_button (Complete) opens the plan-complete screen
dlc29_skv_chaotic_plans_trigger_animation (loot summary, its own trigger_plan_button completes, cancel_button backs out); abandon_button. Shop: shop_button_toggle; tabs
CcoChaoticPlanShopCategoryRecordwh3_dlc29_skv_shop_<tab>; lines CcoCampaignChaoticPlanShopObjectChain<chain>;
button_purchase buys the selected line's first level, button_upgrade its next ones. button_close goes back one page (from the main page it closes
the panel).
"""
from __future__ import annotations
import json
import re
import struct
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
ALARM_MAX = 4                 # campaign variable chaotic_plans_alarm_plan_fail_threshold (memory gives it per plan)
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
    income = board["income"] if board.get("income") is not None else region_income(board.get("effects", []))
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
    if board["alarm"] >= board.get("alarm_max", ALARM_MAX):
        how = cfg.get("at_max_alarm", "complete")
        return ("abandon" if how == "abandon" else "complete"), "Alarm is at its maximum"
    V = board["warpstone"] + board["gold"] / gpw
    G = expected_gain(board, cfg)
    qs = cfg.get("q_by_alarm", [0.0, 0.0, 0.15, 0.99])
    q = qs[min(board["alarm"], len(qs) - 1)]
    rq = board["risk"] / 100.0 * q
    if V <= 0:
        # nothing to lose by waiting: completing now pays nothing (or costs, when a Complication took more than was
        # gathered: 2026-10-18, Essen at Alarm 3 held 25 gold and -4 Warpstone)
        return "wait", f"the loot so far is worth {V:.1f} Warpstone: nothing to lose by waiting"
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


def page(ui) -> str | None:
    """Which page of the panel shows: None (closed), "trigger" (the plan-complete screen), "shop", "board", "setup",
    "main" or "other". The shop and the
    boards open over the main page, whose Underlings list stays visible under them (2026-10-18: the shop read as the
    main page, so closing took one X for it and the panel stayed open over End Turn)."""
    if not ui.root_child(PANEL):
        return None
    if ui.first("cancel_button", under=TRIGGER):
        return "trigger"
    if _under(ui, "dlc29_skv_token_shop", PANEL):
        return "shop"
    if _under(ui, "chaotic_plans_plan_board", PANEL) or _under(ui, "trigger_plan_button", PANEL):
        return "board"
    if _under(ui, "establish_plan_button", PANEL) or _under(ui, "economy_plan_button", PANEL):
        return "setup"
    return "main" if _under(ui, "schemers_list", PANEL) else "other"


def _main_page(ui) -> bool:
    return page(ui) == "main"


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
        p = wait.wait_until(lambda: page(ui) not in (None, "other") and page(ui), 1.5, "Masterplans page shown",
                            must=False)
        if p == "main":
            # the active plans fill in a moment after the page shows
            wait.stable(lambda: len(active_plans(ui)), n=4, timeout=2.0, what="active plans listed", ui=ui, must=False)
            return True
        # a board, the setup, the shop or the plan-complete screen: one page back, confirmed (2026-10-18: a fixed
        # 1.5 s wait for the main page, then a 0.6 s sleep, showed as pauses)
        x = ui.first("cancel_button", under=TRIGGER) if p == "trigger" else _under(ui, "button_close", PANEL)
        if x is None:
            return False
        click(ui, x)
        wait.wait_until(lambda: page(ui) != p, 2.0, f"back from the {p} page", must=False)
    return _main_page(ui)


def close_panel(ui) -> bool:
    """Close the panel with its X, one click per page, each confirmed: a sub-page (shop, board, setup) goes back a
    page, the main page closes the panel, and that is waited out (it fades). Never Escape: with the panel half gone
    it opens the game menu (2026-10-18). True when the panel is gone."""
    from tools import wait
    from tools.ui import click
    for _ in range(6):
        p = page(ui)
        if p is None:
            return True
        x = ui.first("cancel_button", under=TRIGGER) if p == "trigger" else _under(ui, "button_close", PANEL)
        if x is None:
            break
        board = _under(ui, "chaotic_plans_plan_board", PANEL) if p == "board" else None
        if board is not None:                      # a plan just started opens its board: let it finish sliding in
            wait.stable_rect(ui, board, n=4, timeout=1.5, must=False, what="plan board still")
            # and its X takes input a moment later (turn 24: a click on the still board was ignored, 1 s lost):
            # the cursor rests on it until it shows the hover
            from tools.ui import move_to
            over = lambda: "hover" in (ui.state(x) or "")
            end = time.time() + 2.0
            while time.time() < end and not over():
                move_to(*ui.comp(x).center)
                wait.wait_until(over, 0.25, "board X takes the hover", must=False)
        wait.stable_rect(ui, x, n=3, timeout=1.0, must=False, what="Masterplans X still")
        click(ui, x)
        if p == "main":
            break
        # 2026-10-18: an X clicked while a new board slid in was ignored and cost a 2 s wait; 1 s, then it is
        # clicked again (the retry took 0.4 s)
        # right after a start the first X on the new board backs out of the setup underneath, the second closes the
        # board (turns 30-32: the first never changed the page, the second did in 0.4 s): retry soon on a board
        wait.wait_until(lambda: page(ui) != p, 0.5 if p == "board" else 1.0, f"back from the {p} page", must=False)
    return bool(wait.wait_until(lambda: not ui.root_child(PANEL), 3.0, "Masterplans panel closed", must=False))


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


def _log(entry: dict) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), **entry}) + "\n")
    except OSError:
        pass


def _confirm(ui, done=None) -> None:
    """Accept a confirmation the game may show (a prompt with a tick). done: the action's own result (read from
    memory); once it shows, no prompt is coming, so there is no wait (2026-10-18 timing logs: the game never asked
    after a start, a purchase or a completion, and each fixed 1.5 s wait showed as a pause)."""
    from tools import wait
    from tools.ui import click
    box = wait.wait_until(lambda: ui.root_child("dialogue_box") or (done is not None and done()), 1.5,
                          "confirmation or result", must=False)
    if not box or not ui.root_child("dialogue_box"):
        return
    for b in ("button_tick", "button_accept", "button_ok"):
        t = ui.first(b, under="dialogue_box")
        if t is not None:
            click(ui, t)
            wait.wait_until(lambda: not ui.root_child("dialogue_box"), 2.0, "confirmation closed", must=False)
            return


# ------------------------------------------------------------------ memory: the boards, the shop
def board_from(plan, w) -> dict:
    """The decision inputs of a running plan, from memory (bot/sensor/masterplans.Plan); the region's income is
    region_gdp()."""
    from bot.sensor.masterplans import WARPSTONE_KEY
    tot = sum(wt for _t, wt in plan.pool) or 1
    inc = region_gdp(w, plan.region_obj)
    income = float(inc) if inc is not None else None
    return {"risk": plan.risk, "alarm": plan.alarm, "alarm_max": plan.alarm_max, "gold": float(plan.treasury),
            "warpstone": float(plan.resources.get(WARPSTONE_KEY, 0)), "draws": plan.draws_next,
            "bag": [(t, wt * 100.0 / tot) for t, wt in plan.pool], "drawn": len(plan.drawn), "income": income,
            "can_complete": plan.can_complete, "resources": plan.resources}


@lru_cache(maxsize=1)
def shop_objects() -> dict[str, list[dict]]:
    """shop chain -> [{"token", "cost", "needed"} per level, in order] (cost in Warpstone; needed = purchases in
    that tab before the level can be bought)."""
    from . import gamedata as gd
    price = defaultdict(int)
    for r in gd._load("resource_cost_pooled_resource_junctions_tables"):
        if "warpstone" in r["pooled_resource_factor"]:
            price[r["resource_cost"]] += -int(r["amount"])
    objs = {r["key"]: r for r in gd._load("chaotic_plan_shop_category_objects_tables")}
    ch = defaultdict(list)
    for r in gd._load("chaotic_plan_shop_category_chain_to_object_junctions_tables"):
        o = objs.get(r["category_object"])
        if o:
            ch[r["category_chain"]].append((r["order"], {"token": o["token"], "cost": price.get(o["shop_price"], 0),
                                                         "needed": int(o.get("amount_needed_to_unlock") or 0)}))
    return {c: [x for _o, x in sorted(v, key=lambda t: t[0])] for c, v in ch.items()}


TAB_UNDERLING = {"wh3_dlc29_skv_shop_grey_seer": "wh3_dlc29_skv_schemer_grey_seer",
                 "wh3_dlc29_skv_shop_warlord": "wh3_dlc29_skv_schemer_warlord",
                 "wh3_dlc29_skv_shop_assassin": "wh3_dlc29_skv_schemer_master_assassin",
                 "wh3_dlc29_skv_shop_warlock": "wh3_dlc29_skv_schemer_warlock_master"}   # thanquol's tab: always open


def owned_levels(chain: str, inventory: set[str]) -> int:
    """Levels of a shop line owned: one past the highest level whose token is in the Secrets inventory."""
    lv = shop_objects().get(chain, [])
    return max((i + 1 for i, o in enumerate(lv) if o["token"] in inventory), default=0)


def shop_plan(cfg: dict, warpstone: int, inventory: set[str], unlocked: set[str]) -> tuple[list, str]:
    """([(chain, level index, cost, name)] to buy now, in order; why it stops), from memory. Strict order: the first
    entry that can be bought but not afforded is saved for and nothing below it is bought. Locked entries (the tab's
    Underling not unlocked, or too few purchases in that tab yet) are skipped. A tab's purchases are the lines owned
    in it, not the levels (2026-10-22, turn 38, Grey Seer tab with Warlord Clan's Tunnel II and Superior Rats: every
    line needing 2 was open, every one needing 3 locked; counted as 3 levels, Rictus Miners' Holes was tried and had
    no Purchase button)."""
    keep = int(cfg.get("keep_warpstone", 50))
    tabs = shop_tabs()
    per_tab = defaultdict(int)
    for c in shop_objects():
        per_tab[tabs.get(c)] += owned_levels(c, inventory) > 0
    have, buys, owned_now = warpstone, [], {}
    for entry in cfg.get("order", []):
        chain, want = entry["chain"], int(entry.get("levels", 1))
        lv, tab = shop_objects().get(chain), tabs.get(chain)
        if not lv or tab is None:
            continue
        if tab in TAB_UNDERLING and TAB_UNDERLING[tab] not in unlocked:
            continue
        names = entry.get("_what", chain).split(" / ")
        owned = owned_now.get(chain, owned_levels(chain, inventory))
        while owned < min(want, len(lv)):
            o = lv[owned]
            name = names[owned] if owned < len(names) else names[0]
            if per_tab[tab] < o["needed"]:
                break                                  # locked: too few purchases in that tab yet
            if have - o["cost"] < keep:
                return buys, f"saving for {name} ({o['cost']} Warpstone, have {have}, keeping {keep})"
            buys.append((chain, owned, o["cost"], name))
            have -= o["cost"]
            per_tab[tab] += owned == 0
            owned += 1
            owned_now[chain] = owned
    return buys, "" if buys else "nothing on the list left to buy"


TRIGGER = "dlc29_skv_chaotic_plans_trigger_animation"
SETTLE_S = 1.0          # after a completion: the game must render steadily this long before the next click


def _settle_after_completion(ui) -> None:
    """Hands off after a completion (2026-10-18, turn 34: the game stopped rendering ~50 ms after Karak Hirn's
    completion, when the step clicked on to the next plan, and crashed): until the plan-complete screen has closed
    by itself (up to 4 s) and frames have come steadily for SETTLE_S (a frame more than 0.25 s late starts the count
    again; up to 8 s in all). No input in between."""
    from tools import wait
    wait.wait_until(lambda: not ui.first("trigger_plan_button", under=TRIGGER), 4.0, "plan-complete screen gone",
                    must=False)
    end = time.time() + 8.0
    calm = time.time()
    while time.time() < end and time.time() - calm < SETTLE_S:
        t = time.time()
        try:
            wait.next_frame(1, ui, timeout=1.0)
        except Exception:
            pass
        if time.time() - t > 0.25:                  # a stall: start the count again
            calm = time.time()


def _confirm_trigger(ui, done=None) -> bool:
    """Complete opens the plan-complete screen (dlc29_skv_chaotic_plans_trigger_animation: the loot summary with its
    own trigger_plan_button and a cancel_button); its Complete is what completes the plan. The button takes input
    only once the screen's opening animation is over (2026-10-18: clicked 50 ms after the screen showed, it never
    took the hover and the click did nothing; its Cancel, 7.5 s later, worked at once): the cursor rests on it until
    it shows the hover (up to 8 s), then it is clicked; done (the plan gone from memory) confirms, else up to two
    more clicks."""
    from tools import wait
    from tools.ui import click, move_to
    btn = wait.wait_until(lambda: ui.first("trigger_plan_button", under=TRIGGER), 4.0, "plan-complete screen",
                          must=False)
    if btn is None:
        return False
    wait.stable_rect(ui, btn, n=4, timeout=3.0, must=False, what="plan-complete Complete still")
    hovered = lambda: any(k in (ui.state(btn) or "") for k in ("hover", "down"))
    end = time.time() + 8.0
    while time.time() < end and not hovered():
        move_to(*ui.comp(btn).center)
        wait.wait_until(hovered, 0.4, "plan-complete Complete takes the hover", must=False)
    for _ in range(3):
        click(ui, btn)
        if done is None or wait.wait_until(done, _cap(), "plan completed (memory)", must=False):
            return True
        if not ui.first("trigger_plan_button", under=TRIGGER):
            return False
    return False


# ------------------------------------------------------------------ 1. running Steal-Takes
def _open_plan(ui, region: str) -> bool:
    from tools import wait
    from tools.ui import click
    if not open_main(ui):
        return False
    item = next((c for c, p, r in active_plans(ui) if p == ECONOMIC and r == region), None)
    if item is None:
        return False
    click(ui, item)
    return bool(wait.wait_until(lambda: _under(ui, "trigger_plan_button", PANEL), 3.0, "plan board", must=False))


def manage_plans(ui, cfg: dict, turn, state, w) -> list[str]:
    """Every running Steal-Take decided from memory; its board is opened only to press Complete / Abandon, and the
    plan's end is confirmed in memory."""
    from tools import wait
    from tools.ui import click
    from bot.sensor import masterplans as mem
    from . import gamedata as gd
    out = []
    for plan in [p for p in state.plans if p.type == "economic"]:
        place = gd.place_name(plan.region)
        b = board_from(plan, w)
        act, why = decide(b, cfg)
        _log({"turn": turn, "region": plan.region, "board": b, "decision": act, "why": why, "source": "memory"})
        if act == "wait":
            out.append(f"Steal-Take {place}: wait ({why})")
            continue
        if not _open_plan(ui, plan.region):
            out.append(f"Steal-Take {place}: {act} decided, but its board did not open")
            continue
        board_btn = _under(ui, "trigger_plan_button" if act == "complete" else "abandon_button", PANEL)
        click(ui, board_btn)
        running = lambda: any(p.region == plan.region and p.type == "economic" for p in (mem.read(w) or state).plans)
        if act == "complete":
            _confirm_trigger(ui, done=lambda: not running())
        _confirm(ui, done=lambda: not running())
        gone = wait.wait_until(lambda: not running(), _cap(), "plan finished (memory)", must=False)
        _settle_after_completion(ui)
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


def _own_provinces(w, F: int) -> set[str]:
    """Our provinces: every province in which we hold a region."""
    from bot.sensor.world import snapshot
    snap = snapshot(w)
    if snap is None:
        return set()
    return {snap.province_of.get(k, k) for k in snap.own}


def target_scores(w, F: int, state, cfg: dict) -> dict[str, float]:
    """region key -> score for every foreign settlement a Steal-Take may target, from memory: the region's income
    (region:gdp(), the loot is a share of it; player request 2026-10-22: a 200/turn Varenka Hills was taken over a
    900/turn Karaz-a-Karak), and (by default) factions we are not at war with first. Left out: settlements on a
    Masterplans cooldown, already targeted, without a main building, under the shroud, and (skip_own_provinces) every
    settlement in one of our provinces."""
    from bot.sensor.world import region_provinces
    regs = _region_objects(w, F)
    own = _own_provinces(w, F) if cfg.get("skip_own_provinces", True) else set()
    prov = region_provinces()[0]
    busy = {p.region for p in state.plans}
    wars = set(w.wars(F))
    out = {}
    for region, r in regs.items():
        if region in busy or region in state.region_cooldowns or prov.get(region, region) in own:
            continue
        owner = w.region_owner(r)
        if not owner or owner == F:
            continue
        if not w.explored(F, r):
            continue                               # under the shroud: no label to click, the camera was panned there
                                                   # for nothing (2026-10-18, turns 28-29; World.explored, the game's
                                                   # own shroud test, matched every pan tried)
        slots = w.slots(r)
        main = slots[0] if slots else None
        if not main or not main.building:
            continue
        score = float(max(region_gdp(w, r) or 0, 0))
        if cfg.get("prefer_not_at_war", True) and owner not in wars:
            score += NOT_AT_WAR_BONUS
        out[region] = score
    return out


NOT_AT_WAR_BONUS = 100000      # above any region's income: a faction we are not at war with always comes first


def region_gdp(w, region_obj: int) -> int | None:
    """region:gdp(), i32 at the region object +0x10C (decompiled binding 0x1427C3750, 9.0.4; 2026-10-22 live:
    Karaz-a-Karak 900, Varenka Hills 200, as the game shows)."""
    try:
        return struct.unpack("<i", w.pm.read_bytes(region_obj + 0x10C, 4))[0]
    except Exception:
        return None


def _labels_on_screen(ui, avoid_rects) -> dict[str, int]:
    """region key -> its clickable name label, for the settlement labels on screen (click targets only)."""
    parent = ui.root_child("3d_ui_parent")
    out = {}
    for c in ui.children(parent) if parent else []:
        i = ui.id(c) or ""
        if not i.startswith("label_settlement:") or not ui.visible(c):
            continue
        name = next((x for x, ii, _r in ui.nodes(c) if ii == "dy_name"), None)
        if name is None:
            continue
        k = ui.comp(name)
        if not (0 < k.x and k.x + k.w < 1920 and 60 < k.y and k.y + k.h < 1000):
            continue
        cx, cy = k.x + k.w / 2, k.y + k.h / 2
        if any(a.x <= cx <= a.x + a.w and a.y <= cy <= a.y + a.h for a in avoid_rects):
            continue
        out[i.split(":", 1)[1]] = name
    return out


@lru_cache(maxsize=1)
def underling_cards() -> dict[str, str]:
    """Underling subtype -> the start-position id its card is named after
    (CcoChaoticPlanSchemersSpecialInfoRecord<id>special_info_record; the shop tab of that Underling has the same id)."""
    from . import gamedata as gd
    pos = {r["key"]: r["character_start_pos_id"] for r in gd._load("chaotic_plan_shop_categories_tables")}
    return {sub: pos[tab] for tab, sub in TAB_UNDERLING.items() if pos.get(tab)}


def _select_underling(ui, subtype: str) -> bool:
    """Click the Underling's card (found by its id, 2026-10-18: the details show "Grey Seer Underling", not his name)
    and wait until it is selected."""
    from tools import wait
    from tools.ui import click
    pid = underling_cards().get(subtype)
    lst = _under(ui, "schemers_list", PANEL)
    card = next((c for c in (ui.children(lst) if lst else [])
                 if pid and (ui.id(c) or "").startswith(f"CcoChaoticPlanSchemersSpecialInfoRecord{pid}")), None)
    if card is None:
        return False
    if not (ui.state(card) or "").startswith("selected"):
        click(ui, card)
    return bool(wait.wait_until(lambda: (ui.state(card) or "").startswith("selected"), 1.5, "Underling selected",
                                must=False))


def settlement_xy(w, region_obj: int, cache: dict) -> tuple[float, float] | None:
    """A settlement's map position, from memory: where its owner's garrison commander stands."""
    from bot.sensor.camera import character_pos
    from bot.sensor.world import armies
    owner = w.region_owner(region_obj)
    if not owner:
        return None
    if owner not in cache:
        cache[owner] = {a.region_obj: character_pos(w.pm, a.general_ptr)
                        for a in armies(w, owner, include_garrisons=True) if a.garrison and a.general_ptr}
    return cache[owner].get(region_obj)


UNREACHABLE: set[str] = set()      # settlements the camera could not bring on screen, this session


def _reachable_targets(ui, w, scores: dict, taken: set, labels: dict, avoid_rects, cfg: dict):
    """(region, its label) best score first, for the settlements on screen or within max_pan map units of the screen
    centre; one off screen is brought into view (camera panned with WASD from memory, assist/heroes.py) only when its
    turn comes. Yields at most 4 candidates."""
    from bot.sensor.camera import read_camera
    from .heroes import bring_into_view, in_safe
    regs = _region_objects(w, find_player(w))
    cache: dict = {}
    try:
        cx, cy = read_camera(w.s).ground_at_center()
    except Exception:
        cx = cy = None
    cands = []
    for region, score in scores.items():
        if region in taken:
            continue
        if region in labels:
            cands.append((-score, 0.0, region, None))
            continue
        xy = settlement_xy(w, regs.get(region, 0), cache) if regs.get(region) else None
        if xy is None or cx is None:
            continue
        d = ((xy[0] - cx) ** 2 + (xy[1] - cy) ** 2) ** 0.5
        if d <= cfg.get("max_pan", 120):
            cands.append((-score, d, region, xy))
    tries = 0
    for _s, _d, region, xy in sorted(cands)[:8]:
        if region in UNREACHABLE:
            continue
        lab = f"label_settlement:{region}"
        if xy is not None:
            # at most 2 pans per Underling (2026-10-18, turn 28: five settlements without a label on screen, under the
            # fog of war most likely, cost 2-4 s each, 23 s in all); each failure is not tried again this session
            if tries >= 2:
                continue
            tries += 1
            k, _jumped = bring_into_view(w, ui, xy[0], xy[1], lab)
            if k is None or not in_safe(k):
                UNREACHABLE.add(region)                # (2026-10-18: each failed pan cost ~6 s, every turn)
                continue
        now = _labels_on_screen(ui, avoid_rects)
        if region in now:
            yield region, now[region]


def find_player(w) -> int | None:
    from bot.sensor.world import find_player_faction
    return find_player_faction(w)


def start_plans(ui, cfg: dict, state, w, F: int, dry_run: bool = False) -> list[str]:
    """Free Underlings (memory) on Steal-Takes against the best-scored settlement (memory) whose label is on screen;
    each start confirmed in memory. dry_run: pick the Underling and the target, then back out without starting."""
    from tools import wait
    from tools.ui import click, click_at, move_to
    from bot.sensor import masterplans as mem
    from . import gamedata as gd
    free = [u for u in state.underlings if u.free]
    if not free:
        return []
    if "economic" not in state.unlocked_types:
        return [f"{', '.join(u.name for u in free)}: Steal-Take is not unlocked yet"]
    scores = target_scores(w, F, state, cfg)
    warpstone, taken, out = state.warpstone, set(), []
    for u in free:
        if warpstone < 50:
            out.append(f"{u.name}: no Steal-Take started (needs 50 Warpstone, have {warpstone})")
            break
        if not open_main(ui) or not _select_underling(ui, u.subtype):
            out.append(f"{u.name}: could not select the Underling")
            continue
        new = wait.wait_until(lambda: _under(ui, "new_plan_button", PANEL), 1.5, "New Masterplan", must=False)
        if new is None:
            out.append(f"{u.name}: no New Masterplan button")
            continue
        click(ui, new)
        eco = wait.wait_until(lambda: _under(ui, "economy_plan_button", PANEL), 3.0, "plan types", must=False)
        if eco is None:
            out.append(f"{u.name}: no Steal-Take button")
            continue
        click(ui, eco)
        # the targeting view: its panes in place and the settlement labels shown (was a fixed 0.8 s sleep)
        wait.wait_until(lambda: _under(ui, "target_holder", PANEL), 1.5, "Steal-Take targeting", must=False)
        th = _under(ui, "target_holder", PANEL)
        if th is not None:
            wait.stable_rect(ui, th, n=3, timeout=1.0, must=False, what="targeting panes still")
        avoid = [ui.comp(x) for x in (_under(ui, n, PANEL) for n in
                                      ("plan_type_holder", "target_holder", "bottom_bar", "lord_info")) if x]
        labels = _labels_on_screen(ui, avoid)
        started = False
        for region, label in _reachable_targets(ui, w, scores, taken, labels, avoid, cfg):
            k = ui.comp(label)
            click_at(int(k.x + k.w / 2), int(k.y + k.h / 2))
            place = gd.place_name(region)
            shown = wait.wait_until(lambda: place in _txt(ui, _under(ui, "dy_settlement_target", PANEL)), 1.5,
                                    f"{place} targeted", must=False)
            est = _under(ui, "establish_plan_button", PANEL)
            if not shown or est is None:
                continue
            if dry_run:
                out.append(f"{u.name}: would start a Steal-Take on {place} (score {scores[region]})")
                started = True
                break
            click(ui, est)
            _confirm(ui, done=lambda: any(p.region == region for p in (mem.read(w) or state).plans))
            ok = wait.wait_until(lambda: any(p.region == region for p in (mem.read(w) or state).plans), _cap(),
                                 "plan started (memory)", must=False)
            out.append(f"{u.name}: Steal-Take started on {place}" if ok else
                       f"{u.name}: Steal-Take on {place} NOT confirmed")
            if ok:
                _log({"started": region, "underling": u.name, "score": scores[region]})
                warpstone -= 50
                taken.add(region)
            started = True
            break
        if not started:
            out.append(f"{u.name}: no Steal-Take target could be brought on screen ({len(scores)} eligible "
                       f"settlements; none within {cfg.get('max_pan', 120)} map units came on screen)")
        move_to(960, 1070)
    return out


def _cap() -> float:
    """How long an action's effect is waited for in memory: the game's own pace (bot/sensor/commands.py, player rule
    2026-10-19): the wait ends the moment memory shows it; multiplayer sync can take seconds."""
    from bot.sensor.commands import EFFECT_CAP_S
    return EFFECT_CAP_S


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
    if not wait.wait_until(lambda: _under(ui, "dlc29_skv_token_shop", PANEL), 3.0, "Secrets shop", must=False):
        return False
    # the tabs fill in a moment after the shop shows (2026-10-18: a tab looked for at once was "not shown")
    return bool(wait.wait_until(lambda: _under(ui, "CcoChaoticPlanShopCategoryRecordwh3_dlc29_skv_shop_thanquol",
                                               PANEL), 2.0, "shop tabs", must=False))




def buy_secrets(ui, buys: list, w, F: int) -> list[str]:
    """Buy what shop_plan picked (memory): one click per level, each confirmed by the Warpstone spent (memory)."""
    from tools import wait
    from tools.ui import click
    from bot.sensor import masterplans as mem
    from .build import _scroll_into_clip
    rd = mem.Reader(w)
    ws = lambda: rd.pooled(F).get(mem.WARPSTONE_KEY, 0)
    out = []
    if not _open_shop(ui):
        return ["the Secrets shop did not open"]
    for chain, level, cost, name in buys:
        tab = wait.wait_until(lambda: _under(ui, f"CcoChaoticPlanShopCategoryRecord{shop_tabs().get(chain)}", PANEL),
                              2.0, "shop tab shown", must=False)
        if tab is None:
            out.append(f"{name}: its shop tab is not shown")
            break
        if not (ui.state(tab) or "").startswith("selected"):
            click(ui, tab)
            wait.wait_until(lambda: (ui.state(tab) or "").startswith("selected"), 2.0, "shop tab", must=False)
        line = wait.wait_until(lambda: _under(ui, f"CcoCampaignChaoticPlanShopObjectChain{chain}", PANEL), 2.0,
                               f"{chain} listed", must=False)
        if line is None or not _scroll_into_clip(ui, line, "Secrets list"):
            out.append(f"{name}: its line is not shown")
            break
        if not (ui.state(line) or "").startswith("selected"):
            click(ui, ui.child(line, "button_wh3") or line)
            wait.wait_until(lambda: (ui.state(line) or "").startswith("selected"), 2.0, "line selected", must=False)
            time.sleep(0.3)
        # the details on the right fill in a moment after the line is selected (2026-10-18, turn 23: looked for
        # 0.3 s after, the button was not there yet and the purchase was dropped as "memory and the shop disagree")
        # a line's first level is bought with button_purchase, its next levels with button_upgrade ("Upgrade";
        # 2026-10-18, turn 25: Veteran Drillers was dropped for want of a Purchase button)
        def buy_button():
            for bid in ("button_purchase", "button_upgrade"):
                b = _under(ui, bid, PANEL)
                if b is not None and ui.visible(b):
                    return b
            return None
        btn = wait.wait_until(buy_button, 1.5, "Purchase / Upgrade button", must=False)
        if btn is None:
            out.append(f"{name}: no Purchase or Upgrade button (memory and the shop disagree)")
            break
        have = ws()
        click(ui, btn)
        _confirm(ui, done=lambda: ws() <= have - cost)
        if not wait.wait_until(lambda: ws() <= have - cost, _cap(), "purchase registered (memory)", must=False):
            out.append(f"{name}: the purchase did not register")
            break
        out.append(f"bought {name} ({cost} Warpstone)")
        _log({"bought": chain, "level": level + 1, "cost": cost})
        time.sleep(0.4)
    return out


# ------------------------------------------------------------------ the step
LAST_NOTES: list = []     # the last run's result lines (the reasons it gave for what it could not do)


def missed() -> list[str]:
    """The memory check after the step (player request 2026-10-19), everything decided again from memory after the
    run: a Steal-Take the rules complete (or abandon) now must be gone from the plans; a free Underling, with Steal-
    Takes unlocked and 50 Warpstone, must have started one; the Secrets the shop order buys now must be owned. A
    thing the run explained (no target came on screen, a button not there: UI, or the game refused) is reported as
    not possible; anything else is missed. Kill-Stabs are the player's and never checked."""
    from bot.sensor import masterplans as mem
    from bot.sensor.world import World, find_player_faction
    from . import gamedata as gd
    w = World()
    F = find_player_faction(w)
    if F is None or w.faction_name(F) != SCRUTEN:
        return []
    cfg = settings()
    st, shop = cfg.get("steal_take", {}), cfg.get("shop", {})
    state = mem.read(w)
    if state is None or not state.unlocked_types:
        return []
    notes = "; ".join(LAST_NOTES)
    out = []
    if st.get("enabled", True):
        for p in state.plans:
            if p.type == "economic":
                act, why = decide(board_from(p, w), st)
                if act != "wait":
                    place = gd.place_name(p.region)
                    out.append(f"Steal-Take {place}: should be {act}d ({why})"
                               + (" (not possible: the run reported it)" if place in notes else ""))
        free = [u for u in state.underlings if u.free and u.unlocked]
        if "economic" in state.unlocked_types and free and state.warpstone >= 50:
            names = ", ".join(u.name for u in free)
            hit = [n for n in (u.name for u in free) if n in notes]
            out.append(f"{names}: free, no Steal-Take started"
                       + (f" (not possible: {notes})" if hit else ""))
    if shop.get("enabled", True):
        unlocked = {u.subtype for u in state.underlings if u.unlocked}
        buys, _why = shop_plan(shop, state.warpstone, set(state.inventory), unlocked)
        if buys:
            out.append("Secrets not bought: " + ", ".join(b[3] for b in buys))
    return out


def run(log=print, verify: bool = False) -> str:
    from bot.focus import game_focus
    from bot.sensor import masterplans as mem
    from bot.sensor.ui import UI
    from bot.sensor.world import World, find_player_faction
    from . import gamedata as gd
    w = World()
    F = find_player_faction(w)
    if F is None:
        return "player faction not found"
    if w.faction_name(F) != SCRUTEN:
        return "no Masterplans (Thanquol's Clan Scruten only)"
    if verify:
        return "nothing to verify"                   # every action is confirmed in memory as it happens
    cfg = settings()
    st, shop = cfg.get("steal_take", {}), cfg.get("shop", {})
    st_on, shop_on = st.get("enabled", True), shop.get("enabled", True)
    if not st_on and not shop_on:
        return "off (strategy/masterplans.json)"
    state = mem.read(w)
    if state is None:
        return "Masterplans not found in memory"
    if not state.unlocked_types:
        return "Masterplans are not unlocked yet"
    turn = w.s.read().turn
    # everything is decided from memory first; the panel is opened only when there is something to click
    plans = [(p, board_from(p, w)) for p in state.plans if p.type == "economic"] if st_on else []
    acting = any(decide(b, st)[0] != "wait" for _p, b in plans)
    starting = st_on and "economic" in state.unlocked_types and any(u.free for u in state.underlings)
    buys, why = [], ""
    if shop_on:
        unlocked = {u.subtype for u in state.underlings if u.unlocked}
        buys, why = shop_plan(shop, state.warpstone - (50 if starting else 0), set(state.inventory), unlocked)
    out = []
    if not acting:
        for p, b in plans:
            act, reason = decide(b, st)
            _log({"turn": turn, "region": p.region, "board": b, "decision": act, "why": reason, "source": "memory"})
            out.append(f"Steal-Take {gd.place_name(p.region)}: wait ({reason})")
    if st_on and not starting and any(u.free for u in state.underlings):
        out.append("Steal-Take is not unlocked yet")
    if not (acting or starting or buys):
        return "; ".join(out + ([why] if why else [])) or "nothing to do"
    ui = UI(w.s)
    ui.find_root()
    with game_focus():
        try:
            if not open_main(ui):
                return "; ".join(out + ["the Masterplans panel did not open"])
            if acting:
                out += manage_plans(ui, st, turn, state, w)
            if starting:
                out += start_plans(ui, st, mem.read(w) or state, w, F)
            if shop_on and (acting or starting):
                # what to buy decided again from memory now: a completed Steal-Take has brought its Warpstone in and
                # a started one has spent its 50 (2026-10-20, turn 24: Mighdal Vongalbarak's 265 Warpstone came in
                # after the list was made, the Veteran Drillers were not bought and the check reported them missed)
                now = mem.read(w) or state
                buys, why = shop_plan(shop, now.warpstone, set(now.inventory),
                                      {u.subtype for u in now.underlings if u.unlocked})
            if buys:
                out += buy_secrets(ui, buys, w, F)
            if why:
                out.append(why)
        finally:
            if not close_panel(ui):
                out.append("the Masterplans panel did not close")
    LAST_NOTES[:] = out
    return "; ".join(out) or "nothing to do"
