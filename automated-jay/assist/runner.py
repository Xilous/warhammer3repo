"""The assistant loop: at the start of every player turn, do every automation, then say "your turn".

    python -X utf8 -m assist.runner              # widget + loop; Ctrl+C in the terminal to stop
    python -X utf8 -m assist.runner --once       # run the automations once now, no widget

New turn = the campaign turn counter in memory went up. A pass only starts when it is really the player's
turn: a campaign is loaded, the End Turn button is shown and enabled and no AI-turn panel is up (in sequential
multiplayer the round counter moves while another player is still moving), and the player has not touched the
mouse or keyboard for IDLE_SECONDS. Automations run in a fixed order and each one is independent: a failure is
shown on the widget and the next one still runs.
Focus: the game is raised only while an automation sends input; afterwards focus returns to the
terminal (bot/focus.py). If the player switches away from the game during a pass, the next input raises
InputAborted: the pass stops at once ("interrupted"), and "Run now" redoes it.
The game may be closed, restarted or sent back to the main menu at any time: the sensor re-attaches by itself,
and a loaded save is a "campaign change" (the assistant acts from the next turn).
Status: every widget update is also written to %LOCALAPPDATA%/automated-jay/state.json ({"state", "headline", "detail", "turn",
"time"}), swapped in atomically, for the player and for tools (tools/turn_driver.py --external).
"""
from __future__ import annotations
import inspect
import json
import sys
import threading
import time
import traceback
import os
from datetime import datetime
from pathlib import Path

from bot import config
from bot.focus import CinematicPlaying, InputAborted, idle_seconds, return_to_terminal
from bot.sensor.memory import MemorySensor
from bot.sensor.ui import UI
from tools import timing
from . import army_builder, build, masterplans, rites, skills, tech, workshop

# Turn-start settle, by condition (was a fixed 4 s): the pass starts once the turn-start camera pan has finished (the
# map point at the screen centre moves less than SETTLE_CAMERA_PX per frame for SETTLE_CAMERA_MS) AND no root panel
# (event popup) has appeared or disappeared for SETTLE_PANELS_MS, with the game rendering. Popups that slide in later
# are still caught: the popup check runs right before the pass, and every step waits on its own panels.
SETTLE_CAMERA_PX = 0.1
SETTLE_CAMERA_MS = 250
SETTLE_PANELS_MS = 500
SETTLE_TIMEOUT = 20.0         # s: never settled (the player keeps panning): go on, the idle check still applies
POLL_SECONDS = 2.0            # loop period while nothing is about to happen
POLL_NOTICES = 0.5            # during the player's turn: how often to look for event notices to close
POLL_FAST = 0.1               # while a turn is pending or other factions are moving: notice the turn start at once
END_TURN_WAIT_S = 8.0         # after Shift+Enter, until the game runs another faction's turn (took ~2.3 s in the logs)
END_TURN_TRIES = 2            # a key the game did not take is pressed once more
MP_PENDING_WAIT_S = 180.0     # multiplayer: how long End Turn waits out another player's battle ("pending action")
VERIFY_ROUNDS = 2            # verification runs per step (each one that had to redo something is followed by another)
IDLE_SECONDS = 3.0            # the player must have left mouse and keyboard alone this long before a pass
LOST_AFTER = 2                # polls in a row without a campaign before the turn bookkeeping starts over
# Outside OneDrive: the project lives in a synced folder, and OneDrive locks a file while it syncs it, which made
# the swap below fail for seconds at a time (seen 2026-10-16: the widget said YOUR TURN, state.json AUTOMATING).
STATE_FILE = Path(os.environ.get("LOCALAPPDATA") or config.RUNS_DIR) / "automated-jay" / "state.json"

STEP_FNS = {
    "rites": rites.run,                  # commandments + the Dominating Scheme: before any gold is spent (player rule)
    "workshop": workshop.run,            # the Stormfiend Ratling Cannon upgrades, as soon as they can be bought
    "tech": tech.run,
    "skills": skills.run,
    "masterplans": masterplans.run,      # Thanquol: Steal-Takes and Clan Scruten Secrets (end of turn only, 2026-10-18)
    "buildings": build.run,             # player rule: building upgrades take precedence over refilling armies
    "army": army_builder.run,            # recruits with whatever gold the building step left
}
# Player decision (2026-10-16): building moves to the end of the turn ("Build & End Turn" in the app), so that
# settlements taken during the turn are built on the same turn; the army step goes with it, after the buildings, so
# that buildings keep precedence over armies for the gold. strategy/automation.json "schedule" overrides this.
DEFAULT_SCHEDULE = {"turn_start": ["rites", "workshop", "tech", "skills"],
                    "end_turn": ["rites", "workshop", "tech", "skills", "masterplans", "buildings", "army"]}
# masterplans at the end of the turn only (player decision, 2026-10-18): Underlings the player sends on a Kill-Stab during
# the turn are never taken for a Steal-Take first; before buildings, so a completed Steal-Take's gold is spent this turn
# tech and skills at both: a campaign's first turn has no turn start to act on (2026-10-17), and unspent skill points
# make End Turn stop at the game's warning; with nothing to do they send no input
AUTOMATION = config.STRATEGY_DIR / "automation.json"


def schedule() -> dict[str, list[str]]:
    """Which steps run at turn start and which at "Build & End Turn" (automation.json "schedule", read every time so
    an edit applies at once; unknown step names are dropped)."""
    try:
        sch = json.load(open(AUTOMATION, encoding="utf-8")).get("schedule") or {}
    except Exception:
        sch = {}
    return {k: [n for n in sch.get(k, v) if n in STEP_FNS] for k, v in DEFAULT_SCHEDULE.items()}


def all_steps() -> list[str]:
    """Every scheduled step in pass order: turn-start steps, then end-of-turn steps (--once and the test harness)."""
    sch = schedule()
    return sch["turn_start"] + [n for n in sch["end_turn"] if n not in sch["turn_start"]]


def write_state(state: str, headline: str, detail: str, turn: int | None) -> None:
    """runs/state.json, written to a temp file and swapped in, so a reader never sees half a file. On Windows
    the swap fails while a reader has the old file open: retry briefly."""
    data = {"state": state, "headline": headline, "detail": detail, "turn": turn,
            "time": datetime.now().isoformat(timespec="seconds")}
    text = json.dumps(data, ensure_ascii=False, indent=1)
    tmp = STATE_FILE.with_suffix(".tmp")
    for _ in range(20):
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(STATE_FILE)
            return
        except OSError:
            time.sleep(0.05)
    try:                                   # the swap kept failing: a plain write is better than a stale state
        STATE_FILE.write_text(text, encoding="utf-8")
    except OSError:
        print(f"WARNING: could not write {STATE_FILE}", flush=True)


def read_state() -> dict:
    """The last status the runner wrote ({} when there is none yet)."""
    for _ in range(5):
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            time.sleep(0.05)
    return {}


# Simultaneous multiplayer (2026-10-18, Ikit Claw with a friend): every human faction stays in the "whose turn" list
# until all of them have ended the turn, so memory alone cannot tell "ended, waiting for the others" from "still
# moving". The player list at the top left (mp_player_list) shows a ready tick (icon_ready) beside each player who
# ended. Its rows do not say which one is local: it is the one whose tick came on when the assistant pressed End Turn.
MP_ME = {"name": None}


def mp_ready(ui: UI) -> dict[str, bool]:
    """Multiplayer: each player's name in the player list -> their ready tick (ended the turn, waiting for the
    others). Empty outside multiplayer (no player list shown)."""
    lst = ui.cached("mp_player_list", under="hud_campaign")
    out = {}
    if lst is None:
        return out
    for row in ui.children(lst):
        lab = ui.child(row, "label_player")
        if lab is None or not ui.effective_visible(row):    # (template_entry: the hidden row the game copies)
            continue
        icon = ui.child(row, "icon_ready")
        out[ui.text(lab) or ""] = bool(icon is not None and ui.effective_visible(icon))
    return out


def mp_waiting(ui: UI) -> bool:
    """The player ended the turn and the other players have not yet (multiplayer)."""
    return bool(MP_ME["name"]) and mp_ready(ui).get(MP_ME["name"]) is True


def players_turn(ui: UI) -> tuple[bool, str]:
    """(True, "") when the player can act on the campaign map now, else (False, why). Root panels plus one cached
    lookup: cheap enough to poll."""
    from bot.sensor import turn as turn_mem
    mine, why = turn_mem.players_turn(ui.s)        # authoritative: the faction the campaign runs a turn for
    if not mine:                                   # (the ai_turns panel hides for moments while the AI moves)
        return False, why
    if ui.find_root() is None:
        return False, "game UI not found"
    top = dict((cid, c) for c, cid in reversed(ui.root_children()))      # visible root panels, first wins
    if (cin := ui.cinematic()):
        return False, f"a cinematic is playing ({cin}); nothing is clicked until it is over"
    if "hud_campaign" not in top:
        return False, "campaign map not shown"
    if "ai_turns" in top:
        return False, "other factions are moving"
    if mp_waiting(ui):
        return False, "you ended the turn: waiting for the other players"
    end = ui.cached("button_end_turn", under="hud_campaign")
    if end is None:
        return False, "End Turn button not shown"
    st = ui.state(end) or ""
    if st.startswith("selected"):                  # multiplayer: pressed, waiting for the others (watched 2026-10-18)
        return False, "you ended the turn: waiting for the other players"
    if st.startswith(("inactive", "disabled")):
        if any(plans_at_max_alarm(ui.s).values()):
            return True, ""                        # the game holds End Turn until that plan is resolved (below)
        return False, f"End Turn button is {st}"
    return True, ""


def plans_at_max_alarm(sensor) -> dict[str, list[str]]:
    """{"economic": [regions], "military": [regions]}: Masterplans at maximum Alarm, from memory. The game greys out
    End Turn until each is completed or abandoned (2026-10-18, turn 17: Mount Gunbad at Alarm 4/4, End Turn
    "inactive", and the assistant took that for "not your turn" and never started the pass)."""
    out = {"economic": [], "military": []}
    try:
        from bot.sensor import masterplans as mem
        from bot.sensor.world import World
        st = mem.read(World(sensor))
    except Exception:
        return out
    for p in (st.plans if st else []):
        if p.alarm_max and p.alarm >= p.alarm_max and p.type in out:
            out[p.type].append(p.region)
    return out


def settle(ui: UI, cancel=lambda: False, timeout: float = SETTLE_TIMEOUT) -> tuple[bool | None, float]:
    """Wait until the turn start has settled: camera still and no root panel coming or going (see SETTLE_*).
    Returns (True, seconds) when settled, (False, s) when cancelled, (None, s) on timeout."""
    from bot.sensor.camera import read_camera
    import numpy as np
    t0 = time.monotonic()
    cam_since = panels_since = t0
    prev_cam = None
    prev_panels = None
    while time.monotonic() - t0 < timeout:
        if cancel():
            return False, time.monotonic() - t0
        now = time.monotonic()
        try:
            cam = read_camera(ui.s)
            if prev_cam is not None:
                gx, gy = prev_cam.ground_at_center()
                p = cam.project(gx, gy)
                if p is None or float(np.hypot(p[0] - 960, p[1] - 540)) >= SETTLE_CAMERA_PX:
                    cam_since = now
            prev_cam = cam
        except Exception:                    # noqa: BLE001  (camera block unreadable for a moment: not settled)
            prev_cam, cam_since = None, now
        panels = tuple(cid for _c, cid in ui.root_children())
        if panels != prev_panels:
            prev_panels, panels_since = panels, now
        if (now - cam_since) * 1000 >= SETTLE_CAMERA_MS and (now - panels_since) * 1000 >= SETTLE_PANELS_MS:
            return True, now - t0
        try:
            from tools import wait
            wait.next_frame(1, ui, timeout=2.0)      # sample once per rendered frame
        except Exception:                    # noqa: BLE001  (not rendering: not settled)
            time.sleep(0.01)
    return None, time.monotonic() - t0


class Runner:
    def __init__(self, widget=None) -> None:
        self.widget = widget
        # a restarted copy finishes this turn's pass if the old copy left it unfinished: what the old copy last wrote,
        # read now, before this copy's first status overwrites it (2026-10-17: it was read after, so never acted on)
        self.prev_state = read_state() if os.environ.get("AJ_RESTARTED") else {}
        self.paused = False
        self.busy = threading.Lock()          # held only while a pass sends input
        self.stop = threading.Event()
        self.mem = MemorySensor()             # never fails: with no game it waits for one
        self.ui = UI(self.mem)
        self.last_turn: int | None = None     # turn counter last seen
        self.model: str | None = None         # campaign model last seen (a new one = a save was loaded)
        self.pending: int | None = None       # turn whose pass is still to do
        self.done_turn: int | None = None     # turn whose pass is done (by the loop or Run now)
        self.end_done = None                  # (model, turn) ended with "Build & End Turn" (else the next turn start
                                              # catches up on the end-of-turn steps)
        self.no_campaign = 0
        self.campaign_lost = False            # no campaign was seen: the next one is a "campaign change"
        self.gate_since: float | None = None
        self.my_turn = True                   # last players_turn() result seen by the loop (poll fast when False)
        self.phases: dict[str, float] = {}    # pre-pass phase times for the timing log
        self.turn_seen_at: float | None = None
        self._last_post = None
        self.rail_steps: dict[str, str] = {}  # the overlay's Turn rail: step -> done/active/pending/later/failed
        config.RUNS_DIR.mkdir(exist_ok=True)
        self.log = open(config.RUNS_DIR / f"assistant-{datetime.now():%Y%m%d}.jsonl", "a", encoding="utf-8")

    def post(self, state: str, headline: str, detail: str = "", turn: int | None = None) -> None:
        turn = self.last_turn if turn is None else turn
        key = (state, headline, detail, turn)
        if key == self._last_post:            # polled states repeat every 2 s: say it once
            return
        self._last_post = key
        print(f"[{datetime.now():%H:%M:%S}] {headline} {detail}".rstrip(), flush=True)
        write_state(state, headline, detail, turn)
        if self.widget:
            self.widget.post(state, headline, detail)

    def rail(self, reset: bool = False, **changes) -> None:
        """The overlay's Turn rail (assist/rail.py): one status per step. reset: a new turn (end-of-turn steps
        "later", the rest pending)."""
        if reset:
            end = set(schedule()["end_turn"]) - set(schedule()["turn_start"]) | {"end"}
            self.rail_steps = {k: ("later" if k in end else "pending")
                               for k in ("events", "rites", "workshop", "tech", "skills", "masterplans", "buildings",
                                         "army", "end")}
        self.rail_steps.update(changes)
        if self.widget and hasattr(self.widget, "post_steps"):
            self.widget.post_steps(dict(self.rail_steps))

    def offer_ignore(self, ids: list[str]) -> None:
        if self.widget and hasattr(self.widget, "post_ignorable"):
            self.widget.post_ignorable(ids)

    def restart(self) -> None:
        """The app's Restart (player request 2026-10-17): start a fresh copy of the assistant, which loads the latest
        code and settings, and end this one. Never while a pass runs. The new copy starts "mid-turn" (acts from the
        next turn start; Run now / Build & End Turn work at once)."""
        import os
        import subprocess
        if not self.busy.acquire(blocking=False):
            self.post("waiting", "RESTART LATER", "a pass is running: press Restart again when it is done")
            return
        if config.FROZEN:
            cmd = [sys.executable] + sys.argv[1:]
        else:                                          # no console window (player request 2026-10-18)
            cmd = [_windowless_python(), "-X", "utf8", "-m", "assist.runner"] + sys.argv[1:]
        print(f"[{datetime.now():%H:%M:%S}] RESTART: starting a fresh copy", flush=True)
        import win32gui
        from bot.focus import game_hwnd
        env = dict(os.environ, AJ_RESTARTED="1")
        if win32gui.GetForegroundWindow() == game_hwnd():
            env["AJ_FOCUS_GAME"] = "1"                 # the new copy hands the front back to the game
        # no stdout/stderr handed over: pythonw then has none, and the new copy writes runs/console.log
        subprocess.Popen(cmd, cwd=str(config.ROOT), env=env,
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)
        os._exit(0)

    def exit_now(self) -> None:
        """The widget's Exit: close the assistant. Never while a pass runs."""
        import os
        if not self.busy.acquire(blocking=False):
            self.post("waiting", "EXIT LATER", "a pass is running: press Exit again when it is done")
            return
        print(f"[{datetime.now():%H:%M:%S}] EXIT", flush=True)
        os._exit(0)

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        if self.widget and hasattr(self.widget, "post_paused"):
            self.widget.post_paused(self.paused)
        if self.paused:
            self.post("paused", "PAUSED", "click to resume")
        else:
            self.post("waiting", "RESUMED", "will act at the next turn start")

    def ignore(self, cid: str) -> None:
        """The player marked a root panel as harmless: it never blocks a pass again."""
        from . import popups
        popups.add_ignored(cid)
        self.offer_ignore([])
        self.post("waiting", f"WAITING (turn {self.last_turn})",
                  f"'{cid}' is ignored from now on (strategy/popup_ignore.json)")

    # ------------------------------------------------------------------ pass
    def run_now(self) -> None:
        """The app's "Run now": one pass for the current turn, right away (after the idle wait)."""
        if not self.busy.acquire(blocking=False):
            print("Run now: a pass is already running", flush=True)
            return
        try:
            s = self.mem.read()
            if not s.ok:
                self.post("waiting", "WAITING", "Run now: no campaign loaded")
                return
            ok, why = players_turn(self.ui)
            if not ok and why == "campaign map not shown" and self._put_away_panels():
                ok, why = players_turn(self.ui)
            if not ok and why.startswith("End Turn button is") and self._clear_notices_first(have_busy=True):
                ok, why = players_turn(self.ui)
            if not ok:
                self.post("waiting", f"WAITING (turn {s.turn})", f"Run now: not your turn ({why})", turn=s.turn)
                return
            pre, need = self.check_popups()
            if need:
                self.post_decisions(s.turn, need, prefix="Run now: ")
                return
            self.do_pass(s.turn, pre)
        except InputAborted as ex:
            self.post("error", f"INTERRUPTED (turn {self.last_turn})", f"interrupted: {ex}\nRun now redoes the pass")
        except Exception as ex:
            traceback.print_exc()
            self.post("error", "ERROR", f"Run now failed: {ex}\nstill watching for the next turn")
        finally:
            self.busy.release()

    def raise_army(self) -> None:
        """The dashboard's "Create new playbook army" (player rule 2026-10-18: the player decides when an army is
        raised; the dashboard shows what it would cost and greys the button out while it cannot be done): the army
        step runs now with a one-shot request and raises a Verminlord Warpseer army (assist/new_army.py)."""
        from . import new_army
        new_army.request_raise()
        if not self.busy.acquire(blocking=False):
            self.post("waiting", "NEW ARMY LATER", "a pass is running: its army step raises the army")
            return
        try:
            s = self.mem.read()
            if not s.ok:
                self.post("waiting", "WAITING", "New army: no campaign loaded")
                return
            ok, why = players_turn(self.ui)
            if not ok:
                self.post("waiting", f"WAITING (turn {s.turn})", f"New army: not your turn ({why})", turn=s.turn)
                return
            done = self.automate(s.turn, [], label="new army", names=["army"])
            self.post("your turn", f"YOUR TURN {s.turn}", "\n".join(done), turn=s.turn)
        except InputAborted as ex:
            self.post("error", f"INTERRUPTED (turn {self.last_turn})", f"interrupted: {ex}")
        except Exception as ex:
            traceback.print_exc()
            self.post("error", "ERROR", f"New army failed: {ex}")
        finally:
            new_army.take_request()                     # one press, one try
            self.busy.release()

    def end_turn_now(self) -> None:
        """The app's "Build & End Turn": the end-of-turn steps (by default buildings, then the army builder), then
        the game's End Turn button. The player asked for it, so there is no idle wait; everything else is checked as
        for a turn-start pass, and End Turn is pressed only when every step ran (an interruption, a failure to raise
        the game or a decision that came up leaves the turn open)."""
        if not self.busy.acquire(blocking=False):
            print("Build & End Turn: a pass is already running", flush=True)
            return
        turn = self.last_turn
        try:
            s = self.mem.read()
            if not s.ok:
                self.post("waiting", "WAITING", "Build & End Turn: no campaign loaded")
                return
            turn = s.turn
            ok, why = players_turn(self.ui)
            if not ok and why == "campaign map not shown" and self._put_away_panels():
                ok, why = players_turn(self.ui)
            if not ok and why.startswith("End Turn button is") and self._clear_notices_first(have_busy=True):
                ok, why = players_turn(self.ui)
            if not ok:
                self.post("waiting", f"WAITING (turn {turn})", f"Build & End Turn: not your turn ({why})", turn=turn)
                return
            from bot.focus import game_focus
            with game_focus():                             # (the Masterplans panel, a Hero Actions panel ...)
                self.close_panels()
            pre, need = self.check_popups()
            if need:
                self.post_decisions(turn, need, prefix="Build & End Turn: ")
                return
            sch = schedule()
            names = self.start_steps(turn) if (self.pending == turn and self.done_turn != turn) else []
            names += [n for n in sch["end_turn"] if n not in names]
            self.offer_ignore([])
            done = self.automate(turn, pre, names=names, label="end_turn")
            if self.pending == turn:                       # the turn-start steps ran too
                self.pending, self.done_turn = None, turn
            if any(line.startswith("could not bring the game") for line in done):
                self.post("error", f"TURN {turn} NOT ENDED", "\n".join(done), turn=turn)
                return
            from bot.focus import game_focus
            with game_focus():                             # what a step left open is not a decision (agent_options)
                self.close_panels()
            _pre, need = self.check_popups()
            if need:
                self.post_decisions(turn, need, prefix="steps done, turn not ended: ")
                return
            ended = self.press_end_turn(turn)
            if ended:
                self.end_done = (self.model, turn)
                self.rail(end="done")
            self.post("waiting" if ended else "error", f"TURN {turn} ENDED" if ended else f"TURN {turn} NOT ENDED",
                      "\n".join(done + [f"End Turn pressed: {self.end_turn_note}" if ended else
                                        f"turn not ended: {getattr(self, 'end_turn_problem', '')}"]),
                      turn=turn)
        except InputAborted as ex:
            self.post("error", f"INTERRUPTED (turn {turn})",
                      f"interrupted: {ex}\nthe turn was not ended; Build & End Turn again to redo it", turn=turn)
        except Exception as ex:
            traceback.print_exc()
            self.post("error", "ERROR", f"Build & End Turn failed: {ex}\nthe turn was not ended", turn=turn)
        finally:
            self.busy.release()

    def press_end_turn(self, turn) -> bool:
        """End the turn with Shift+Enter, the game's own "end turn and skip the End Turn warnings", and wait until the
        turn really ends (the AI phase starts or the turn counter moves). False when the game did not end it.
        Why skip the warnings (2026-10-17, turn 1 of a new campaign): a plain End Turn stops at the game's warnings and
        opens the panel concerned (unspent skill points, "a building can be constructed" in a war-blocked province,
        an army that can still move). The player pressed Build & End Turn after the assistant did everything the
        player's rules allow, so those warnings are about things left alone on purpose."""
        from bot.focus import game_focus
        from tools import wait
        from tools.ui import held, press
        with game_focus():
            # Player report 2026-10-17: End Turn was clicked while Ikit's skill page was still open. Close every
            # panel a step (or the game's own End Turn warning) left open first, and click only on the bare map.
            left = self.close_panels()
            if left:
                self.end_turn_problem = f"could not close {', '.join(left)}"
                return False
            b = self.ui.cached("button_end_turn", under="hud_campaign")
            if b is None:
                self.end_turn_problem = "the End Turn button is not shown"
                return False
            from bot.sensor import turn as turn_mem
            self.end_turn_note = "the other factions are moving"

            def ended() -> bool:
                # memory: the game runs another faction's turn, or the counter moved. (2026-10-17: the UI checks
                # flickered right after the key, the End Turn button among them, and a turn that never ended was
                # reported ended. The switch to the next faction took ~2.3 s in the logs, so wait well beyond that.)
                if self.mem.read().turn != turn or turn_mem.players_turn(self.mem)[0] is False:
                    return True
                # multiplayer: the player's ready tick came on (MP_ME). 2026-10-18: without this the turn ended,
                # memory still listed the player's faction while the friend moved, and a second Shift+Enter went in.
                ready = mp_ready(self.ui)
                new = [n for n, r in ready.items() if r and not ready0.get(n)]
                if MP_ME["name"] is None and len(new) == 1:
                    MP_ME["name"] = new[0]
                    print(f"multiplayer: you are {new[0]!r} in the player list", flush=True)
                b = self.ui.cached("button_end_turn", under="hud_campaign")
                waiting = bool(b) and (self.ui.state(b) or "").startswith("selected")     # (the tick's twin)
                if (MP_ME["name"] is not None and ready.get(MP_ME["name"])) or (ready and waiting):
                    others = [n for n, r in ready.items() if not r and n != MP_ME["name"]]
                    self.end_turn_note = f"waiting for {', '.join(others) or 'the other players'} to end their turn"
                    return True
                return False
            opened: list[str] = []
            for attempt in range(END_TURN_TRIES):
                before = {cid for _c, cid in self.ui.root_children()}
                ready0 = mp_ready(self.ui)
                with held("shift"):
                    press("enter")
                if wait.wait_until(ended, END_TURN_WAIT_S, "another faction's turn", must=False):
                    return True
                # multiplayer: another player's battle or other pending action holds the turn end ("Involved
                # players: ..."). It has no buttons and goes when that player is done: wait for it, never press past it
                if self.ui.root_child("mp_pending_action_blocking_msg"):
                    self.post("waiting", f"ENDING TURN {turn}", "another player has a battle or other action pending:"
                              " the turn ends when they are done", turn=turn)
                    wait.wait_until(lambda: not self.ui.root_child("mp_pending_action_blocking_msg"),
                                    MP_PENDING_WAIT_S, "the other player's pending action", must=False)
                    if wait.wait_until(ended, END_TURN_WAIT_S, "another faction's turn", must=False):
                        return True
                    if self.ui.root_child("mp_pending_action_blocking_msg"):
                        self.end_turn_problem = "another player's action is still pending; Build & End Turn again later"
                        return False
                # not ended: a warning panel the game opened anyway, or the key went unnoticed: clear and press again
                opened = sorted({cid for _c, cid in self.ui.root_children()} - before) or opened
                if self.close_panels():
                    break
            # the shortcut not taken twice: the End Turn button itself (2026-10-18, multiplayer turn 1: Shift+Enter
            # did not end the turn twice and the player had to press End Turn)
            b = self.ui.cached("button_end_turn", under="hud_campaign")
            if b is not None and (self.ui.state(b) or "").startswith("active") and not self.close_panels():
                from tools.ui import click
                ready0 = mp_ready(self.ui)
                click(self.ui, b)
                if wait.wait_until(ended, END_TURN_WAIT_S, "another faction's turn (button)", must=False):
                    self.end_turn_note += " (End Turn button: the shortcut was not taken)"
                    return True
            self.end_turn_problem = (f"the game did not end the turn after {END_TURN_TRIES} tries"
                                     + (f"; it opened {', '.join(opened)}" if opened else ""))
            return False

    def close_panels(self) -> list[str]:
        """Close the full-screen panels (character details, settlement, technology, recruitment) with Escape, one at a
        time, each confirmed gone in the UI tree; the game menu that Escape opens when nothing was open is resumed.
        Returns what is still open (empty = the bare campaign map). Game in front."""
        from tools import wait
        from tools.ui import click, press
        # units_panel = an army or character selected: Shift+Enter does not end the turn then (2026-10-17: the army
        # builder left an army selected and End Turn failed twice; deselected, one Shift+Enter ended it)
        closable = ("character_details_panel", "settlement_panel", "technology_panel", "recruitment_docker",
                    "units_recruitment", "units_panel", "agent_options", "dlc29_skv_chaotic_plans")
        open_ = lambda: [cid for _c, cid in self.ui.root_children() if cid in closable]
        # Thanquol's Masterplans panel and a scripted tour over it close with their own X (2026-10-17): the player
        # asked for the pass, so whatever they had open is put away first
        for panel, under in (("scripted_tour_controls", "under_advisor_docker"), ("plans_main_panel",
                                                                                  "dlc29_skv_chaotic_plans")):
            holder = self.ui.root_child(under) if under == "dlc29_skv_chaotic_plans" else self.ui.first(panel)
            box = self.ui.first(panel, under=under) if holder else None
            x = self.ui.child(box, "button_close") if box else None
            if x is not None and self.ui.effective_visible(x):
                click(self.ui, x)
                wait.wait_until(lambda: not self.ui.effective_visible(x), 1.0, f"{panel} closed", must=False)
        # a Hero Actions panel (agent_options) is closed with its X, as declining the action (2026-10-17: one left
        # open by the army builder's engineer move blocked the end of the turn)
        hero = self.ui.root_child("agent_options")
        x = self.ui.first("button_decline", under=hero) if hero else None
        if x is not None:
            click(self.ui, x)
            wait.gone(self.ui, hero, timeout=1.0, must=False, what="Hero Actions closed")
        # the Masterplans panel closes with its X only; one already closing (its X clicked) is waited out, never
        # given an Escape: Escape with the panel half gone opens the game menu (2026-10-18, End Turn stuck there)
        if self.ui.root_child("dlc29_skv_chaotic_plans"):
            from . import masterplans
            masterplans.close_panel(self.ui)             # page by page with its X, waited out (assist/masterplans.py)
        from .army_builder import _resume
        for _ in range(6):
            now = open_()
            if not now:
                break
            wait.next_frame(2, self.ui)               # a panel already on its way out: no Escape for it (an Escape
            if not open_():                           # with nothing open brings up the game menu)
                break
            press("esc")
            wait.wait_until(lambda: open_() != now or self.ui.root_child("esc_menu"), 1.0, f"{now[0]} closed",
                            must=False)
            if self.ui.root_child("esc_menu"):
                _resume(self.ui)
        if self.ui.root_child("esc_menu"):            # (left by a step, or by the player)
            _resume(self.ui)
        return open_() + (["esc_menu"] if self.ui.root_child("esc_menu") else [])

    def wait_idle(self, turn, cancel) -> bool:
        """Wait until the player has not clicked or pressed a key for IDLE_SECONDS (moving the mouse is fine: player
        request 2026-10-17; the pass then takes the mouse away until it is done, bot/focus.game_focus). False when
        cancelled."""
        from bot import killswitch
        while not self.stop.is_set():
            if cancel():
                return False
            idle = min(killswitch.physical_click_age(), killswitch.physical_key_age())
            if idle >= IDLE_SECONDS:
                return True
            self.post("waiting", f"WAITING (turn {turn})", "waiting for you to stop clicking", turn=turn)
            self.stop.wait(max(0.2, IDLE_SECONDS - idle))
        return False

    def check_popups(self) -> tuple[list[str], list[tuple[str, str, bool]]]:
        """Close event notices; returns (what was closed, open popups that need the player). Raises if the check
        itself fails (the caller then skips the pass rather than clicking into an unknown screen)."""
        from . import popups
        closed = popups.dismiss_events(self.ui)
        popups.log_open(self.ui, self.last_turn, "turn start")
        need = popups.open_decisions(self.ui)
        lines = []
        if closed:
            other = sorted(set(closed) - {"events"})            # "events" is the generic notice id: says nothing
            lines.append(f"closed {len(closed)} event notice{'s' if len(closed) > 1 else ''}"
                         + (f" ({', '.join(other)})" if other else ""))
        return lines, need

    def post_decisions(self, turn, need, prefix: str = "") -> None:
        can = [cid for cid, _d, ig in need if ig]
        news = all(d.startswith(("a global event", "a story event")) for _cid, d, _ig in need)
        tour = all(d.startswith("a guided tour") for _cid, d, _ig in need)
        self.post("paused", f"{'GLOBAL EVENT' if news else 'GUIDED TOUR' if tour else 'DECISION NEEDED'} (turn {turn})",
                  prefix + ("take your time to read it; " if news else "") + "waiting for you: "
                  + ", ".join(d for _cid, d, _ig in need) + "\nautomations run when it is closed"
                  + ("\nharmless? 'Ignore' in the assistant window" if can else ""), turn=turn)
        self.offer_ignore(can)

    def start_steps(self, turn) -> list[str]:
        """The turn-start pass: the turn-start steps, plus the end-of-turn steps when the previous turn was ended
        without "Build & End Turn" (the player pressed End Turn in the game), so nothing waits a whole turn."""
        sch = schedule()
        names = list(sch["turn_start"])
        if self.end_done != (self.model, (turn or 0) - 1):
            names += [n for n in sch["end_turn"] if n not in names]
        # a Steal-Take at maximum Alarm holds End Turn: the Masterplans step completes it now, not at the end
        if "masterplans" not in names and plans_at_max_alarm(self.mem)["economic"]:
            names.append("masterplans")
        return names

    def do_pass(self, turn, pre: list[str], phases: dict | None = None) -> None:
        """One turn-start pass (busy must be held). InputAborted propagates to the caller."""
        self.offer_ignore([])
        done = self.automate(turn, pre, phases=phases, names=self.start_steps(turn))
        from . import gamedata as gd
        for region in plans_at_max_alarm(self.mem)["military"]:       # Kill-Stabs are the player's (2026-10-17)
            done.append(f"Kill-Stab at {gd.place_name(region)} is at maximum Alarm: complete it yourself "
                        "(the game holds End Turn until you do)")
        self.done_turn = turn
        if self.pending == turn:
            self.pending = None
        self.post("your turn", f"YOUR TURN {turn}", "\n".join(done), turn=turn)

    def automate(self, turn: int | None, pre: list[str] | None = None, phases: dict | None = None,
                 label: str = "pass", names: list[str] | None = None) -> list[str]:
        """All steps run inside one game_focus: the game is raised once for the whole pass and focus goes
        back to the terminal (or this app) only when every step is done. Timed into runs/timing-*.jsonl."""
        from bot.focus import game_focus
        with timing.trace(label, turn=turn):
            for k, v in (phases or {}).items():
                timing.phase(k, v)
            if pre is None:                           # --once and the test harness: one popup check, no waiting
                with timing.step("popups"):
                    pre, need = self.check_popups()
                    timing.set_result("; ".join(pre))
                if need:
                    return pre + ["skipped: waiting for you: " + ", ".join(d for _cid, d, _ig in need)]
            self.post("automating", f"AUTOMATING turn {turn}", "", turn=turn)
            try:
                with game_focus():
                    return self._automate(turn, list(pre), all_steps() if names is None else names)
            except RuntimeError as ex:
                return list(pre) + [f"could not bring the game to the front: {ex}"]

    def _call(self, name: str, verify: bool = False):
        fn = STEP_FNS[name]
        if verify and "verify" in inspect.signature(fn).parameters:
            return fn(log=lambda m: None, verify=True)
        return fn(log=lambda m: None)

    def fingerprint(self, name: str) -> tuple:
        """What step `name` changes, from memory: tech the research running, skills every character's unspent skill
        points, buildings the treasury (every construction, upgrade and repair costs gold), army the treasury and
        every army's units and recruitment queue."""
        from bot.sensor.world import World, find_player_faction
        w = World(self.mem)
        if name == "buildings":
            return (self.mem.read().treasury,)
        if name == "tech":
            try:
                T = tech.tech_manager(w)
                return (tech.researching(w, T) if T else None,)
            except Exception:
                return ("?",)
        F = find_player_faction(w)
        if F is None:
            return ()
        if name == "rites":
            return rites.fingerprint(w, F)
        if name == "workshop":
            return tuple(k for k in workshop.UPGRADES if k in workshop.faction_bundles(w, F))
        if name == "skills":                       # the faction's character list (bot/sensor/world.characters), points only
            out = []
            n, arr = w.u32(F + 0xF24), w.q(F + 0xF28)
            for i in range(min(n, 500)):
                try:
                    C = w.q(w.q(arr + 8 * i))
                    out.append((C, skills._points(w, C)))
                except Exception:
                    pass
            return tuple(sorted(out))
        forces = []                                # the faction's forces (bot/sensor/world.armies): unit and queue counts
        n, arr = w.u32(F + 0xF64), w.q(F + 0xF68)
        for i in range(min(n, 200)):
            try:
                MF = w.q(w.q(arr + 8 * i))
                forces.append((MF, w.u32(MF + 0x6C8 + 0xC), w.u32(MF + 0x6EC)))
            except Exception:
                pass
        return self.mem.read().treasury, tuple(sorted(forces))

    def _verify(self, name: str) -> str:
        """Verification run (player request 2026-10-17: a mouse move during a pass made a building slot get missed).
        Every step plans from memory, so running it again is the check: a run that changes nothing in memory means
        everything the first run tried really happened. One that does change something redid what was missed (a
        click that went astray, a construction that got cancelled): it is reported and checked once more."""
        notes = []
        for _ in range(VERIFY_ROUNDS):
            before = self.fingerprint(name)
            with timing.step(f"{name}:verify"):
                try:
                    r = self._call(name, verify=True)
                except InputAborted:
                    raise
                except Exception as ex:
                    traceback.print_exc()
                    return f"verification failed ({ex})"
                timing.set_result(r)
            if self.fingerprint(name) == before:
                return "verified" if not notes else "; ".join(notes) + "; then verified"
            notes.append(f"verification redid: {r}")
        return "; ".join(notes) + "; still changing after verification"

    def _automate(self, turn, done: list[str], names: list[str]) -> list[str]:
        from tools import ui as ui_input
        yields0, suspect0 = ui_input.PLAYER_YIELDS, ui_input.SUSPECT_CLICKS
        try:
            self.rail(events="done")
            for name in names:
                self.rail(**{name: "active"})
                with timing.step(name):
                    try:
                        result = self._call(name)
                    except InputAborted:
                        raise
                    except Exception as ex:
                        result = f"ERROR {ex}"
                        traceback.print_exc()
                    timing.set_result(result)
                result = f"{result} | {self._verify(name)}"
                self.rail(**{name: "failed" if result.startswith("ERROR") else "done"})
                done.append(f"{name}: {result}")
                self.post("automating", f"AUTOMATING turn {turn}", "\n".join(done), turn=turn)
            from . import popups
            try:                                        # notices that arrived during the pass, then a record of
                late = popups.dismiss_events(self.ui)   # anything still open (to teach the popup rules)
                if late:
                    done.append(f"closed {len(late)} late notice{'s' if len(late) > 1 else ''}")
                popups.log_open(self.ui, turn, "after pass")
            except InputAborted:
                raise
            except Exception:
                traceback.print_exc()
            waited = ui_input.PLAYER_YIELDS - yields0
            if waited:
                done.append(f"paused {waited}x while you used the mouse/keyboard"
                            + (f"; {ui_input.SUSPECT_CLICKS - suspect0} click(s) disturbed, re-checked"
                               if ui_input.SUSPECT_CLICKS > suspect0 else ""))
        except InputAborted as ex:
            done.append(f"interrupted: {ex}")
            raise
        finally:
            self.log.write(json.dumps({"t": time.time(), "turn": turn, "steps": done}) + "\n")
            self.log.flush()
            if self.widget and hasattr(self.widget, "post_log"):
                self.widget.post_log([f"turn {turn}"] + done)
        return done

    # ------------------------------------------------------------------ watching
    def loop(self) -> None:
        self.post("waiting", "WAITING", "for a new turn")
        while not self.stop.is_set():
            try:
                self._tick()
            except InputAborted as ex:
                self.post("error", f"INTERRUPTED (turn {self.last_turn})",
                          f"interrupted: {ex}\nRun now redoes the pass; still watching for the next turn")
            except Exception as ex:          # keep watching: a failed read (game closing, loading) is not fatal
                traceback.print_exc()
                self.post("error", "ERROR", f"{ex}\nstill watching for the next turn")
            self.stop.wait(POLL_FAST if (self.pending is not None or not self.my_turn) else POLL_NOTICES)

    def _tick(self) -> None:
        s = self.mem.read()
        if not s.ok:
            self.no_campaign += 1
            if self.last_turn is None or self.no_campaign >= LOST_AFTER:
                self.last_turn = self.model = self.pending = self.done_turn = None
                self.campaign_lost = True
                self.offer_ignore([])
                self.post("waiting", "WAITING", ("no campaign loaded" if self.mem.attached else "the game is not running")
                          + "\nacts from the first new turn after a campaign is loaded")
            return
        self.no_campaign = 0
        model = s.extras.get("model")
        if self.last_turn is None:
            self.last_turn, self.model = s.turn, model
            prev, self.prev_state = self.prev_state, {}
            from bot.sensor import turn as turn_mem
            mine = turn_mem.players_turn(self.mem)[0]
            # started while the other factions move: the player's next turn start is still to come, and its pass is
            # pending (the counter still shows the turn just ended; the next turn change starts the pass). 2026-10-17:
            # a copy restarted after "TURN 5 ENDED" took the turn it found for "mid-turn" and skipped turn 6's pass
            coming = mine is False
            # restarted on the player's turn whose pass the old copy left to do: unfinished (waiting / interrupted /
            # error), or never begun because the old copy ended the turn before and was stopped during the AI moves
            unfinished = mine is True and (
                (prev.get("turn") == s.turn and prev.get("state") != "your turn")
                or (prev.get("turn") == s.turn - 1 and str(prev.get("headline", "")).startswith(f"TURN {s.turn - 1} ENDED")))
            if (coming or unfinished) and not self.campaign_lost:
                self.pending = s.turn
                self.turn_seen_at = time.monotonic()
                self.rail(reset=True)
                self.post("waiting", f"WAITING (turn {s.turn})",
                          "acts when your turn starts" if coming else "restarted: finishing this turn's start",
                          turn=s.turn)
                return
            self.post("your turn", f"YOUR TURN {s.turn}", "campaign changed; acts from next turn" if self.campaign_lost
                      else "assistant started mid-turn; acts from next turn")
            return
        if model != self.model or (s.turn != self.last_turn and s.turn != self.last_turn + 1):
            # a different campaign or save was loaded: not a turn start, wait for the next one
            self.last_turn, self.model = s.turn, model
            self.pending = self.done_turn = None
            self.offer_ignore([])
            self.post("your turn", f"YOUR TURN {s.turn}", "campaign changed; acts from next turn")
            return
        if s.turn == self.last_turn + 1:
            self.last_turn = s.turn
            self.gate_since = None
            self.turn_seen_at = time.monotonic()
            self.phases = {}
            self.rail(reset=True)
            if self.paused:
                self.post("paused", f"PAUSED (turn {s.turn})", "skipped this turn's automations")
            elif self.done_turn != s.turn:                  # Run now may already have done it
                self.pending = s.turn
        if self.pending is not None:
            self._try_pass(self.pending)
        else:
            self.my_turn = players_turn(self.ui)[0]
            from bot.sensor import turn as turn_mem
            if self.my_turn or turn_mem.players_turn(self.mem)[0] is True:
                self._close_notices()

    FULL_SCREEN = ("dlc29_skv_chaotic_plans", "character_details_panel", "technology_panel")

    def _put_away_panels(self) -> bool:
        """The player pressed Run now / Build & End Turn with a full-screen panel open (2026-10-17: Thanquol's
        Masterplans panel hides the campaign HUD, and the pass refused with "campaign map not shown"): when memory
        says it is the player's turn, close it (close_panels) so the checks see the map. True when one was closed."""
        from bot.sensor import turn as turn_mem
        from bot.focus import game_focus
        if turn_mem.players_turn(self.mem)[0] is not True:
            return False
        if not any(self.ui.root_child(p) for p in self.FULL_SCREEN):
            return False
        from tools import wait
        with game_focus():
            self.close_panels()
        # the Masterplans panel animates out for a while: the campaign HUD is back once it is gone
        return bool(wait.wait_until(lambda: self.ui.root_child("hud_campaign")
                                    and not any(self.ui.root_child(p) for p in self.FULL_SCREEN), 3.0,
                                    "campaign map back", must=False))

    def _clear_notices_first(self, have_busy: bool = False) -> bool:
        """It is the player's turn by memory, but End Turn is greyed out: the game does that while an event notice is
        open (2026-10-17: "Rite Expires" kept a turn-start pass waiting for End Turn, and the pass that would close
        the notice never started). Close the notices now (never decisions). True when one was closed."""
        from bot.sensor import turn as turn_mem
        from . import popups
        try:
            if (turn_mem.players_turn(self.mem)[0] is not True or self.ui.cinematic()
                    or not popups._closable(self.ui)):
                return False
            if not have_busy and not self.busy.acquire(blocking=False):
                return False
            try:
                closed = popups.dismiss_events(self.ui)
            finally:
                if not have_busy:
                    self.busy.release()
            if closed:
                print(f"[{datetime.now():%H:%M:%S}] closed {len(closed)} notice(s) that kept End Turn greyed out",
                      flush=True)
            return bool(closed)
        except InputAborted:
            return False
        except Exception:
            traceback.print_exc()
            return False

    def _close_notices(self) -> None:
        """During the player's own turn: close event notices as they come (player request 2026-10-17), the same ones
        the turn-start pass closes; never a decision. Only while the game is the window in front (it is never pulled
        forward) and no pass runs. Each close holds mouse and keyboard for the moment of the click and puts the cursor
        back (bot/focus.game_focus). Off with automation.json "close_notices_during_turn": false."""
        from . import popups
        from bot.focus import game_hwnd
        import win32gui
        try:
            if not json.load(open(AUTOMATION, encoding="utf-8")).get("close_notices_during_turn", True):
                return
            if self.paused or self.busy.locked() or win32gui.GetForegroundWindow() != game_hwnd():
                return
            if self.ui.cinematic():                 # never during a cinematic (a click would skip it)
                return
            if not popups._closable(self.ui):
                ids = tuple(sorted(cid for _c, cid in popups.scan(self.ui)))
                if ids and ids != getattr(self, "_open_seen", ()):
                    popups.log_open(self.ui, self.last_turn, "during your turn")     # what the rules leave open
                self._open_seen = ids
                return
            if not self.busy.acquire(blocking=False):
                return
            try:
                closed = popups.dismiss_events(self.ui)
            finally:
                self.busy.release()
            if closed:
                print(f"[{datetime.now():%H:%M:%S}] closed {len(closed)} notice{'s' if len(closed) > 1 else ''}"
                      " during your turn", flush=True)
        except InputAborted:
            pass                                       # the player switched windows mid-click: try again later
        except Exception:
            traceback.print_exc()

    def _try_pass(self, turn: int) -> None:
        """Start the pending pass once it is really the player's turn and the player is idle. Never blocks for
        long: a popup that needs the player is reported and checked again at the next poll, so Pause and Run now
        keep working while it is open."""
        if self.busy.locked():
            return                                          # Run now is doing a pass right now
        if self.paused:
            self.pending = None
            self.offer_ignore([])
            self.post("paused", f"PAUSED (turn {turn})", "skipped this turn's automations")
            return
        ok, why = players_turn(self.ui)
        self.my_turn = ok
        if not ok and why.startswith("End Turn button is") and self._clear_notices_first():
            ok, why = players_turn(self.ui)                 # (the game greys End Turn out while a notice is open)
        if not ok:
            self.gate_since = None
            self.post("waiting", f"WAITING (turn {turn})", f"{why}; acts when your turn starts", turn=turn)
            return
        if self.gate_since is None:
            self.gate_since = time.monotonic()
            if self.turn_seen_at is not None:
                self.phases["detect"] = self.gate_since - self.turn_seen_at
            self.post("waiting", f"WAITING (turn {turn})", "your turn started; letting it settle", turn=turn)
            done, secs = settle(self.ui, cancel=lambda: self.stop.is_set() or self.paused)
            self.phases["settle"] = secs
            if done is False or self.stop.is_set() or self.paused:
                return
            if done is None:
                print(f"[{datetime.now():%H:%M:%S}] turn start did not settle in {SETTLE_TIMEOUT:.0f} s "
                      "(camera or panels kept changing); going on", flush=True)
            ok, why = players_turn(self.ui)
            if not ok:
                self.gate_since = None
                return
        # no wait for the player to stop clicking (player request 2026-10-17): the pass takes mouse and keyboard at
        # once (bot/focus.game_focus) and gives them back, cursor where it was, when it is done
        if not self.busy.acquire(blocking=False):
            return                                          # Run now is doing a pass right now
        try:
            if self.done_turn == turn or self.pending != turn:
                return
            ok, why = players_turn(self.ui)                  # once more, right before the first click
            if not ok:
                self.gate_since = None
                self.post("waiting", f"WAITING (turn {turn})", f"{why}; acts when your turn starts", turn=turn)
                return
            try:
                t_pop = time.monotonic()
                pre, need = self.check_popups()
                self.phases["popups"] = time.monotonic() - t_pop
            except InputAborted:
                raise
            except Exception as ex:
                traceback.print_exc()
                self.pending = None
                self.post("error", f"SKIPPED turn {turn}",
                          f"the popup check failed ({ex}), so nothing was clicked\nRun now to try again", turn=turn)
                return
            if need:
                self.post_decisions(turn, need)
                return
            self.do_pass(turn, pre, phases=dict(self.phases))
        except CinematicPlaying as ex:                      # the pass stays pending: it runs again after the cinematic
            self.gate_since = None
            self.post("waiting", f"WAITING (turn {turn})", f"{ex}: the pass goes on once it is over", turn=turn)
        except InputAborted as ex:
            self.pending = None
            self.post("error", f"INTERRUPTED (turn {turn})", f"interrupted: {ex}\nRun now redoes the pass", turn=turn)
        finally:
            self.busy.release()


ALREADY_RUNNING = 3                 # exit code: another copy has the game (run_assistant.bat says so)
_instance = None


def single_instance(wait_s: float = 8.0) -> bool:
    """One assistant at a time (2026-10-17: two launcher windows were open and looked like two copies). A named
    mutex, held for the life of the process; a Restart starts the new copy just before the old one exits, so the
    new one waits a few seconds for it."""
    global _instance
    import win32event
    h = win32event.CreateMutex(None, False, "Local\\automated-jay-assistant")
    r = win32event.WaitForSingleObject(h, int(wait_s * 1000))
    if r in (win32event.WAIT_OBJECT_0, win32event.WAIT_ABANDONED):
        _instance = h
        return True
    return False


def _console_log() -> None:
    """No console (started with pythonw, player request 2026-10-18: no terminal window in the background): print()
    and tracebacks go to runs/console.log instead (read by whoever reads the logs)."""
    if sys.stdout is None or sys.stderr is None:
        config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
        log = open(config.RUNS_DIR / "console.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


def _windowless_python() -> str:
    """pythonw.exe next to this Python (no console window), else this Python."""
    w = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return w if os.path.exists(w) else sys.executable


def main() -> int:
    _console_log()
    if "--once" in sys.argv:
        Runner().run_now()          # same checks as the app's Run now: your turn, 3 s idle, no open decision
        return 0
    if not single_instance():
        print("automated-jay is already running (its widget is over the game); this copy stops.", flush=True)
        return ALREADY_RUNNING
    from .app import App
    holder: dict = {}
    app = App(on_pause=lambda: holder["r"].toggle_pause(), on_run_now=lambda: holder["r"].run_now(),
              on_ignore=lambda cid: holder["r"].ignore(cid), on_end_turn=lambda: holder["r"].end_turn_now(),
              on_restart=lambda: holder["r"].restart(), on_exit=lambda: holder["r"].exit_now(),
              on_raise_army=lambda: holder["r"].raise_army())
    r = Runner(widget=app)
    holder["r"] = r
    threading.Thread(target=r.loop, daemon=True).start()
    if os.environ.get("AJ_FOCUS_GAME"):          # restarted from the widget while playing: the game keeps the front
        def _game_front():
            from bot.focus import _raise, game_hwnd
            g = game_hwnd()
            if g:
                _raise(g)
        app.root.after(900, _game_front)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    r.stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
