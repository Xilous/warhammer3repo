"""The assistant's own window (Alt+Tab-able) plus the small always-on-top overlay over the game.

Main window:
  - status: state, turn, treasury; Pause/Resume and "Run now" buttons
  - this turn: what each automation did
  - armies: every field army (not garrisons) by lord name, its location and how it compares with the
    template; the checkbox turns on "match template" for that army (strategy/automation.json)
  - settlements blocked from building (next to an enemy-held one) and why
  - while a pass waits for an unknown panel: one "Ignore <id>" button per panel (never blocks again)
The window only reads game memory to refresh; it never sends input to the game. One refresh at a time, on one
long-lived sensor (it re-attaches by itself when the game is restarted).
"""
from __future__ import annotations
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from .widget import COLORS

REFRESH_MS = 4000
LOG_MAX_LINES = 18


def _version() -> str:
    """The commit this copy runs (from the repo), or the exe's release name: shown in the window title."""
    import subprocess
    from bot import config
    if config.FROZEN:
        try:
            return (config.BUNDLE / "data" / "release.txt").read_text(encoding="utf-8").strip().replace(
                "automated-jay-", "")
        except OSError:
            return ""
    try:
        out = subprocess.run(["git", "-C", str(config.ROOT), "log", "-1", "--format=%h %cd", "--date=format:%H:%M"],
                             capture_output=True, text=True, timeout=3, creationflags=0x08000000)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def template_status(w, F, src) -> tuple[bool, str]:
    """Is there at least one province that can recruit the whole army template? The army builder's own test
    (assist/army_builder.eligible), so the widget and the builder never disagree. (ok, text)."""
    from .army import load_automation, unit_name
    from .army_builder import eligible
    from .recruit import unit_buildings, building_name
    units = list(load_automation()["army_builder"]["template"]["units"])
    full = sorted(eligible(w, F, set(units)))
    if full:
        return True, "Can build the whole template: " + ", ".join(nice(p) for p in full)
    lines, needs = [], []
    for u in units:
        where = sorted({p for p, _r, _b in src.get(u, [])})
        if where:
            lines.append(f"{unit_name(u)}: {', '.join(nice(p) for p in where)}")
        else:
            need = sorted(unit_buildings().get(u, set()))
            lines.append(f"{unit_name(u)}: nowhere yet" + (f" (needs {building_name(need[0])})" if need else ""))
            if need:
                needs.append(building_name(need[0]))
    return False, "No province can build the whole template yet" + chr(10) + chr(10).join(lines)


def template_needs(src) -> list[str]:
    """The buildings still missing for template units that no province can recruit (short form for the bar)."""
    from .army import load_automation
    from .recruit import unit_buildings, building_name
    out = []
    for u in load_automation()["army_builder"]["template"]["units"]:
        if not src.get(u):
            need = sorted(unit_buildings().get(u, set()))
            if need:
                out.append(building_name(need[0]))
    return out


def nice(text: str) -> str:
    """Replace game keys (regions, provinces, factions) with their in-game names."""
    import re
    from . import gamedata as gd
    loc = gd.loc()

    def one(m):
        k = m.group(0)
        for pre in ("regions_onscreen_", "provinces_onscreen_", "factions_screen_name_"):
            v = loc.get(pre + k)
            if v:
                return v
        return k
    return re.sub(r"wh\d?_[a-z0-9_]+", one, text)


def last_logged_turn() -> list[str]:
    from bot import config
    try:
        logs = sorted(config.RUNS_DIR.glob("assistant-*.jsonl"))
        if not logs:
            return []
        import json
        last = json.loads(logs[-1].read_text(encoding="utf-8").strip().splitlines()[-1])
        return [f"turn {last.get('turn')} (last run)"] + last.get("steps", [])
    except Exception:
        return []


def army_signal(rows, fin, checks) -> str | None:
    """The collapsed rail's army line (player request 2026-10-18): an army that can be ticked for a refill to the
    playbook (its refill is possible now), or a new playbook army that can be created, with the income left after
    it. None when there is no such decision."""
    from .army import enabled_armies, tick_for
    enabled = enabled_armies()
    cost = {c.cqi: c for c in (fin.armies if fin else [])}
    for a, d, (can, _why) in rows:
        if can and not tick_for(a, enabled)[0] and (d.missing or d.heroes_missing) and a.cqi in cost:
            inc = cost[a.cqi].income_if_refilled
            what = "rebuilt into the playbook army" if cost[a.cqi].removed else "refilled to the playbook"
            return (f"{a.general_name} can be {what}: income after {inc:+,}/turn"
                    + (" ✓" if inc >= 0 else " ✗"))
    if checks and all(ok for _l, ok, _w in checks) and fin is not None:
        return (f"a new playbook army can be created: income after {fin.after_next:+,}/turn"
                + (" ✓" if fin.after_next >= 0 else " ✗"))
    return None


class App:
    def __init__(self, on_pause, on_run_now, on_ignore=None, on_end_turn=None, on_restart=None, on_exit=None,
                 on_raise_army=None) -> None:
        self.q: queue.Queue = queue.Queue()
        self.on_pause = on_pause
        self.on_run_now = on_run_now
        self.on_ignore = on_ignore
        self.on_end_turn = on_end_turn
        self.on_restart = on_restart
        self.on_exit = on_exit
        self.on_raise_army = on_raise_army
        self._world = None                         # one sensor for every refresh (bot/sensor/world.py World)
        self._refreshing = threading.Lock()
        self.root = tk.Tk()
        self.root.title(f"automated-jay {_version()}   (Shift+Esc = emergency stop)")
        self.root.geometry("640x720+60+60")
        self.root.configure(bg="#1d1f1d")
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background="#1d1f1d", foreground="#e8e8e8", fieldbackground="#262826")
        style.configure("TCheckbutton", background="#1d1f1d", foreground="#e8e8e8")
        style.configure("TLabelframe", background="#1d1f1d", foreground="#9fd9a6")
        style.configure("TLabelframe.Label", background="#1d1f1d", foreground="#9fd9a6")
        style.configure("TButton", padding=4)

        top = tk.Frame(self.root, bg="#1d1f1d", padx=10, pady=8)
        top.pack(fill="x")
        self.state_lbl = tk.Label(top, text="STARTING", font=("Segoe UI", 15, "bold"), bg="#1d1f1d", fg="#bdbdbd")
        self.state_lbl.pack(side="left")
        self.pause_btn = ttk.Button(top, text="Pause", command=self._pause)
        self.pause_btn.pack(side="right", padx=4)
        if on_restart is not None:                 # a fresh copy with the latest code and settings
            ttk.Button(top, text="Restart", command=self._restart).pack(side="right", padx=4)
        ttk.Button(top, text="Run now", command=self._run_now).pack(side="right", padx=4)
        if on_end_turn is not None:                # buildings + army, then the game's End Turn (runner.end_turn_now)
            ttk.Button(top, text="Build & End Turn", command=self._end_turn).pack(side="right", padx=4)
        self.info_lbl = tk.Label(self.root, text="", font=("Segoe UI", 10), bg="#1d1f1d", fg="#c8c8c8", anchor="w", padx=12)
        self.info_lbl.pack(fill="x")
        self.ignore_frame = tk.Frame(self.root, bg="#1d1f1d", padx=10)     # "Ignore <id>" buttons while waiting
        self.ignore_frame.pack(fill="x")

        lf = ttk.LabelFrame(self.root, text="This turn", padding=6)
        lf.pack(fill="x", padx=10, pady=6)
        self.log = tk.Text(lf, height=7, bg="#262826", fg="#e8e8e8", relief="flat", wrap="word", font=("Consolas", 9))
        self.log.pack(fill="x")
        self.root.after(200, lambda: self._show_log(last_logged_turn()))

        af = ttk.LabelFrame(self.root, text="Armies  (tick to refill the army to the template)", padding=6)
        af.pack(fill="both", expand=True, padx=10, pady=6)
        self.army_frame = tk.Frame(af, bg="#1d1f1d")
        self.army_frame.pack(fill="both", expand=True)
        self.army_vars: dict[int, tk.BooleanVar] = {}

        ff = ttk.LabelFrame(self.root, text="Army finances  (you decide when a new army is raised)", padding=6)
        ff.pack(fill="x", padx=10, pady=6)
        self.verdict_lbl = tk.Label(ff, text="", justify="left", anchor="w", bg="#1d1f1d", fg="#c8c8c8",
                                    font=("Segoe UI", 10, "bold"), wraplength=600)
        self.verdict_lbl.pack(fill="x")
        self.finance_lbl = tk.Label(ff, text="", justify="left", anchor="w", bg="#1d1f1d", fg="#c8c8c8",
                                    font=("Consolas", 9), wraplength=600)
        self.finance_lbl.pack(fill="x")
        self.raise_btn = ttk.Button(ff, text="Create new playbook army", command=self._raise_army,
                                    state="disabled")
        if on_raise_army is not None:
            self.raise_btn.pack(anchor="w", pady=(4, 0))

        pf = ttk.LabelFrame(self.root, text="Provinces where nothing is built", padding=6)
        pf.pack(fill="x", padx=10, pady=6)
        self.prov_lbl = tk.Label(pf, text="", justify="left", anchor="w", bg="#1d1f1d", fg="#d8b0b0",
                                 font=("Segoe UI", 9), wraplength=600)
        self.prov_lbl.pack(fill="x")

        # overlay over the game: the Turn rail (assist/rail.py; the player's pick of the designs, 2026-10-17).
        # Its button is reachable without leaving the game (the overlay never takes focus); a click elsewhere on it
        # toggles pause.
        from .rail import TurnRail
        self.rail = TurnRail(self.root, on_pause=self._pause,
                             on_end_turn=self._end_turn if on_end_turn is not None else None,
                             on_run_now=self._run_now,
                             on_restart=self._restart if on_restart is not None else None,
                             on_exit=self._exit if on_exit is not None else None)
        self.overlay = self.rail.win
        # everything else lives in the rail's fold-out panel (player request 2026-10-17: no alt-tab needed); the
        # full window is hidden and can be shown from the panel; closing it only hides it again
        from .railpanel import RailPanel
        self.panel = RailPanel(self.root, self.rail, on_run_now=self._run_now, on_pause=self._pause,
                               on_restart=self._restart, on_ignore=self._ignore, on_full_window=self._show_full,
                               on_exit=self._exit if on_exit is not None else None,
                               on_raise_army=self._raise_army if on_raise_army is not None else None)
        self.rail.on_toggle_panel = self.panel.toggle
        self.rail.on_moved = self.panel.place
        self.rail.draw()
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)
        self.root.withdraw()
        self.ov_hwnd = 0
        self.view_applied = None                   # the runner's view version last drawn (set_view)
        self.root.after(100, self._overlay_ready)

        self.root.after(150, self._poll)
        self.root.after(500, self._refresh_async)

    # ---------------------------------------------------------------- thread-safe API for the runner
    def post(self, state: str, headline: str, detail: str = "") -> None:
        self.state = state
        self._overlay_style(click_through=state == "automating" or self._stepping_aside())  # now: clicks follow
        self.q.put(("status", state, headline, detail))

    def set_view(self, view: dict) -> None:
        """The runner's state, latest wins (a plain assignment: any thread); the Tk poll draws it."""
        self._view = view

    def post_steps(self, steps: dict[str, str]) -> None:
        self.q.put(("steps", steps))

    def post_log(self, lines: list[str]) -> None:
        self.q.put(("log", lines))

    def post_paused(self, paused: bool) -> None:
        self.q.put(("paused", paused))

    def post_ignorable(self, ids: list[str]) -> None:
        self.q.put(("ignorable", list(ids)))

    # ---------------------------------------------------------------- UI internals
    def _pause(self) -> None:
        self.on_pause()

    def _run_now(self) -> None:
        threading.Thread(target=self.on_run_now, daemon=True).start()

    def _show_full(self) -> None:
        self.root.deiconify()
        self.root.lift()

    def _exit(self) -> None:
        threading.Thread(target=self.on_exit, daemon=True).start()

    def _raise_army(self) -> None:
        if getattr(self, "_can_raise", False):
            threading.Thread(target=self.on_raise_army, daemon=True).start()

    def _restart(self) -> None:
        threading.Thread(target=self.on_restart, daemon=True).start()

    def _end_turn(self) -> None:
        threading.Thread(target=self.on_end_turn, daemon=True).start()

    def _overlay_ready(self) -> None:
        self.ov_hwnd = int(self.overlay.wm_frame(), 16)
        self._root_hwnd = int(self.root.wm_frame(), 16)
        self._overlay_style(click_through=False)
        from bot import focus
        focus.BEFORE_INPUT.append(self._step_aside)

    STEP_ASIDE_S = 1.5            # the assistant's input idle this long (outside a pass): the overlay is solid again

    def _stepping_aside(self) -> bool:
        return time.monotonic() - getattr(self, "_input_t", -1e9) < self.STEP_ASIDE_S

    def _step_aside(self) -> None:
        """bot/focus.BEFORE_INPUT, on the runner's thread, before every click, key and move (player question
        2026-10-19: can the widget get in the way?). During a pass the overlay already lets the mouse through and
        the panel is hidden; outside one (notices closed at turn start, during the player's turn, the ones that
        keep End Turn greyed out) the rail was solid: a click under it landed on it (and toggled pause), a hover
        never reached the game. So the rail lets the mouse through and the panel hides until the input has been
        idle for STEP_ASIDE_S."""
        self._input_t = time.monotonic()
        if not getattr(self, "_click_through", False):
            self._overlay_style(click_through=True)
        if self.panel.open and not self.panel.suppressed:
            done = threading.Event()
            self.q.put(("step_aside", done))
            done.wait(0.5)                       # the Tk thread hides it (its next poll, 150 ms at most)

    def _overlay_style(self, click_through: bool) -> None:
        """The overlay sits over the game's top-left corner. It never takes focus (a click on it pauses without
        pulling the game out of the foreground), and while the assistant clicks in the game it lets the mouse
        through: otherwise a click aimed at the game under it lands on the overlay (and toggles pause).
        Plain Win32 calls on the cached handle, so the runner's thread can call it too. They go through ctypes,
        which releases the GIL: changing the style sends the window a message that only the Tk thread can
        answer, and win32gui.SetWindowLong waits for that answer holding the GIL, which deadlocked the app as
        soon as the Tk thread needed the GIL itself."""
        import ctypes
        import win32con
        if not self.ov_hwnd:
            return
        user32 = ctypes.windll.user32
        ex = user32.GetWindowLongW(self.ov_hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_NOACTIVATE
        ex = ex | win32con.WS_EX_TRANSPARENT if click_through else ex & ~win32con.WS_EX_TRANSPARENT
        user32.SetWindowLongW(self.ov_hwnd, win32con.GWL_EXSTYLE, ex)
        # wake the Tk thread (2026-10-20, rail frozen on QUEUED with every after() timer dead: the style change sent
        # from the runner's thread was handled inside Tcl's GetMessageW, which then waited for a posted message that
        # never came, the overlay being click-through. py-spy: main thread in GetMessageW; a posted WM_NULL revived it)
        user32.PostMessageW(self.ov_hwnd, win32con.WM_NULL, 0, 0)
        self._click_through = click_through

    def _poll(self) -> None:
        """Drain the runner's messages into the widgets, every 150 ms. Always rescheduled (2026-10-20: one message
        that raised ended the chain; the rail froze on "YOUR TURN 2 / QUEUED" while the runner went on to turn 3)."""
        self.tk_beat = time.time()                   # the runner's _watch reports a widget that stops beating
        try:
            self._drain()
        except Exception:
            import traceback
            print("widget update failed:", flush=True)
            traceback.print_exc()
        finally:
            self.root.after(150, self._poll)

    def wake(self) -> None:
        """From any thread: a posted WM_NULL to each of the widget's windows ends a Tcl wait that no message would
        end (see _overlay_style)."""
        import ctypes
        import win32con
        for h in (self.ov_hwnd, getattr(self, "_root_hwnd", 0)):
            if h:
                ctypes.windll.user32.PostMessageW(h, win32con.WM_NULL, 0, 0)

    def _drain(self) -> None:
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "status":
                    _, state, headline, detail = msg
                    bg, fg = COLORS.get(state, COLORS["waiting"])
                    self.state_lbl.configure(text=headline, fg=fg)
                    self.rail.set_status(state, headline, nice(detail))
                    self.panel.suppress(state == "automating" or self._stepping_aside())
                elif kind == "step_aside":
                    self.panel.suppress(True)
                    msg[1].set()
                elif kind == "steps":
                    self.rail.set_steps(msg[1])
                elif kind == "log":
                    self._show_log(msg[1])
                    self.panel.show_log(msg[1])
                elif kind == "paused":
                    self.pause_btn.configure(text="Resume" if msg[1] else "Pause")
                    self.panel.set_paused(msg[1])
                elif kind == "world":
                    self._show_world(*msg[1:])
                    self.panel.show_world(*msg[1:])
                    ts = getattr(self, "template_status", None)
                    self.panel.show_template(ts)
                    if ts:
                        ok, text = ts
                        short = text.split(": ", 1)[1] if ok else (
                            "no province yet" + (f" (needs {', '.join(n for n in self.template_needs)})"
                                                  if getattr(self, "template_needs", None) else ""))
                        self.rail.set_template(ok, short)
                elif kind == "signal":
                    self.rail.set_signal(msg[1])
                elif kind == "finance":
                    f = msg[1]
                    self._can_raise = f["can"]
                    self.verdict_lbl.configure(text=f["verdict"], fg="#b8d98a" if f["ok"] else "#f0b49f")
                    self.finance_lbl.configure(text="\n".join(f["lines"] + ([f["why_not"]] if f["why_not"] else [])))
                    self.raise_btn.configure(state="normal" if f["can"] else "disabled")
                    self.panel.show_finance(f)
                elif kind == "diplomacy":
                    self.panel.show_diplomacy(msg[1])
                elif kind == "ignorable":
                    self._show_ignorable(msg[1])
                    self.panel.show_ignorable(msg[1])
        except queue.Empty:
            pass
        v = getattr(self, "_view", None)
        if v is not None and v.get("ver") != self.view_applied:
            self.rail.set_view(v)
            self.view_applied = v.get("ver")         # the runner's _watch checks the widget keeps up with it
        if getattr(self, "state", "") != "automating" and not self._stepping_aside():   # back once input is idle
            if getattr(self, "_click_through", False):
                self._overlay_style(click_through=False)
            if self.panel.suppressed:
                self.panel.suppress(False)

    def _show_log(self, lines: list[str]) -> None:
        """The box grows with the text, wrapped lines included: at a fixed 7 lines the last steps were cut off."""
        self.log.delete("1.0", "end")
        self.log.insert("end", "\n".join(nice(x) for x in lines))
        self.log.update_idletasks()
        n = self.log.count("1.0", "end", "displaylines")
        n = n[0] if isinstance(n, tuple) else n
        self.log.configure(height=max(7, min(LOG_MAX_LINES, n or 0)))

    def _show_ignorable(self, ids: list[str]) -> None:
        for child in self.ignore_frame.winfo_children():
            child.destroy()
        for cid in ids:
            ttk.Button(self.ignore_frame, text=f"Ignore {cid}",
                       command=lambda c=cid: self._ignore(c)).pack(side="left", padx=2, pady=4)

    def _ignore(self, cid: str) -> None:
        if self.on_ignore:
            self.on_ignore(cid)

    def _refresh_async(self) -> None:
        """At most one refresh in flight: a slow read (late-game save) is skipped, not stacked."""
        if self._refreshing.acquire(blocking=False):
            threading.Thread(target=self._refresh, daemon=True).start()
        self.root.after(REFRESH_MS, self._refresh_async)

    def _refresh(self) -> None:
        """Memory reads only; never touches input or focus. Runs with self._refreshing held."""
        try:
            self._refresh_once()
        finally:
            self._refreshing.release()

    def _refresh_once(self) -> None:
        try:
            from bot.sensor.world import World, armies, characters, find_player_faction, snapshot
            from .army import delta, load_automation
            if self._world is None:
                self._world = World()
            w = self._world
            st = w.s.read()
            F = find_player_faction(w)
            if F is None:
                self.q.put(("world", st, [], {}, []))
                return
            from .army_builder import _load_claims, eligible, free_engineer_slots, refill_check
            t = load_automation()["army_builder"]["template"]
            heroes = [c for c in characters(w, F) if c.embedded_force == 0 and c.subtype in t["heroes"]]
            # can each army be ticked for a refill (player rule 2026-10-18)? one province / cap / claims read for all
            elig_any, slots, claims = bool(eligible(w, F, set(t["units"]))), free_engineer_slots(w, F), _load_claims()
            rows = [(a, d, refill_check(w, F, a, d, elig_any, slots, claims))
                    for a in armies(w, F) for d in [delta(a, heroes)]]
            snap = snapshot(w)
            blocked = dict(snap.blocked_settlements) if snap else {}
            from .recruit import report, sources
            src = sources(w)
            self.recruit_lines = report(src)
            self.template_status = template_status(w, F, src)
            self.template_needs = template_needs(src)
            self.q.put(("world", st, rows, blocked, heroes))
            try:
                from .army_finance import checks, compute
                f = compute(w, F)
                cs = checks(w, F)
                ws = None
                if (w.faction_name(F) or "") == "wh3_dlc29_skv_clan_scruten":
                    from bot.sensor import masterplans as mp
                    ws = mp.Reader(w).pooled(F).get(mp.WARPSTONE_KEY)
                self.q.put(("signal", army_signal(rows, f, cs)))
                self.q.put(("finance", {"fin": f, "verdict": f.verdict(), "ok": f.after_next >= 0,
                                        "can": all(ok for _l, ok, _w in cs), "checks": cs, "warpstone": ws,
                                        "lines": f.lines(),
                                        "why_not": "; ".join(f"{lb}: {why}" for lb, ok, why in cs if not ok)}))
            except Exception as ex:                       # noqa: BLE001  (the dashboard says why)
                self.q.put(("finance", {"fin": None, "verdict": f"army finances unreadable: {ex}", "ok": False,
                                        "can": False, "checks": [], "warpstone": None, "lines": [],
                                        "why_not": str(ex)}))
            try:
                from .diplomacy import listed
                self.q.put(("diplomacy", listed(w)))
            except Exception:                             # noqa: BLE001  (the list stays as last read)
                pass
        except Exception as ex:
            self.q.put(("world", None, [], {"error": str(ex)}, []))

    def _show_world(self, st, rows, blocked, heroes=()) -> None:
        from .army import enabled_armies, set_enabled, tick_for
        if st is not None:
            self.info_lbl.configure(text=f"Turn {st.turn}    Treasury {st.treasury}"
                                    if st.turn is not None else "no campaign loaded")
        enabled = enabled_armies()
        for child in self.army_frame.winfo_children():
            child.destroy()
        if not rows:
            tk.Label(self.army_frame, text="no field armies found", bg="#1d1f1d", fg="#9a9a9a").pack(anchor="w")
        for a, d, (can, why_not) in rows:
            var = self.army_vars.setdefault(a.cqi, tk.BooleanVar())
            on, why = tick_for(a, enabled)          # a tick set for another general (another campaign) is off
            var.set(on)
            row = tk.Frame(self.army_frame, bg="#1d1f1d", pady=3)
            row.pack(fill="x", anchor="w")
            # the tick stores the general's character id and name with the cqi (cqis repeat between campaigns)
            cb = ttk.Checkbutton(row, variable=var, command=lambda a=a, var=var: set_enabled(
                a.cqi, a.general_name, var.get(), a.general_id, a.turn, a.rank))
            if not on and not can:                  # a refill that cannot happen cannot be ticked; a tick can go
                cb.state(["disabled"])
            cb.pack(side="left")
            where = nice(a.region or "")
            size = f"{len(a.units)} units" + (f" + {len(a.queued)} recruiting" if a.queued else "")
            tk.Label(row, text=f"{a.general_name}  ({size}, {where})", font=("Segoe UI", 10, "bold"),
                     bg="#1d1f1d", fg="#e8e8e8").pack(side="left")
            if why:
                tk.Label(self.army_frame, text=why, bg="#1d1f1d", fg="#ffb0b0", font=("Segoe UI", 9),
                         wraplength=540, justify="left", anchor="w", padx=28).pack(fill="x", anchor="w")
            tk.Label(self.army_frame, text=d.summary(), bg="#1d1f1d",
                     fg="#8dff9c" if d.matches else "#c8c8c8", font=("Segoe UI", 9), wraplength=540,
                     justify="left", anchor="w", padx=28).pack(fill="x", anchor="w")
            if not on and not can and (d.missing or d.heroes_missing):
                tk.Label(self.army_frame, text=why_not, bg="#1d1f1d", fg="#ffd27a", font=("Segoe UI", 9),
                         wraplength=540, justify="left", anchor="w", padx=28).pack(fill="x", anchor="w")
        if st is not None:                    # always shown, so "none" is visible rather than a missing line
            tk.Label(self.army_frame, text="Heroes on their own: " + (", ".join(
                f"{c.name} ({nice(c.region or '')})" for c in heroes) or "none"),
                bg="#1d1f1d", fg="#ffd27a", font=("Segoe UI", 9), wraplength=590, justify="left",
                anchor="w").pack(fill="x", anchor="w", pady=(8, 0))
        if getattr(self, "recruit_lines", None):
            tk.Label(self.army_frame, text="Recruitable now:\n" + "\n".join(self.recruit_lines),
                     bg="#1d1f1d", fg="#9fd9a6", font=("Segoe UI", 9), wraplength=590, justify="left",
                     anchor="w").pack(fill="x", anchor="w", pady=(8, 0))
        if "error" in blocked:
            self.prov_lbl.configure(text="could not read the campaign: " + blocked["error"])
        else:
            self.prov_lbl.configure(text="\n".join(f"{nice(p)}: {nice(why)}" for p, why in blocked.items()) or "none")

    def run(self) -> None:
        self.root.mainloop()
