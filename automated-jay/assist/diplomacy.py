"""Diplomacy for gold (player decisions 2026-10-21): at the start of every turn, until no deal is left, read fresh
from memory every turn (so it works the same from any point of a campaign, and factions met later join in):

  peace      for each AI faction the player is at war with that does not border the player's territory (minor or
             major), offer peace for a payment to the player
  join war   for each AI faction the player has met that is a minor faction, or a major at most half the player's
             strength, and is at war with a major faction the player has met: offer the major "I join your war
             against <it>" for a payment to the player

A wiped-out faction (is_dead) is never offered anything, so the list shrinks as factions die. Tribute (a payment
demand alone) was tried and dropped the same day (player decision 2026-10-21): a demand with nothing in return starts
at -20 to the AI, so no faction would ever accept it.

asking for the most gold the AI accepts. Never a war against a faction with a treaty with the player (trade,
non-aggression, alliance, vassal), with a treaty or alliance with another human, or bordering the player; never a
deal against or with a human faction. The player turns factions off and on per kind of deal in the expanded widget
(strategy/diplomacy.json "off"; all on by default).

Never Threaten (button_threat_of_force): the game's tooltip says a rejected threat means war and counts as treachery
(reliability down), so it is not a safe deal.

Major = faction:can_be_human, strength = faction_strength (bot/sensor/diplomacy.py); every fact the plan stands on is read from memory. Each deal is
checked in memory: the treasury goes up and the war starts (join war) or ends (peace).

UI stop-gap: the AI's evaluation of a proposal (label_deal_success_chance, label_payment_success_chance: positive =
they accept) is read from the panel, memory reader pending. Decoded so far (9.0.4, 2026-10-21): the evaluation is
recomputed by the panel on every change and kept only on the stack (total float, payment component float -0.00653
per gold for Wissenland, linear in the amount); no heap copy was found.

Diplomacy panel (9.0.4, 2026-10-21, checked live with a join-war deal: Wissenland paid 587 for a war against The
Court of Night, the most it accepted, found by this search):
  diplomacy_dropdown (root child) / sortable_list_factions / faction_row_entry_<key>; Negotiate = button_ok under
  faction_panel_bottom/both_buttongroup; the offer screen: list_possible_actions/diplomatic_option_<kind> (join_war,
  payment, peace ...; label_success_chance_for_action = the AI's value of that item alone, peace shows it before it is
  added); join war opens diplomacy_hud_request_join_war: list_offers rows list_box_<n> (text = the faction's screen
  name) with a checkbox, ok_request; payments opens diplomacy_hud_payments: pay_demand / pay_offer, amount (a text
  label: typed text is taken by the next arrow click, an arrow moves it 200), l_/r_arrow_amount, ok_payments;
  button_send under button_set_holder; the answer: dy_text state they_accepted, closed with button_accept; the
  button_cancel under button_set_holder goes back to the faction list.

    python -X utf8 -m assist.diplomacy plan     # memory: the deals that would be offered, and why others are not
    python -X utf8 -m assist.diplomacy run      # offer them (raises the game)
"""
from __future__ import annotations
import json
import sys
from dataclasses import dataclass

from bot import config
from bot.focus import game_focus
from bot.sensor import commands
from bot.sensor import diplomacy as dip
from bot.sensor.ui import UI
from bot.sensor.world import World, find_player_faction
from tools import wait
from tools.ui import click, press, type_text
from . import gamedata as gd

SETTINGS = config.STRATEGY_DIR / "diplomacy.json"
KINDS = ("peace", "join_war")    # also the order deals are offered in
WEAK = 0.5                     # "much weaker": strength at most this share of the player's (player decision 2026-10-21;
                               # diplomacy.json "major_target_max_strength", set in the widget)
MAX_DEALS = 30                 # per pass: a guard, the plan normally runs out long before
STEP = 200                     # the payment arrows move the amount by 200


@dataclass(frozen=True)
class Deal:
    kind: str                  # "peace" or "join_war"
    target: str                # the faction the deal is about: the war is against it (join war) or made with it
                               # (peace)
    payer: str                 # who pays: the major (join war), the target itself (peace)
    treasury: int              # the payer's treasury (memory)

    def line(self) -> str:
        if self.kind == "join_war":
            return f"{name(self.payer)}: join their war against {name(self.target)}"
        return f"{name(self.target)}: {self.kind}"


def name(key: str) -> str:
    return gd.loc().get(f"factions_screen_name_{key}") or key


# ------------------------------------------------------------------ settings (the widget's toggles)
def _settings() -> dict:
    try:
        return json.load(open(SETTINGS, encoding="utf-8"))
    except Exception:
        return {}


def weak_share() -> float:
    try:
        return float(_settings().get("major_target_max_strength", WEAK))
    except (TypeError, ValueError):
        return WEAK


def kind_on(kind: str) -> bool:
    """diplomacy.json "enabled": a whole kind of deal switched off in the widget."""
    return bool((_settings().get("enabled") or {}).get(kind, True))


def load_off() -> dict[str, set[str]]:
    try:
        off = json.load(open(SETTINGS, encoding="utf-8")).get("off") or {}
    except Exception:
        off = {}
    return {k: set(off.get(k) or ()) for k in KINDS}


def set_on(kind: str, target: str, on: bool) -> None:
    """The widget's toggle: a faction turned off (or back on) for one kind of deal."""
    try:
        data = json.load(open(SETTINGS, encoding="utf-8"))
    except Exception:
        data = {}
    data.setdefault("_doc", DOC)
    off = data.setdefault("off", {})
    keys = set(off.get(kind) or ())
    (keys.discard if on else keys.add)(target)
    off[kind] = sorted(keys)
    for k in KINDS:
        off.setdefault(k, [])
    tmp = SETTINGS.with_suffix(".tmp")
    json.dump(data, open(tmp, "w", encoding="utf-8"), indent=2)
    tmp.replace(SETTINGS)


DOC = ["Diplomacy for gold (assist/diplomacy.py), player decisions 2026-10-21: peace for gold with AI factions at war "
       "with the player that do not border them, join-war offers to major factions against minors and majors at most "
       "half the player's strength; always the most gold the AI accepts.",
       "'off': faction keys the player turned off in the expanded widget, per kind of deal; every faction is on "
       "unless listed here.",
       "'enabled': each kind of deal on or off; 'major_target_max_strength': a major faction is a join-war target "
       "only at most this share of the player's strength (0.5 = half). Both set in the expanded widget."]


# ------------------------------------------------------------------ the plan (memory only)
def candidates(me: dip.Faction, others: dict[str, dip.Faction], border: set[str], share: float = WEAK) \
        -> tuple[list[Deal], list[tuple[str, str, str]]]:
    """Every deal the rules allow, toggles not applied, in KINDS order (best payer first per target), and
    (kind, target, why) for the factions left out. Pure: tests feed it plain data."""
    deals: list[Deal] = []
    skipped: list[tuple[str, str, str]] = []
    humans = [k for k, f in others.items() if f.human]
    weak = lambda f: 0 < f.strength <= share * me.strength
    for k, t in sorted(others.items()):
        r = me.rels.get(k)
        if t.human or t.rebel or t.dead or r is None or not r.met:
            continue
        if r.war:
            if k in border:
                skipped.append(("peace", k, "borders your territory"))
            else:
                deals.append(Deal("peace", k, k, t.treasury))
            continue
        if not t.regions or (t.major and not weak(t)):
            continue
        payers = sorted((a for a, ra in t.rels.items() if ra.war and a in others and others[a].major
                         and not others[a].human and me.rels.get(a) is not None and me.rels[a].met
                         and not me.rels[a].war),
                        key=lambda a: -others[a].treasury)
        if not payers:
            continue
        why = ("a treaty with you" if r.treaty else "borders your territory" if k in border else
               next((f"a treaty with {name(h)}" for h in humans if t.rels.get(h) and t.rels[h].treaty), None))
        if why:
            skipped.append(("join_war", k, why))
            continue
        deals += [Deal("join_war", k, a, others[a].treasury) for a in payers]
    deals.sort(key=lambda d: KINDS.index(d.kind))            # stable: payer order kept
    return deals, skipped


def plan(w: World | None = None, F: int | None = None) -> tuple[list[Deal], list[tuple[str, str, str]]]:
    """The deals to offer now: candidates() with the player's toggles and this turn's refusals taken out."""
    w = w or World()
    F = F or find_player_faction(w)
    if not F:
        return [], []
    me, others, border = dip.read(w, F)
    deals, skipped = candidates(me, others, border, weak_share())
    deals = [d for d in deals if kind_on(d.kind)]
    off = load_off()
    tried = _tried(w)
    made = {k[1] for k, line in tried.items() if _made(line)}   # one deal per faction a turn: peace for gold and
    out = []                                                    # then a paid war on it again would flip it every pass
    for d in deals:
        if d.target in off[d.kind]:
            skipped.append((d.kind, d.target, "turned off"))
        elif d.target in made:
            skipped.append((d.kind, d.target, "a deal with it was made this turn"))
        elif _key(d) not in tried:
            out.append(d)
    return out, skipped


def listed(w: World | None = None) -> list[tuple[str, str, bool]]:
    """The widget's list: (kind, faction key, on) for every faction a deal could be offered for."""
    w = w or World()
    F = find_player_faction(w)
    if not F:
        return []
    me, others, border = dip.read(w, F)
    deals, _ = candidates(me, others, border, weak_share())
    deals = [d for d in deals if kind_on(d.kind)]
    off = load_off()
    seen = dict.fromkeys((d.kind, d.target) for d in deals)
    return [(kind, m, m not in off[kind]) for kind, m in seen]


# this turn's deals already offered or found not worth it, kept across assistant restarts:
# {"campaign": [model, turn], "tried": [[kind, target, payer, report line], ...]}
TRIED_FILE = config.RUNS_DIR / "diplomacy_turn.json"


def _key(d: Deal) -> tuple:
    return (d.kind, d.target, d.payer)


def _made(line: str) -> bool:
    return line.endswith(" gold") and ": +" in line


def _tried(w: World) -> dict:
    """{deal key: report line} for this campaign's current turn (another turn or campaign: empty)."""
    cid = [w.s.model, w.s.read().turn]
    try:
        data = json.load(open(TRIED_FILE, encoding="utf-8"))
        if data.get("campaign") == cid:
            return {tuple(t[:3]): t[3] for t in data.get("tried", [])}
    except Exception:
        pass
    return {}


def _record(w: World, d: Deal, line: str) -> None:
    tried = _tried(w)
    tried[_key(d)] = line
    tmp = TRIED_FILE.with_suffix(".tmp")
    json.dump({"campaign": [w.s.model, w.s.read().turn], "tried": [[*k, v] for k, v in tried.items()]},
              open(tmp, "w", encoding="utf-8"), indent=1)
    tmp.replace(TRIED_FILE)


# ------------------------------------------------------------------ the panel
def _list_open(ui: UI) -> bool:
    return ui.first("sortable_list_factions") is not None


def open_list(ui: UI) -> bool:
    """The diplomacy faction list on screen: from the map (button_diplomacy) or from an offer screen (cancel)."""
    if _list_open(ui):
        return True
    back = ui.first("button_cancel", under="button_set_holder")
    if back is not None:
        click(ui, back)
    else:
        b = ui.first("button_diplomacy")
        if b is None:
            return False
        click(ui, b)
    return bool(wait.wait_until(lambda: _list_open(ui), 3.0, "diplomacy faction list", must=False))


def close(ui: UI) -> None:
    """Back to the map: offer screen -> list -> Escape, each confirmed in the UI tree."""
    if ui.root_child("diplomacy_dropdown") is None:
        return
    if not _list_open(ui):
        open_list(ui)
    press("esc")
    wait.wait_until(lambda: ui.root_child("diplomacy_dropdown") is None, 2.0, "diplomacy closed", must=False)


def negotiate(ui: UI, key: str) -> str | None:
    """Open the offer screen with `key`. None when open, else why not."""
    from .build import _scroll_into_clip
    if not open_list(ui):
        return "the diplomacy panel did not open"
    row = wait.wait_until(lambda: ui.first(f"faction_row_entry_{key}"), 2.0, f"{key} listed", must=False)
    if row is None or not _scroll_into_clip(ui, row, "diplomacy faction list"):
        return f"{name(key)} is not in the diplomacy list"
    click(ui, row)
    if not wait.state_is(ui, row, "selected", timeout=1.5, must=False, what=f"{key} selected"):
        return f"{name(key)} could not be selected"
    ok = ui.first("button_ok", under="faction_panel_bottom")
    if ok is None:
        return "no Negotiate button"
    click(ui, ok)
    if not wait.wait_until(lambda: ui.first("list_possible_actions"), 3.0, "offer screen", must=False):
        return "the offer screen did not open"
    return None


def _option(ui: UI, kind: str):
    return ui.first(f"diplomatic_option_{kind}", under="list_possible_actions")


def _offered(ui: UI, kind: str) -> bool:
    return ui.first(f"diplomatic_option_{kind}", under="your_offers_list") is not None


def add_join_war(ui: UI, target: str) -> str | None:
    opt = _option(ui, "join_war")
    if opt is None or (ui.state(opt) or "") == "inactive":
        return "not possible: join war is not offered"
    click(ui, opt)
    lo = wait.wait_until(lambda: ui.first("list_offers", under="diplomacy_hud_request_join_war"), 2.0,
                         "join war list", must=False)
    if lo is None:
        return "the join war list did not open"
    want = name(target)
    row = next((c for c, ids in ui.walk(lo) if ids[-1].startswith("list_box_") and ui.text(c) == want), None)
    box = ui.child(row, "checkbox") if row else None
    if box is None:
        click(ui, ui.first("cancel_request"))
        return f"{want} is not in their join war list"
    if not (ui.state(box) or "").startswith("selected"):
        click(ui, box)
        if not wait.state_is(ui, box, "selected", timeout=1.0, must=False, what=f"{want} ticked"):
            return f"{want} could not be ticked"
    click(ui, ui.first("ok_request"))
    if not wait.wait_until(lambda: _offered(ui, "join_war"), 2.0, "join war offered", must=False):
        return "join war was not added to the offer"
    return None


def add_peace(ui: UI) -> str | None:
    opt = _option(ui, "peace")
    if opt is None or (ui.state(opt) or "") == "inactive":
        return "not possible: peace is not offered"
    lab = ui.child(opt, "label_success_chance_for_action")
    if lab is not None and (ui.state(lab) or "") == "negative":       # UI stop-gap: the AI's value of peace alone
        return f"not possible: they would not take peace even for nothing ({ui.text(lab)})"
    click(ui, opt)
    if not wait.wait_until(lambda: _offered(ui, "peace"), 2.0, "peace offered", must=False):
        return "peace was not added to the offer"
    return None


def deal_positive(ui: UI) -> bool:
    """UI stop-gap: the panel's evaluation of the whole proposal (positive = they accept), memory reader pending."""
    lab = ui.first("label_deal_success_chance")
    return lab is not None and (ui.state(lab) or "") == "positive"


def _amount(ui: UI) -> int | None:
    a = ui.first("amount", under="payment_parent")
    try:
        return int((ui.text(a) or "").replace(",", ""))
    except ValueError:
        return None


def set_amount(ui: UI, x: int) -> int | None:
    """Put x in the payment amount (typed, then taken by an arrow click: x - 200 and the right arrow, or x + 200 and
    the left one). -> the amount shown (the game clamps it to what the payer can give), None when it did not take."""
    for _ in range(2):
        a = ui.first("amount", under="payment_parent")
        if a is None:
            return None
        click(ui, a)
        for _ in range(6):
            press("backspace")
        type_text(str(x - STEP if x > STEP else x + STEP))
        click(ui, ui.first("r_arrow_amount" if x > STEP else "l_arrow_amount"))
        got = wait.wait_until(lambda: (lambda v: v if v is not None and v != x - STEP and v != x + STEP else None)(
            _amount(ui)), 1.0, "payment amount", must=False)
        wait.next_frame(2, ui)                         # the evaluation label follows the amount a frame later
        if got is not None and got <= x:
            return got
    return None


def payment_positive(ui: UI) -> bool:
    """UI stop-gap: the panel's evaluation with this payment (positive = they accept), memory reader pending."""
    lab = ui.first("label_payment_success_chance")
    return lab is not None and (ui.state(lab) or "") == "positive"


def payment_value(ui: UI) -> float | None:
    """UI stop-gap: the panel's evaluation with this payment as a number (shown to 0.1), memory reader pending."""
    lab = ui.first("label_payment_success_chance")
    try:
        return float(ui.text(lab) or "")
    except (TypeError, ValueError):
        return None


def _step_up(ui: UI) -> int | None:
    """One right-arrow click (+200): -> the new amount, None when it did not move (the game's maximum)."""
    before = _amount(ui)
    click(ui, ui.first("r_arrow_amount"))
    got = wait.wait_until(lambda: (lambda v: v if v is not None and v != before else None)(_amount(ui)), 1.0,
                          "payment amount up", must=False)
    wait.next_frame(2, ui)                             # the evaluation label follows the amount a frame later
    return got


def most_they_pay(ui: UI, cap: int) -> int | None:
    """Open the payment window as a demand and find the highest amount they still accept, lowest first (player
    request 2026-10-21, to save time): the window opens at 1 gold, so a refusal costs no probe; then up by 200 with
    the arrow (one click) until they refuse; then the last 200 narrowed with typed amounts, starting from where the
    two evaluations put zero (the payment's value is linear in the amount). The amount is left set. None: not even
    1 gold."""
    opt = _option(ui, "payment")
    if opt is None or (ui.state(opt) or "") == "inactive":
        return None
    click(ui, opt)
    if not wait.wait_until(lambda: ui.first("diplomacy_hud_payments"), 2.0, "payments window", must=False):
        return None
    dem = ui.first("pay_demand")
    if dem is not None and not (ui.state(dem) or "").startswith("selected"):
        click(ui, dem)
        wait.state_is(ui, dem, "selected", timeout=1.0, must=False, what="demand payment")
    wait.next_frame(2, ui)
    if _amount(ui) != 1 and set_amount(ui, 1) != 1:
        return None
    if not payment_positive(ui):
        return None
    lo, hi = 1, None
    seen = [(1, payment_value(ui))]                    # (amount, shown value) at every arrow step
    while hi is None:
        got = _step_up(ui)
        if got is None or got <= lo:                   # the game's maximum: they accept all of it
            return lo if set_amount(ui, lo) == lo else None
        seen.append((got, payment_value(ui)))
        if payment_positive(ui):
            lo = got
            if got >= cap:
                return got
        else:
            hi = got
    # the estimate: where a straight line through every value seen so far crosses zero (least squares: the
    # values are shown to 0.1, and more points pin the line down better than two); then the far edge of its error;
    # then halving what is left
    tries = []
    pts = [(x, v) for x, v in seen if v is not None]
    if len(pts) >= 2:
        n = len(pts)
        mx, mv = sum(x for x, _ in pts) / n, sum(v for _, v in pts) / n
        sxx = sum((x - mx) ** 2 for x, _ in pts)
        slope = sum((x - mx) * (v - mv) for x, v in pts) / sxx if sxx else 0.0
        if slope < 0:
            est = int(mx - mv / slope)
            margin = int(0.05 / -slope / max(1.0, (n / 2) ** 0.5)) + 2
            tries = [est, ("+", margin)]
    last_ok = True
    while hi - lo > 1:
        t = tries.pop(0) if tries else None
        if isinstance(t, tuple):                       # the edge, on the side the estimate pointed to
            m = (lo + t[1]) if last_ok else (hi - t[1])
        else:
            m = t if t is not None else (lo + hi) // 2
        if not lo < m < hi:
            m = (lo + hi) // 2
        got = set_amount(ui, m)
        if got is None:
            return None
        last_ok = payment_positive(ui)
        if last_ok:
            lo = got
        else:
            hi = got
    if set_amount(ui, lo) != lo or not payment_positive(ui):
        return None
    return lo


def _cancel_payment(ui: UI) -> None:
    c = ui.first("cancel_payments")
    if c is not None:
        click(ui, c)
        wait.gone(ui, "diplomacy_hud_payments", timeout=1.0, must=False)


def _answer(ui: UI) -> None:
    """Close the AI's answer (button_accept), then back to the faction list."""
    b = wait.wait_until(lambda: ui.first("button_accept", under="button_set_holder"), 3.0, "their answer", must=False)
    if b is not None:
        click(ui, b)
        wait.gone(ui, b, timeout=1.5, must=False)
    open_list(ui)


def offer(ui: UI, w: World, F: int, d: Deal) -> tuple[bool, str]:
    """One deal: build it, find the most they pay, send it, confirm it in memory. -> (made, report line)."""
    whom = d.payer
    why = negotiate(ui, whom)
    if why:
        return False, f"{d.line()}: {why}"
    why = add_join_war(ui, d.target) if d.kind == "join_war" else add_peace(ui)
    if why:
        open_list(ui)
        return False, f"{d.line()}: {why}"
    if not deal_positive(ui):
        open_list(ui)
        return False, f"{d.line()}: not possible: they would not take it even for nothing"
    gold = most_they_pay(ui, d.treasury)
    if not gold:
        _cancel_payment(ui)
        open_list(ui)
        return False, f"{d.line()}: not possible: they would not pay for it"
    click(ui, ui.first("ok_payments"))
    wait.gone(ui, "diplomacy_hud_payments", timeout=1.5, must=False)
    if not deal_positive(ui):
        open_list(ui)
        return False, f"{d.line()}: not possible: the deal with {gold} gold turned negative"
    send = ui.first("button_send", under="button_set_holder")
    if send is None or (ui.state(send) or "") == "inactive":
        open_list(ui)
        return False, f"{d.line()}: the Send button is greyed out"
    t0 = dip.treasury(w, F)
    M = next((o for o in dip.relations(w, F) if w.faction_name(o) == d.target), None)
    want_war = d.kind == "join_war"

    def effect():
        r = dip.relations(w, F, {M}).get(M) if M else None
        return r is not None and r.war == want_war and dip.treasury(w, F) > t0

    st, _v = commands.act(w.pm, lambda: click(ui, send) and None, effect)
    _answer(ui)
    if st == "done":
        return True, f"{d.line()}: +{dip.treasury(w, F) - t0} gold"
    return False, f"{d.line()}: {'refused by the game' if st == 'refused' else commands.WHY.get(st) or st}"


# ------------------------------------------------------------------ the step
def run(log=print) -> str:
    w = World()
    F = find_player_faction(w)
    if F is None:
        return "player faction not found"
    deals, _skipped = plan(w, F)
    if not deals:
        return "no deal to offer"
    ui = UI(w.s)
    ui.find_root()
    done, failed = [], []
    with game_focus():
        try:
            for _ in range(MAX_DEALS):
                deals, _skipped = plan(w, F)
                if not deals:
                    break
                d = deals[0]
                made, line = offer(ui, w, F, d)
                _record(w, d, line)
                log(line)
                (done if made else failed).append(line)
        finally:
            close(ui)
    return "; ".join(done + failed) or "no deal to offer"


def missed() -> list[str]:
    """The memory check after the step: the plan made again from memory. A deal still open that the step did not
    get to is missed; one it tried and the AI turned down is reported with its reason."""
    w = World()
    F = find_player_faction(w)
    if not F:
        return []
    me, others, border = dip.read(w, F)
    deals, _ = candidates(me, others, border, weak_share())
    deals = [d for d in deals if kind_on(d.kind)]
    off, tried = load_off(), _tried(w)
    made = {k[1] for k, line in tried.items() if _made(line)}
    out = []
    for d in deals:
        if d.target in off[d.kind] or d.target in made:
            continue
        line = tried.get(_key(d))
        out.append(f"{d.line()}: not offered" if line is None else line)   # the runner keeps "not possible" apart
    return out


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if cmd == "plan":
        deals, skipped = plan()
        for d in deals:
            print(f"offer  {d.line()}  (their treasury {d.treasury})")
        for kind, k, why in skipped:
            print(f"skip   {kind:8s} {name(k)}: {why}")
        if not deals and not skipped:
            print("nothing to offer")
    elif cmd == "run":
        print(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
