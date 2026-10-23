"""Turn-start popups, from the UI tree.

Every popup is a visible child of the UI root that is not part of the normal campaign HUD.
  - event notices (ids containing "event") are closed with their own accept/close button: safe, they only
    report something that already happened;
  - anything that asks for a decision (AI diplomacy offers, pre-battle screens, dilemmas, message boxes,
    and any popup not recognised yet) is left for the player: the assistant waits and says what is open.
An unrecognised panel is shown by its id. When it is harmless, the player clicks "Ignore <id>" in the app once:
the id goes into strategy/popup_ignore.json and never blocks a pass again.
"""
from __future__ import annotations
import json

from bot import config
from bot.focus import game_focus
from bot.sensor.ui import UI
from tools import wait
from tools.ui import click

IGNORE_FILE = config.STRATEGY_DIR / "popup_ignore.json"

NORMAL = {
    "ai_turns",            # AI turn progress bar (only during end turn)
    "ai_attack_targets_parent", "3d_ui_parent", "mission_indicator_parent", "endgame_scenarios_holder",
    "hud_campaign", "menu_bar", "panel_manager", "under_advisor_docker", "tooltip_default", "black_fade",
    "tutorial_halo_group",  # tutorial highlight around a HUD element: never a decision (seen 2026-10-16)
    "mp_start_turn_popup",  # multiplayer "Your Turn" banner: no buttons, fades by itself (held a pass 2026-10-18)
    "mp_pending_action_blocking_msg",   # another player's battle or decision: waited out by runner.players_turn and
                                        # tools.ui.wait_for_other_players, never the player's decision
    "highlight_dummy", "text_pointer_parent",   # parts of a scripted tour (fullscreen_highlight is the one reported)
    "advice_interface", "help_panel", "saving_icon", "qa_console", "campaign_space_bar_options",
    "targeting_interface_dimming", "character_map_path_icons", "units_panel", "resources_bar",
    # panels the assistant itself opens
    "settlement_panel", "character_details_panel", "technology_panel", "units_recruitment",
    "recruitment_docker", "diplomacy_dropdown_hidden",
    # cinematics are not popups: while one plays nothing is sent at all (bot/sensor/ui.py UI.cinematic)
    "fullscreen_movie", "cinematic_bars", "scripted_movie_panel",
}
DECISION_HINTS = {
    "diplomacy_dropdown": "an AI diplomacy offer",
    "popup_pre_battle": "a battle",
    "popup_battle_results": "battle results",
    "dilemma": "a dilemma",
    "popup_message_box": "a confirmation box",
    "esc_menu": "the game menu",
    # significant global events: left for the player to read and close (player rule 2026-10-17), never ignorable
    "endgame": "a global event to read",               # dlc29_endgame_crisis_scenarios (the Chaos Invasion)
    # a scripted tour of a panel (first opening of Thanquol's Masterplans, 2026-10-17): it dims the screen and takes
    # the clicks; the player steps through it or closes it
    "fullscreen_highlight": "a guided tour (step through it or close it)",
    "event_movie_panel": "a global event to read",     # an event with a movie window
}
# event notices about significant global events, never closed by the assistant: the endgame chain (its incidents are
# keyed *_episode_*, e.g. wh3_dlc29_chaos_invasion_episode_foreshadow_1 "Chaos Stirs"), by component id, and by what
# the notice says. ("movie" is no sign: the ordinary events layout has a dy_movie_frame too.)
SIGNIFICANT = ("episode", "endgame", "end_times")
SIGNIFICANT_TEXT = ("chaos invasion", "end times", "endgame", "archaon")
NAMES = {"agent_options": "a Hero Actions panel",      # known panels that are not decisions (they can be ignored)
         "dlc29_skv_chaotic_plans": "the Masterplans panel (Thanquol)"}
CLOSE_BUTTONS = ("button_accept", "button_tick", "button_close", "button_ok", "button_dismiss")
MAX_NOTICES = 24              # notices closed per check at most (they stack at turn start)
CLOSE_TIMEOUT = 5.0           # s: a clicked notice should be gone (or show the next stacked notice) by then;
                              # multiplayer closes take seconds (2026-10-18: 2 s timed out, then closed)
RECLICK_S = 8.0               # a notice just clicked is not clicked again for this long (it may still be closing)
_CLICKED: dict = {}           # (id, title) -> when its close button was clicked
import time as _time
NEXT_NOTICE_MS = 150          # after the last notice closed: no root panel appearing for this long = none is coming


def ignored() -> set[str]:
    """Root-child ids the player marked as harmless (strategy/popup_ignore.json: {"ignore": [ids]})."""
    try:
        return set(json.loads(IGNORE_FILE.read_text(encoding="utf-8")).get("ignore", []))
    except (OSError, ValueError, AttributeError):
        return set()


def add_ignored(cid: str) -> None:
    ids = sorted(ignored() | {cid})
    data = {"_doc": "Root-level panels the assistant treats as part of the normal HUD (added with the app's "
                    "'Ignore' button). Remove an id to make it block the turn-start pass again.",
            "ignore": ids}
    tmp = IGNORE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    from tools.fileio import replace as _replace
    _replace(tmp, IGNORE_FILE)


def scan(ui: UI | None = None) -> list[tuple[int, str]]:
    ui = ui or UI()
    if ui.find_root() is None:
        raise RuntimeError("game UI not found in memory")
    skip = NORMAL | ignored()
    return [(c, cid) for c, cid in ui.root_children()
            if cid not in skip and not "tooltip" in cid.lower()           # hover tooltips are never popups
            and not feed_preview(ui, c, cid)]


def feed_preview(ui: UI, c: int, cid: str) -> bool:
    """The Event Messages feed's hover preview: an "events" panel with a link_arrow pointing at the feed entry.
    It fades out when the mouse leaves but stays flagged visible (2026-10-18: a faded "Technology Researched"
    preview held Build & End Turn on "GLOBAL EVENT" with nothing on screen). Never a popup. A notice with a close
    button is a real one, arrow or not."""
    return (cid == "events" and ui.child(c, "link_arrow", visible_only=True) is not None
            and _close_button(ui, c) is None and not needs_choice(ui, c))


def needs_choice(ui: UI, c: int) -> bool:
    """An 'events' popup can be a plain notice or a choice (dilemma). Choices have dilemma layouts or
    choice buttons: those are always left to the player."""
    for _b, n, _r in ui.nodes(c):
        if "dilemma" in n or n == "choice_button" or "ChoiceDetailRecord" in n:
            return True
    return False


def significant(ui: UI, c: int) -> bool:
    """An event notice about a significant global event (SIGNIFICANT): the player reads and closes it."""
    for b, n, _r in ui.nodes(c):
        t = (ui.text(b) or "").lower()
        if any(k in n.lower() for k in SIGNIFICANT) or any(k in t for k in SIGNIFICANT_TEXT):
            return True
    return False


def _sig(ui: UI, cid: str, c: int) -> tuple:
    """A notice's identity for the re-click guard: its id and first texts (2026-10-18: stacked notices share a title,
    "Enemy Killed In Battle", one per enemy, and the title alone left the next one open)."""
    texts = tuple(t for b, _n, _r in ui.nodes(c) if (t := (ui.text(b) or "").strip()) and len(t) < 120)[:4]
    return (cid,) + texts


def title(ui: UI, c: int) -> str:
    return next((t for b, _n, _r in ui.nodes(c) if (t := (ui.text(b) or "").strip()) and len(t) < 80), "")


def known(cid: str) -> bool:
    return any(k in cid for k in DECISION_HINTS)


def describe(cid: str) -> str:
    for k, v in DECISION_HINTS.items():
        if k in cid:
            return f"{v} ({cid})"
    if cid in NAMES:
        return f"{NAMES[cid]} ({cid})"
    return f"unknown panel '{cid}'"


def is_event(cid: str) -> bool:
    return "event" in cid and not any(k in cid for k in DECISION_HINTS)


def _close_button(ui: UI, c: int) -> int | None:
    for b, n, _r in ui.nodes(c):
        if n in CLOSE_BUTTONS:
            return b
    return None


def diplomacy_notice(ui: UI, c: int) -> int | None:
    """The OK button of a diplomacy panel that only tells something (2026-10-22, turn 57: "They have ended their non-
    aggression pact with you", Ikit Claw, held the other factions' turns as "an AI diplomacy offer"): its shown button
    set (offers_list_panel/button_set_holder/button_setN) holds button_accept alone. An offer's set has Send, Counter-
    offer, Cancel or Decline as well and is always left to the player. None when it is not such a notice."""
    holder = ui.first("button_set_holder", under=c)
    if holder is None:
        return None
    for bs in ui.children(holder):
        if not ui.effective_visible(bs):
            continue
        btns = [(b, ui.id(b)) for b in ui.children(bs) if (ui.id(b) or "").startswith("button")
                and ui.effective_visible(b)]
        if len(btns) == 1 and btns[0][1] == "button_accept":
            return btns[0][0]
    return None


def _closable(ui: UI) -> list[tuple[int, str, int]]:
    out = []
    for c, cid in scan(ui):
        if cid == "diplomacy_dropdown" and (ok := diplomacy_notice(ui, c)) is not None:
            out.append((c, cid, ok))
            continue
        if not is_event(cid) or needs_choice(ui, c) or significant(ui, c):
            continue
        btn = _close_button(ui, c)
        if btn is not None:
            out.append((c, cid, btn))
    return out


def _shows(ui: UI, c: int) -> tuple:
    """The texts a notice shows: the same panel can be re-used for the next stacked notice."""
    return tuple(t for b, _n, _r in ui.nodes(c) if (t := ui.text(b)))


def dismiss_events(ui: UI | None = None) -> list[str]:
    """Close event notices, one at a time (they can stack), all inside one game_focus. Each click is followed by a
    wait until that notice is gone or shows the next stacked one; after the last, a short wait that no further panel
    is sliding in. Returns the ids closed. A notice that does not close raises WaitTimeout (the pass is skipped)."""
    ui = ui or UI()
    closed: list[str] = []
    # the player's standing answer to one dilemma (assist/rites.py): the Dominating Scheme's Verminlord choice
    from . import rites
    ev = ui.root_child("events")
    if ev and any(ids[-1].endswith(rites.VERMINLORD_DILEMMA + rites.WARPSEER_CHOICE) for _c, ids in ui.walk(ev)):
        with game_focus():
            if rites.answer_verminlord_dilemma(ui, timeout=0.5) == "taken":
                closed.append("Verminlord choice: Warpseer")
    focus = None
    try:
        for _ in range(MAX_NOTICES):
            todo = _closable(ui)
            if not todo and closed:
                wait.root_children_stable(ui, ms=NEXT_NOTICE_MS, timeout=3, must=False)
                todo = _closable(ui)
            if not todo:
                break
            if focus is None:
                focus = game_focus()
                focus.__enter__()
            todo = [t for t in todo if _time.time() - _CLICKED.get(_sig(ui, t[1], t[0]), 0) > RECLICK_S]
            if not todo:
                break
            c, cid, btn = todo[0]
            before = _shows(ui, c)
            if cid == "diplomacy_dropdown":
                # still OK alone a moment later (an offer's buttons could be filling in), then logged: what was
                # closed, to check it was never an offer
                _time.sleep(0.4)
                if diplomacy_notice(ui, c) != btn:
                    break
                log_open(ui, None, "closing a diplomacy notice")
            _CLICKED[_sig(ui, cid, c)] = _time.time()
            # multiplayer (2026-10-18): a notice closes some seconds after its button, once the game has synced
            # with the other players. Paced by the game (bot/sensor/commands.py): a click that wrote a command waits
            # for the close however long the sync takes; one that wrote none and closed nothing did not reach the
            # game. The notice is never clicked again meanwhile (RECLICK_S).
            from bot.sensor import commands
            st, _v = commands.act(ui.pm, lambda: click(ui, btn) and None,
                                  lambda: not ui.effective_visible(btn) or _shows(ui, c) != before,
                                  cap=max(CLOSE_TIMEOUT, commands.EFFECT_CAP_S))
            if st == "done":
                closed.append(cid)
            else:
                break
    finally:
        if focus is not None:
            focus.__exit__(None, None, None)
    return closed


def log_open(ui: UI, turn, where: str) -> None:
    """Append every popup still open to runs/popups_seen.jsonl: its id, buttons and texts, and how the rules here
    see it. Player report 2026-10-17: some turn-start notices were left open; this tells which, next time."""
    import time as _t
    rows = []
    for c, cid in scan(ui):
        rows.append({"id": cid, "event": is_event(cid), "choice": needs_choice(ui, c), "significant": significant(ui, c),
                     "buttons": sorted({n for _b, n, _r in ui.nodes(c) if n.startswith("button")})[:20],
                     "texts": [t for b, _n, _r in ui.nodes(c) if (t := ui.text(b)) and len(t) < 120][:8]})
    if not rows:
        return
    try:
        with open(config.RUNS_DIR / "popups_seen.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": _t.time(), "turn": turn, "where": where, "open": rows}, ensure_ascii=False) + chr(10))
    except OSError:
        pass


def open_decisions(ui: UI | None = None) -> list[tuple[str, str, bool]]:
    """(id, description, ignorable) for each open popup that needs the player. Only unknown panels can be
    ignored: diplomacy offers, battles, dilemmas and message boxes always wait for the player."""
    ui = ui or UI()
    out = []
    for c, cid in scan(ui):
        if cid == "diplomacy_dropdown" and diplomacy_notice(ui, c) is not None:
            continue                                   # a diplomacy notice: closed like an event notice
        if not is_event(cid):
            d = describe(cid)
            if d.startswith("a global event") and (t := title(ui, c)):
                d = f"a global event to read: {t}"
            out.append((cid, d, not known(cid)))
        elif needs_choice(ui, c):
            out.append((cid, f"a dilemma (choice event, {cid})", False))
        elif significant(ui, c):
            out.append((cid, f"a global event to read: {title(ui, c) or cid}", False))
        elif not any(n.startswith("button") for _b, n, _r in ui.nodes(c)):
            # a passing notice: no button at all, it fades out by itself after a few seconds (2026-10-18, turn 2:
            # "Oakenhammer has been taken" held Build & End Turn on "GLOBAL EVENT"; also "Enemy Killed In Battle").
            # Story and world-event panels always have at least their Continue button (button_txt).
            continue
        elif _close_button(ui, c) is None:
            # a notice with no close button the assistant knows: story and world-event panels have only "Continue"
            # (2026-10-17, Thanquol's turn 2: "Act I - Favoured by the Horned Rat", a modal incident_large panel,
            # stayed open and the pass clicked the HUD under it for nothing). The player reads and closes it.
            out.append((cid, f"a story event to read: {title(ui, c) or cid}", False))
    return out


def decisions(ui: UI | None = None) -> list[str]:
    """Human-readable list of open popups that need the player."""
    return [d for _cid, d, _ig in open_decisions(ui)]


# ------------------------------------------------------------------ AI offers (standing answer, 2026-10-22)
# strategy/automation.json "ai_offers" (a widget setting): "ask" leaves every AI diplomacy offer to the player (as
# before); "accept_gifts" accepts an offer that asks nothing of the player beyond a Non-Aggression Pact or a Trade
# Agreement and gives only gold, a Non-Aggression Pact or a Trade Agreement (turn 64: Gorbad Ironclaw's 600 gold for a
# Non-Aggression Pact held the AI turns until answered). Anything else is still left to the player.
# UI stop-gap: the offer's terms are read from the diplomacy panel (diplomatic_option_<type> under their_offers /
# your_offers); a memory reader for pending diplomatic proposals is pending.
GIFT_TERMS = {"payment", "nonaggression_pact", "trade_agreement"}
GIVE_TERMS = {"nonaggression_pact", "trade_agreement"}


def offer_terms(ui: UI, c: int) -> tuple[set, set] | None:
    """(what they ask of the player, what they give) of an open AI offer, as option types; None when the panel is
    not an incoming offer (its button set has no Accept and Cancel) or a side cannot be read."""
    holder = ui.first("button_set_holder", under=c)
    shown = set()
    for bs in (ui.children(holder) if holder is not None else []):
        if ui.effective_visible(bs):
            shown |= {ui.id(b) for b in ui.children(bs) if ui.effective_visible(b)}
    if not {"button_accept", "button_cancel"} <= shown:
        return None
    ask, give = set(), set()
    for comp, path in ui.walk(c):
        cid = path[-1] if path else ""
        if not cid.startswith("diplomatic_option_") or not ui.effective_visible(comp):
            continue
        kind = cid[len("diplomatic_option_"):]
        if "your_offers" in path:
            ask.add(kind)                       # "Their Demands": what the player would give
        elif "their_offers" in path:
            give.add(kind)
    return (ask, give) if ask or give else None


def is_gift(ask: set, give: set) -> bool:
    """The "accept_gifts" rule: they give something, and ask and give only the harmless terms."""
    return bool(give) and ask <= GIVE_TERMS and give <= GIFT_TERMS


def offer_rule() -> str:
    try:
        return json.load(open(config.STRATEGY_DIR / "automation.json", encoding="utf-8")).get("ai_offers", "ask")
    except Exception:
        return "ask"


def answer_offer(ui: UI) -> str | None:
    """Accept an open AI offer the standing answer covers (offer_rule). -> what was done, or None (left to the
    player). Paced by the game: the Accept click must write a command and close the panel (memory: the UI tree)."""
    if offer_rule() != "accept_gifts":
        return None
    c = ui.root_child("diplomacy_dropdown")
    if not c or not ui.effective_visible(c):
        return None
    terms = offer_terms(ui, c)
    if terms is None:
        return None
    ask, give = terms
    if not is_gift(ask, give):
        return None
    btn = ui.first("button_accept", under=c)
    if btn is None:
        return None
    _time.sleep(0.4)                            # the same terms a moment later (the panel fills in over frames)
    if offer_terms(ui, c) != terms:
        return None
    log_open(ui, None, f"accepting an AI offer (they ask {sorted(ask)}, give {sorted(give)})")
    from bot.sensor import commands
    with game_focus():
        st, _v = commands.act(ui.pm, lambda: click(ui, btn) and None, lambda: not ui.effective_visible(btn),
                              cap=max(CLOSE_TIMEOUT, commands.EFFECT_CAP_S))
    if st != "done":
        return None
    return f"accepted an AI offer: they asked {', '.join(sorted(ask)) or 'nothing'}, gave {', '.join(sorted(give))}"
