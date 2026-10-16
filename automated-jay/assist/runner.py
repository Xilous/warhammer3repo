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
Status: every widget update is also written to runs/state.json ({"state", "headline", "detail", "turn",
"time"}), swapped in atomically, for the player and for tools (tools/turn_driver.py --external).
"""
from __future__ import annotations
import json
import sys
import threading
import time
import traceback
from datetime import datetime

from bot import config
from bot.focus import InputAborted, idle_seconds, return_to_terminal
from bot.sensor.memory import MemorySensor
from bot.sensor.ui import UI
from tools import timing
from . import army_builder, build, skills, tech

SETTLE_SECONDS = 4.0          # let turn-start camera moves and event popups appear first
POLL_SECONDS = 2.0
IDLE_SECONDS = 3.0            # the player must have left mouse and keyboard alone this long before a pass
LOST_AFTER = 2                # polls in a row without a campaign before the turn bookkeeping starts over
STATE_FILE = config.RUNS_DIR / "state.json"

STEPS = [
    ("tech", tech.run),
    ("skills", skills.run),
    ("buildings", build.run),            # player rule: building upgrades take precedence over refilling armies
    ("army", army_builder.run),          # recruits with whatever gold the building step left
]


def write_state(state: str, headline: str, detail: str, turn: int | None) -> None:
    """runs/state.json, written to a temp file and swapped in, so a reader never sees half a file. On Windows
    the swap fails while a reader has the old file open: retry briefly."""
    data = {"state": state, "headline": headline, "detail": detail, "turn": turn,
            "time": datetime.now().isoformat(timespec="seconds")}
    tmp = STATE_FILE.with_suffix(".tmp")
    for _ in range(20):
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(STATE_FILE)
            return
        except OSError:
            time.sleep(0.05)
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


def players_turn(ui: UI) -> tuple[bool, str]:
    """(True, "") when the player can act on the campaign map now, else (False, why)."""
    root = ui.find_root()
    if root is None:
        return False, "game UI not found"
    top: dict[str, int] = {}
    for c in ui.children(root):
        top.setdefault(ui.id(c) or "?", c)
    hud = top.get("hud_campaign")
    if hud is None or not ui.visible(hud):
        return False, "campaign map not shown"
    ai = top.get("ai_turns")
    if ai is not None and ui.visible(ai):
        return False, "other factions are moving"
    end = next((c for c, ids in ui.walk(hud) if ids[-1] == "button_end_turn"), None)
    if end is None:
        return False, "End Turn button not shown"
    st = ui.state(end) or ""
    if st.startswith(("inactive", "disabled")):
        return False, f"End Turn button is {st}"
    return True, ""


class Runner:
    def __init__(self, widget=None) -> None:
        self.widget = widget
        self.paused = False
        self.busy = threading.Lock()          # held only while a pass sends input
        self.stop = threading.Event()
        self.mem = MemorySensor()             # never fails: with no game it waits for one
        self.ui = UI(self.mem)
        self.last_turn: int | None = None     # turn counter last seen
        self.model: str | None = None         # campaign model last seen (a new one = a save was loaded)
        self.pending: int | None = None       # turn whose pass is still to do
        self.done_turn: int | None = None     # turn whose pass is done (by the loop or Run now)
        self.no_campaign = 0
        self.campaign_lost = False            # no campaign was seen: the next one is a "campaign change"
        self.gate_since: float | None = None
        self._last_post = None
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

    def offer_ignore(self, ids: list[str]) -> None:
        if self.widget and hasattr(self.widget, "post_ignorable"):
            self.widget.post_ignorable(ids)

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
            if not ok:
                self.post("waiting", f"WAITING (turn {s.turn})", f"Run now: not your turn ({why})", turn=s.turn)
                return
            if not self.wait_idle(s.turn, cancel=lambda: False):
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

    def wait_idle(self, turn, cancel) -> bool:
        """Wait until the player has left mouse and keyboard alone for IDLE_SECONDS. False when cancelled."""
        while not self.stop.is_set():
            if cancel():
                return False
            idle = idle_seconds()
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
        need = popups.open_decisions(self.ui)
        lines = []
        if closed:
            other = sorted(set(closed) - {"events"})            # "events" is the generic notice id: says nothing
            lines.append(f"closed {len(closed)} event notice{'s' if len(closed) > 1 else ''}"
                         + (f" ({', '.join(other)})" if other else ""))
        return lines, need

    def post_decisions(self, turn, need, prefix: str = "") -> None:
        can = [cid for cid, _d, ig in need if ig]
        self.post("paused", f"DECISION NEEDED (turn {turn})",
                  prefix + "waiting for you: " + ", ".join(d for _cid, d, _ig in need) + "\nautomations run when it is closed"
                  + ("\nharmless? 'Ignore' in the assistant window" if can else ""), turn=turn)
        self.offer_ignore(can)

    def do_pass(self, turn, pre: list[str], phases: dict | None = None) -> None:
        """One full pass (busy must be held). InputAborted propagates to the caller."""
        self.offer_ignore([])
        done = self.automate(turn, pre, phases=phases)
        self.done_turn = turn
        if self.pending == turn:
            self.pending = None
        self.post("your turn", f"YOUR TURN {turn}", "\n".join(done), turn=turn)

    def automate(self, turn: int | None, pre: list[str] | None = None, phases: dict | None = None,
                 label: str = "pass") -> list[str]:
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
                    return self._automate(turn, list(pre))
            except RuntimeError as ex:
                return list(pre) + [f"could not bring the game to the front: {ex}"]

    def _automate(self, turn, done: list[str]) -> list[str]:
        try:
            for name, fn in STEPS:
                with timing.step(name):
                    try:
                        result = fn(log=lambda m: None)
                    except Exception as ex:
                        result = f"ERROR {ex}"
                        traceback.print_exc()
                    timing.set_result(result)
                done.append(f"{name}: {result}")
                self.post("automating", f"AUTOMATING turn {turn}", "\n".join(done), turn=turn)
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
            self.stop.wait(POLL_SECONDS)

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
            if self.paused:
                self.post("paused", f"PAUSED (turn {s.turn})", "skipped this turn's automations")
            elif self.done_turn != s.turn:                  # Run now may already have done it
                self.pending = s.turn
        if self.pending is not None:
            self._try_pass(self.pending)

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
        if not ok:
            self.gate_since = None
            self.post("waiting", f"WAITING (turn {turn})", f"{why}; acts when your turn starts", turn=turn)
            return
        if self.gate_since is None:
            self.gate_since = time.monotonic()
            self.post("waiting", f"WAITING (turn {turn})", "your turn started; letting it settle", turn=turn)
            if self.stop.wait(SETTLE_SECONDS) or self.paused:
                return
            ok, why = players_turn(self.ui)
            if not ok:
                self.gate_since = None
                return
        if not self.wait_idle(turn, cancel=lambda: self.paused):
            return
        if not self.busy.acquire(blocking=False):
            return                                          # Run now is doing a pass right now
        try:
            if self.done_turn == turn or self.pending != turn:
                return
            try:
                pre, need = self.check_popups()
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
            self.do_pass(turn, pre)
        except InputAborted as ex:
            self.pending = None
            self.post("error", f"INTERRUPTED (turn {turn})", f"interrupted: {ex}\nRun now redoes the pass", turn=turn)
        finally:
            self.busy.release()


def main() -> int:
    if "--once" in sys.argv:
        Runner().run_now()          # same checks as the app's Run now: your turn, 3 s idle, no open decision
        return 0
    from .app import App
    holder: dict = {}
    app = App(on_pause=lambda: holder["r"].toggle_pause(), on_run_now=lambda: holder["r"].run_now(),
              on_ignore=lambda cid: holder["r"].ignore(cid))
    r = Runner(widget=app)
    holder["r"] = r
    threading.Thread(target=r.loop, daemon=True).start()
    app.root.after(700, return_to_terminal)      # opening the window may have taken focus
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    r.stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
