"""TEST HARNESS ONLY: play whole turns on a test save without a human.

  python -X utf8 -m tools.turn_driver N              # end N turns; after each, run the assistant's turn-start steps
  python -X utf8 -m tools.turn_driver N --external   # the real assistant (python -m assist.runner) is running:
                                                     # end N turns and let IT run the turn-start steps

Between turns it makes the decisions a player would (this is NOT part of the assistant):
  AI diplomacy offers -> cancel, battles -> autoresolve, results / events -> close, esc menu -> resume.
Every popup it sees and what it did is printed, so unknown popups can be added.

--external plays only the human. It watches the runner's runs/state.json: while the runner says DECISION NEEDED
for the new turn it resolves those popups (as the player), and once the runner says "your turn" for the new
turn it ends the turn again. It never clicks while the runner is automating: every click is made under the
input lock (bot/focus.py) after re-checking the runner's state. Event notices are left to the runner.
"""
from __future__ import annotations
import json
import sys
import time

import win32gui

from assist import popups
from assist.runner import Runner, read_state
from bot import config
from bot.focus import game_focus, game_hwnd, input_lock
from bot.sensor.memory import MemorySensor
from bot.sensor.ui import UI
from tools.ui import click_at, held, press as press_key

PREFERRED = ["button_autoresolve", "button_cancel", "button_dismiss", "button_close", "button_accept",
             "button_ok", "button_tick", "button_continue", "button_resume"]
DETECT_TIMEOUT = 90          # s: the runner polls memory every 2 s, then lets the turn settle for 4 s
FINISH_TIMEOUT = 900         # s: a whole turn-start pass, decisions included


def press(ui: UI, comp: int, guard=None, wait: float = 1.2) -> bool:
    """Click a popup button as the player. The guard is checked under the input lock right before the click
    (so the runner cannot start in between); False = leave the popup alone."""
    with input_lock():
        if guard is not None and not guard():
            return False
        with game_focus():
            click_at(*ui.comp(comp).center)
            time.sleep(wait)
    return True


def handle(ui: UI, guard=None, decisions_only: bool = False) -> list[str]:
    acted = []
    for c, cid in popups.scan(ui):
        if decisions_only and popups.is_event(cid) and not popups.needs_choice(ui, c):
            continue                            # event notices are the runner's to close
        if cid == "events" and popups.needs_choice(ui, c):
            choice = next((b for b, ids in ui.walk(c) if ids[-1] == "choice_button"), None)
            if choice is not None:              # TEST ONLY: take the first option of a dilemma
                if not press(ui, choice, guard, wait=1.5):
                    return acted + ["left alone: the runner is busy"]
                acted.append("dilemma -> first choice (test harness)")
                continue
        btns = {ids[-1]: b for b, ids in ui.walk(c) if ids[-1].startswith("button_")}
        pick = next((n for n in PREFERRED if n in btns), None)
        if cid == "esc_menu":
            pick = "button_resume" if "button_resume" in btns else pick
        if pick is None:
            acted.append(f"{cid}: no known button ({sorted(btns)[:8]})")
            continue
        if not press(ui, btns[pick], guard):
            return acted + ["left alone: the runner is busy"]
        acted.append(f"{cid} -> {pick}")
    return acted


def end_turn(ui: UI) -> None:
    with game_focus():
        with held("shift"):
            time.sleep(0.08)
            press_key("enter")
            time.sleep(0.08)
        time.sleep(3)


def army_in(army_cqi: int, province: str) -> bool:
    from bot.sensor.world import World, armies, find_player_faction, region_provinces
    w = World()
    F = find_player_faction(w)
    prov, _ = region_provinces()
    a = next((a for a in armies(w, F) if a.cqi == army_cqi), None)
    return a is not None and prov.get(a.region or "") == province


def army_matches(cqi: int) -> bool:
    from bot.sensor.world import World, armies, find_player_faction
    from assist.army import delta
    w = World()
    F = find_player_faction(w)
    a = next((a for a in armies(w, F) if a.cqi == cqi), None)
    if a is None:
        return False
    d = delta(a, [])
    print(f"    army {cqi}: {len(a.units)} units, {len(a.queued)} queued; {d.summary()}", flush=True)
    return d.matches


def play_ai_phase(m: MemorySensor, ui: UI, t0: int, guard=None) -> bool:
    """End the turn and answer popups until the turn counter moves. False if it never does. Right after a save is
    loaded the game can ignore the End Turn key: it is pressed again while the End Turn button is still active."""
    from assist.runner import players_turn
    print(f"=== ending turn {t0}", flush=True)
    end_turn(ui)
    start = pressed = time.time()
    while m.read().turn == t0 and time.time() - start < 900:
        for a in handle(ui, guard):
            print("   ", a, flush=True)
        if time.time() - pressed > 20 and players_turn(ui)[0] and (guard is None or guard()):
            print("    End Turn was ignored; pressing it again", flush=True)
            end_turn(ui)
            pressed = time.time()
        time.sleep(2)
    if m.read().turn == t0:
        print("turn did not advance; stopping")
        return False
    return True


# ------------------------------------------------------------------ --external: the real assistant runs the steps

IDLE = ("your turn", "waiting")      # states in which the runner sends no input


def runner_says(turn: int, states: tuple = IDLE, headline: str | None = None) -> bool:
    st = read_state()
    return (st.get("turn") == turn and st.get("state") in states
            and (headline is None or str(st.get("headline", "")).startswith(headline)))


def wait_for_runner(ui: UI, turn: int, timeout: float, done: tuple = ("your turn",)) -> dict | None:
    """Follow the runner through a turn start: resolve its DECISION NEEDED popups, return its final state
    once it says "your turn" (or another state in done) for this turn. None (with the reason printed) on
    timeout or when the runner is paused."""
    start = time.time()
    last = None
    seen = False
    while time.time() - start < timeout:
        st = read_state()
        line = (st.get("turn"), st.get("state"), st.get("headline"))
        if line != last:
            print(f"    runner: {st.get('headline')} [{st.get('state')}, turn {st.get('turn')}]", flush=True)
            last = line
        if st.get("turn") == turn:
            seen = True
            if st.get("state") in done:
                return st
            if str(st.get("headline", "")).startswith("PAUSED"):
                print(f"STOP: the assistant is paused (click its overlay to resume); its state: {st}", flush=True)
                return None
            if str(st.get("headline", "")).startswith("DECISION NEEDED"):
                for a in handle(ui, guard=lambda: runner_says(turn, ("paused",), "DECISION NEEDED"),
                                decisions_only=True):
                    print("    player:", a, flush=True)
        elif not seen and time.time() - start > DETECT_TIMEOUT:
            print(f"STOP: the assistant did not pick up turn {turn} within {DETECT_TIMEOUT}s "
                  f"(is 'python -m assist.runner' running?); its last state: {st}", flush=True)
            return None
        time.sleep(1)
    print(f"STOP: the assistant did not finish turn {turn} within {timeout:.0f}s; its last state: {st}", flush=True)
    return None


def logged_steps(turn: int) -> list[str] | None:
    logs = sorted(config.RUNS_DIR.glob("assistant-*.jsonl"))
    for line in reversed(logs[-1].read_text(encoding="utf-8").splitlines() if logs else []):
        rec = json.loads(line)
        if rec.get("turn") == turn:
            return rec.get("steps", [])
    return None


def check_turn(turn: int, st: dict) -> list[str]:
    """What the runner left behind for this turn; returns the problems found."""
    bad = []
    steps = logged_steps(turn)
    names = [s.split(":", 1)[0] for s in steps or []]
    missing = [n for n in ("tech", "skills", "buildings", "army") if n not in names]
    print(f"    log: {len(steps or [])} lines for turn {turn}" + (f", MISSING {missing}" if missing else ""), flush=True)
    for s in steps or []:
        print(f"      {s}", flush=True)
    if steps is None or missing:
        bad.append(f"turn {turn}: log line missing or incomplete")
    if any("ERROR" in s for s in steps or []):
        bad.append(f"turn {turn}: a step failed")
    fg = win32gui.GetForegroundWindow()
    who = f"{win32gui.GetClassName(fg)} '{win32gui.GetWindowText(fg)}'" if fg else "none"
    print(f"    focus: {who}", flush=True)
    if fg and fg == game_hwnd():
        bad.append(f"turn {turn}: the game kept the focus")
    if st.get("state") != "your turn":
        bad.append(f"turn {turn}: state.json ended at {st.get('state')}")
    return bad


def external(n: int, m: MemorySensor, ui: UI) -> int:
    problems = []
    for _ in range(n):
        t0 = m.read().turn
        st = wait_for_runner(ui, t0, DETECT_TIMEOUT, done=IDLE)        # the runner must be idle on this turn
        if st is None:
            return 1
        for a in handle(ui, guard=lambda: runner_says(t0)):          # a popup left open after its pass
            print("    player:", a, flush=True)
        start = time.time()
        if not play_ai_phase(m, ui, t0, guard=lambda: m.read().turn == t0):
            return 1
        t = m.read().turn
        print(f"=== turn {t} started ({time.time() - start:.0f}s); the assistant runs its steps", flush=True)
        st = wait_for_runner(ui, t, FINISH_TIMEOUT)
        if st is None:
            return 2
        print(f"=== turn {t}: assistant done after {time.time() - start:.0f}s", flush=True)
        problems += check_turn(t, st)
    print("=== done: " + ("; ".join(problems) if problems else "every turn checked out"), flush=True)
    return 3 if problems else 0


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    until = None
    if "--until" in sys.argv:                  # --until <army cqi> <province key>
        i = sys.argv.index("--until")
        until = (int(sys.argv[i + 1]), sys.argv[i + 2])
    match = int(sys.argv[sys.argv.index("--until-match") + 1]) if "--until-match" in sys.argv else None
    m = MemorySensor()
    ui = UI(m)
    ui.find_root()
    if "--external" in sys.argv:
        return external(n, m, ui)
    r = Runner()
    for i in range(n):
        t0 = m.read().turn
        start = time.time()
        if not play_ai_phase(m, ui, t0):
            return 1
        time.sleep(6)
        for _ in range(6):
            acts = handle(ui)
            for a in acts:
                print("   ", a, flush=True)
            if not acts:
                break
        t = m.read().turn
        print(f"=== turn {t} started ({time.time() - start:.0f}s); running assistant steps", flush=True)
        r.last_turn = t
        for line in r.automate(t):
            print("   ", line, flush=True)
        if until and army_in(*until):
            print(f"=== army {until[0]} is in {until[1]}; stopping", flush=True)
            return 0
        if match is not None and army_matches(match):
            print(f"=== army {match} matches the template; stopping", flush=True)
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
