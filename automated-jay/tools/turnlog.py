"""RESEARCH / TEST TOOL: ground truth for "the AI factions are still moving" vs "the player's turn has started".

  python -X utf8 -m tools.turnlog OUT.jsonl --seconds 900     # passive: memory and UI tree only, sends no input
  python -X utf8 -m tools.turnlog OUT.jsonl --drive N         # TEST ONLY: plays N turns as the human (see below)
  python -X utf8 -m tools.turnlog --summary OUT.jsonl         # the order of the signals around each AI-phase end

Every sample (about every 30 ms) records: the turn counter, whose turn it is (bot/sensor/turn.py) and whether that
is the player's faction, the visible root panels (ai_turns, hud_campaign, popups), the End Turn button's state, the
OLD runner gate (hud_campaign shown, no ai_turns, End Turn not inactive/disabled), the frame stamp, and with
--drive whether the UI answers input: the cursor is moved onto a HUD button and that button's state object must
switch to its hover state within HOVER_FRAMES rendered frames (0.5-1.5 frames when the UI is live). The targets
alternate between button_menu (menu bar, top left) and tab_units (hud_campaign top bar). Nothing is clicked by the
probe. A target still in its hover state before the cursor arrives (the UI did not see the cursor leave) counts as
not answering.

--drive: ends the turn with Shift+Enter like tools/turn_driver.py, keeps the game in front through the whole AI
phase (hover only registers while the game is the foreground window), answers AI popups with the turn driver's
`handle` (diplomacy -> cancel, battles -> autoresolve), and stops sampling TAIL seconds after the player's turn is
live. It runs no assistant steps, and assist.runner must not be running at the same time.
"""
from __future__ import annotations
import json
import sys
import time

T0 = time.perf_counter()
HOVER_FRAMES = 4                 # frames the hover state may take (normal 0.5-1.5)
TARGETS = ("button_menu", "tab_units")
TAIL = 6.0                       # s of live player's turn logged after the transition
PHASE_TIMEOUT = 900.0
REPRESS_AFTER = 20.0             # End Turn ignored (right after a load): press again


def now() -> float:
    return round(time.perf_counter() - T0, 4)


def old_gate(ui) -> tuple[bool, str]:
    """assist.runner.players_turn as it was before 2026-10-17 (UI tree only)."""
    if ui.find_root() is None:
        return False, "game UI not found"
    top = dict((cid, c) for c, cid in reversed(ui.root_children()))
    if "hud_campaign" not in top:
        return False, "campaign map not shown"
    if "ai_turns" in top:
        return False, "other factions are moving"
    end = ui.cached("button_end_turn", under="hud_campaign")
    if end is None:
        return False, "End Turn button not shown"
    st = ui.state(end) or ""
    if st.startswith(("inactive", "disabled")):
        return False, f"End Turn button is {st}"
    return True, ""


class Sampler:
    def __init__(self, m, ui) -> None:
        from bot.sensor.world import World
        self.m, self.ui = m, ui
        self.w = World(m)
        self.names: dict[int, str] = {}
        self.player = None
        self.player_model = None
        self.last: dict = {}
        self.k = 0
        self.stamp = None

    def name(self, f: int) -> str:
        if f not in self.names:
            self.names[f] = self.w.faction_name(f) or hex(f)
        return self.names[f]

    def sample(self) -> dict:
        from bot.sensor import turn as turnmem
        from bot.sensor.world import find_player_faction
        m, ui = self.m, self.ui
        rec: dict = {"t": now()}
        model = m.model
        if model is None:
            rec["model"] = None
            return rec
        if model != self.player_model:
            self.player, self.player_model, self.names = find_player_faction(self.w), model, {}
        rec["round"] = m._field("turn", "<i", model)
        w = turnmem.whose_turn(m.pm, model)
        rec["whose"] = None if w is None else [self.name(f) for f in w]
        rec["mine"] = None if w is None or self.player is None else self.player in w
        try:
            rc = ui.root_children()
        except Exception:
            rc = []
        ids = [cid for _c, cid in rc]
        rec["root"] = ids
        rec["ai_turns"] = "ai_turns" in ids
        rec["hud"] = "hud_campaign" in ids
        try:
            end = ui.cached("button_end_turn", under="hud_campaign") if rec["hud"] else None
            rec["end"] = (ui.state(end) or "") if end else None
        except Exception:
            rec["end"] = None
        rec["old"] = old_gate(ui)[0]
        try:
            st = ui.frame_stamp()
        except Exception:
            st = None
        rec["render"] = st is not None and st != self.stamp
        self.stamp = st
        return rec

    def hover(self) -> dict:
        """Move the cursor onto the next target; did the game register it? Needs the game in front."""
        import win32api
        from tools import wait
        ui = self.ui
        cid = TARGETS[self.k % len(TARGETS)]
        self.k += 1
        out = {"hv_t": cid, "hv": None, "hv_ms": None}
        try:
            c = ui.cached(cid)
            if c is None:
                out["hv_why"] = "not shown"
                return out
            out["hv_st"] = ui.state(c)
            pr = ui.hover_probe(c)
            if pr is None:
                out["hv_why"] = "no hover form"
                return out
            p, hs = pr
            if ui.state_ptr(p) in hs:
                out["hv"] = False
                out["hv_why"] = "stale hover"
                win32api.SetCursorPos((960, 640))       # off the target so the next probe can see an arrival
                return out
            x, y = ui.comp(c).center
            t = time.perf_counter()
            win32api.SetCursorPos((int(x), int(y)))
            ok = wait.frames_until(lambda: ui.state_ptr(p) in hs, HOVER_FRAMES, ui)
            out["hv"] = bool(ok)
            out["hv_ms"] = round((time.perf_counter() - t) * 1000, 1)
        except Exception as ex:          # noqa: BLE001
            out["hv_why"] = f"error {ex}"
        return out


def writer(path):
    f = open(path, "a", encoding="utf-8")

    def write(rec: dict) -> None:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        f.flush()
    return write


def passive(out: str, seconds: float, m, ui) -> int:
    S = Sampler(m, ui)
    write = writer(out)
    write({"t": now(), "event": "start", "mode": "passive"})
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        t = time.perf_counter()
        write(S.sample())
        time.sleep(max(0.0, 0.03 - (time.perf_counter() - t)))
    write({"t": now(), "event": "stop"})
    return 0


def drive(out: str, n: int, m, ui, hover: bool = True) -> int:
    from assist import popups
    from bot.focus import game_focus, return_to_terminal
    from tools.turn_driver import handle
    from tools.ui import held, press as press_key
    S = Sampler(m, ui)
    write = writer(out)
    write({"t": now(), "event": "start", "mode": "drive", "turns": n})
    for i in range(n):
        t0 = m.read().turn
        with game_focus():
            write({"t": now(), "event": "end_turn", "round": t0})
            print(f"=== ending turn {t0}", flush=True)
            with held("shift"):
                time.sleep(0.05)
                press_key("enter")
            pressed = start = time.perf_counter()
            live_since = None
            last_pop = 0.0
            while time.perf_counter() - start < PHASE_TIMEOUT:
                t = time.perf_counter()
                rec = S.sample()
                if hover:
                    rec.update(S.hover())
                write(rec)
                moved = rec.get("round") not in (None, t0)
                live = moved and rec.get("mine") and rec.get("old") and (rec.get("hv") is not False if hover else True)
                if live:
                    live_since = live_since or t
                    if t - live_since >= TAIL:
                        break
                else:
                    live_since = None
                if not moved and rec.get("old") and t - pressed > REPRESS_AFTER:
                    write({"t": now(), "event": "end_turn_again"})
                    print("    End Turn was ignored; pressing it again", flush=True)
                    with held("shift"):
                        time.sleep(0.05)
                        press_key("enter")
                    pressed = time.perf_counter()
                if not moved and t - last_pop > 1.0:
                    last_pop = t
                    try:
                        pops = popups.scan(ui)
                    except Exception:
                        pops = []
                    if pops:
                        acts = handle(ui)
                        if acts:
                            write({"t": now(), "event": "popups", "acts": acts})
                            for a in acts:
                                print("   ", a, flush=True)
                time.sleep(max(0.0, 0.03 - (time.perf_counter() - t)))
            write({"t": now(), "event": "phase_end", "round": m.read().turn})
        # the turn-start notices, as the turn driver closes them (the player would)
        for _ in range(6):
            acts = handle(ui)
            for a in acts:
                print("   ", a, flush=True)
            if not acts:
                break
        if acts:
            write({"t": now(), "event": "popups_after", "acts": acts})
        print(f"=== turn {m.read().turn} started", flush=True)
        print_summary(out, last_only=True)
    return_to_terminal()
    write({"t": now(), "event": "stop"})
    return 0


# ------------------------------------------------------------------ summary

def phases(path: str) -> list[list[dict]]:
    """Split the log at each end-turn (drive) or at each change of the turn counter (passive: from the moment the
    End Turn button went inactive before it)."""
    recs = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    out, cur = [], None
    for r in recs:
        if r.get("event") == "end_turn":
            cur = [r]
            out.append(cur)
        elif r.get("event") == "start":
            cur = None
        elif cur is not None:
            cur.append(r)
    if out:
        return out
    # passive: phase = from the last sample with the old gate true before a turn change to the next turn change
    samples = [r for r in recs if "round" in r]
    for i in range(1, len(samples)):
        if samples[i]["round"] != samples[i - 1]["round"]:
            j = i - 1
            while j > 0 and not samples[j].get("old"):
                j -= 1
            k = i
            while k + 1 < len(samples) and samples[k + 1]["round"] == samples[i]["round"]:
                k += 1
            out.append([{"t": samples[j]["t"], "event": "end_turn", "round": samples[i - 1]["round"]}] + samples[j:k + 1])
    return out


def summarize(ph: list[dict]) -> dict:
    t_end = ph[0]["t"]
    r0 = ph[0].get("round")
    s = [r for r in ph if "round" in r]
    rel = lambda r: round(r["t"] - t_end, 3)
    res: dict = {"round": r0, "samples": len(s)}
    if not s:
        return res
    i_round = next((i for i, r in enumerate(s) if r["round"] not in (None, r0)), None)
    res["round+1"] = rel(s[i_round]) if i_round is not None else None
    factions = []
    for r in s:
        w = tuple(r.get("whose") or ())
        if not factions or factions[-1] != w:
            factions.append(w)
    res["turns_seen"] = len(factions)

    def last_onset(pred):
        """Time from which pred holds until the end of the log (None if it does not hold at the end)."""
        t = None
        for r in s:
            if pred(r):
                t = t if t is not None else rel(r)
            else:
                t = None
        return t

    def first(pred):
        return next((rel(r) for r in s if pred(r)), None)
    res["mine_from"] = last_onset(lambda r: r.get("mine"))
    res["mine_first"] = first(lambda r: r.get("mine") and r["round"] != r0)
    res["ai_turns_gone"] = last_onset(lambda r: not r.get("ai_turns"))
    res["end_active_from"] = last_onset(lambda r: r.get("end") not in (None, "") and not str(r.get("end")).startswith(("inactive", "disabled")))
    res["old_gate_from"] = last_onset(lambda r: r.get("old"))
    hv = [r for r in s if r.get("hv_t") == "tab_units"]
    if hv:
        res["hover_hud_from"] = last_onset(lambda r: r.get("hv_t") != "tab_units" or r.get("hv"))
        res["hover_menu_from"] = last_onset(lambda r: r.get("hv_t") != "button_menu" or r.get("hv"))
    # where the old gate said "your turn" although the AI was still moving (memory) or the UI ignored input (hover)
    early, cur = [], None
    for r in s:
        bad = r.get("old") and (not r.get("mine") or r["round"] == r0 or r.get("hv") is False)
        if bad:
            why = ("whose=" + ",".join(r.get("whose") or ["?"])) if not r.get("mine") else (
                "same round" if r["round"] == r0 else f"no hover on {r.get('hv_t')}")
            if cur is None:
                cur = [rel(r), rel(r), why]
                early.append(cur)
            cur[1] = rel(r)
        else:
            cur = None
    res["old_gate_early"] = early
    return res


def print_summary(path: str, last_only: bool = False) -> None:
    ph = phases(path)
    for p in (ph[-1:] if last_only else ph):
        print("   ", json.dumps(summarize(p)), flush=True)


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--summary":
        print_summary(args[1])
        return 0
    out = args[0]
    from bot.sensor.memory import MemorySensor
    from bot.sensor.ui import UI
    m = MemorySensor()
    ui = UI(m)
    ui.find_root()
    if "--drive" in args:
        return drive(out, int(args[args.index("--drive") + 1]), m, ui, hover="--no-hover" not in args)
    secs = float(args[args.index("--seconds") + 1]) if "--seconds" in args else 600.0
    return passive(out, secs, m, ui)


if __name__ == "__main__":
    sys.exit(main())
