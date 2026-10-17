"""The assistant's own window (Alt+Tab-able) plus the small always-on-top overlay over the game.

Main window:
  - status: state, turn, treasury; Pause/Resume and "Run now" buttons
  - this turn: what each automation did
  - armies: every field army (not garrisons) by lord name, its location and how it compares with the
    template; the checkbox turns on "match template" for that army (strategy/automation.json)
  - provinces: which ones are blocked from building and why
  - while a pass waits for an unknown panel: one "Ignore <id>" button per panel (never blocks again)
The window only reads game memory to refresh; it never sends input to the game. One refresh at a time, on one
long-lived sensor (it re-attaches by itself when the game is restarted).
"""
from __future__ import annotations
import queue
import threading
import tkinter as tk
from tkinter import ttk

from .widget import COLORS

REFRESH_MS = 4000
LOG_MAX_LINES = 18


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


class App:
    def __init__(self, on_pause, on_run_now, on_ignore=None, on_end_turn=None) -> None:
        self.q: queue.Queue = queue.Queue()
        self.on_pause = on_pause
        self.on_run_now = on_run_now
        self.on_ignore = on_ignore
        self.on_end_turn = on_end_turn
        self._world = None                         # one sensor for every refresh (bot/sensor/world.py World)
        self._refreshing = threading.Lock()
        self.root = tk.Tk()
        self.root.title("automated-jay   (Shift+Esc = emergency stop)")
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

        af = ttk.LabelFrame(self.root, text="Armies  (tick to make the army match the template)", padding=6)
        af.pack(fill="both", expand=True, padx=10, pady=6)
        self.army_frame = tk.Frame(af, bg="#1d1f1d")
        self.army_frame.pack(fill="both", expand=True)
        self.army_vars: dict[int, tk.BooleanVar] = {}

        pf = ttk.LabelFrame(self.root, text="Provinces where nothing is built", padding=6)
        pf.pack(fill="x", padx=10, pady=6)
        self.prov_lbl = tk.Label(pf, text="", justify="left", anchor="w", bg="#1d1f1d", fg="#d8b0b0",
                                 font=("Segoe UI", 9), wraplength=600)
        self.prov_lbl.pack(fill="x")

        # overlay over the game
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.attributes("-alpha", 0.92)
        self.overlay.geometry("+10+72")
        self.ov_frame = tk.Frame(self.overlay, padx=10, pady=6)
        self.ov_frame.pack()
        self.ov_title = tk.Label(self.ov_frame, font=("Segoe UI", 12, "bold"), anchor="w")
        self.ov_title.pack(fill="x")
        self.ov_detail = tk.Label(self.ov_frame, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=320)
        self.ov_detail.pack(fill="x")
        self.ov_end = None
        if on_end_turn is not None:                    # reachable without leaving the game (the overlay never takes
            self.ov_end = tk.Button(self.ov_frame, text="Build & End Turn", command=self._end_turn,   # focus)
                                    font=("Segoe UI", 9, "bold"), relief="raised", bd=1, padx=8, pady=1,
                                    bg="#3b3b3b", fg="#f0f0f0", activebackground="#5a5a5a", cursor="hand2")
            self.ov_end.pack(anchor="w", pady=(4, 0))
        # a binding on the toplevel already fires for every widget in it (bindtags): binding the children as well
        # toggled pause twice per click, i.e. not at all. Clicks on the End Turn button are not a pause.
        self.overlay.bind("<Button-1>", lambda e: None if e.widget is self.ov_end else self._pause())
        self.ov_hwnd = 0
        self.root.after(100, self._overlay_ready)

        self.root.after(150, self._poll)
        self.root.after(500, self._refresh_async)

    # ---------------------------------------------------------------- thread-safe API for the runner
    def post(self, state: str, headline: str, detail: str = "") -> None:
        self._overlay_style(click_through=state == "automating")     # now, not at the next poll: clicks follow
        self.q.put(("status", state, headline, detail))

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

    def _end_turn(self) -> None:
        threading.Thread(target=self.on_end_turn, daemon=True).start()

    def _overlay_ready(self) -> None:
        self.ov_hwnd = int(self.overlay.wm_frame(), 16)
        self._overlay_style(click_through=False)

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

    def _poll(self) -> None:
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "status":
                    _, state, headline, detail = msg
                    bg, fg = COLORS.get(state, COLORS["waiting"])
                    self.state_lbl.configure(text=headline, fg=fg)
                    for wdg in (self.ov_frame, self.ov_title, self.ov_detail, self.overlay):
                        wdg.configure(bg=bg)
                    self.ov_title.configure(text=headline, fg=fg)
                    self.ov_detail.configure(text=nice(detail), fg="#e8e8e8")
                    if self.ov_end is not None:        # not while a pass is clicking (the overlay lets clicks through)
                        self.ov_end.configure(state="disabled" if state == "automating" else "normal")
                elif kind == "log":
                    self._show_log(msg[1])
                elif kind == "paused":
                    self.pause_btn.configure(text="Resume" if msg[1] else "Pause")
                elif kind == "world":
                    self._show_world(*msg[1:])
                elif kind == "ignorable":
                    self._show_ignorable(msg[1])
        except queue.Empty:
            pass
        self.root.after(150, self._poll)

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
            heroes = [c for c in characters(w, F) if c.embedded_force == 0 and c.subtype in
                      load_automation()["army_builder"]["template"]["heroes"]]
            rows = [(a, delta(a, heroes)) for a in armies(w, F)]
            snap = snapshot(w)
            blocked = dict(snap.blocked_provinces) if snap else {}
            from .recruit import report, sources
            self.recruit_lines = report(sources(w))
            self.q.put(("world", st, rows, blocked, heroes))
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
        for a, d in rows:
            var = self.army_vars.setdefault(a.cqi, tk.BooleanVar())
            on, why = tick_for(a, enabled)          # a tick set for another general (another campaign) is off
            var.set(on)
            row = tk.Frame(self.army_frame, bg="#1d1f1d", pady=3)
            row.pack(fill="x", anchor="w")
            # the tick stores the general's character id and name with the cqi (cqis repeat between campaigns)
            cb = ttk.Checkbutton(row, variable=var, command=lambda a=a, var=var: set_enabled(
                a.cqi, a.general_name, var.get(), a.general_id))
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
