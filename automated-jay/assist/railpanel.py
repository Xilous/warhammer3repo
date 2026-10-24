"""The rail's fold-out panel: everything the main window offers, without leaving the game (player request 2026-10-17:
"make the app's interface be entirely on the widget ... so i can control it without having to alt tab").

Opened and closed with the rail's expand button; sits under the rail and follows it when it is dragged. Like the
rail it never takes focus (the game stays in front while armies are ticked or buttons pressed), and it hides itself
while a pass runs, so it can never be under a click the assistant makes.

Layout (player request 2026-10-23: "no need to constrain its size to be completely vertical ... i dont mind if it took
the whole screen"): the buttons across the top, then three columns, as wide as the screen allows: the turn and the
armies; the next army and the frontline; every setting, in two sub-columns, all shown at once (one tall column
had grown past the screen's height, so the lower settings could not be reached).

Look: Clan Brass (player's pick 2026-10-18, assist/theme.py). Contents: Run now / Pause / Restart /
Exit, treasury - income - Warpstone, "Ignore <id>" for popups that block a pass, what failed this turn and why (only failures, player request 2026-10-21), the
armies with their army-builder tick boxes (saved exactly as the main window does: assist/army.py set_enabled) and
what each costs now and once refilled, the next army (can you afford it: a bar of income against its cost, Create
new playbook army, greyed out with a ✓/✗ list of what it needs), the settings (every option of the strategy files and which steps run when, changed with a click:
assist/settings.py), the frontline settlements, and a link to the full window.
"""
from __future__ import annotations
import tkinter as tk

from . import theme as T

WIDTH = 494                     # one column: the compact rail's width
BAR_W = WIDTH - 40
SET_COL_W = 400                 # each of the two settings sub-columns (one when the screen is too narrow)


def _nice(text: str) -> str:
    from .app import nice
    return nice(text)


FAIL = ("ERROR", "MISSED", "INTERRUPTED", "interrupted", "could not", "not started", "did not", "refused by the game",
        "greyed out", "failed", "NOT confirmed", "still changing", "NOT ENDED")
REASON = "not done, with a reason: "


def failures(lines: list[str]) -> list[str]:
    """The failed parts of a pass's step lines ("step: result | verified | MISSED (memory check): why"), each as
    "step — why". Planned waits ("needs N gold", "saving for ...", "waits for ...") are not failures."""
    out = []
    for line in lines:
        if line.startswith("turn ") or ": " not in line:
            continue
        step, rest = line.split(": ", 1)
        for part in rest.split(" | "):
            part = part.strip()
            if part.startswith(REASON):
                out += [f"{step} — {x.strip()}" for x in part[len(REASON):].split("; ") if x.strip()]
            elif part.startswith("problems: "):
                out += [f"{step} — {x.strip()}" for x in part[len("problems: "):].split("; ")
                        if any(k in x for k in FAIL)]
            elif any(k in part for k in FAIL):
                out.append(f"{step} — {part}")
    return out


class RailPanel:
    def __init__(self, root: tk.Tk, rail, on_run_now, on_pause, on_restart, on_ignore, on_full_window,
                 on_exit=None, on_raise_army=None) -> None:
        self.rail = rail
        self.on_run_now, self.on_pause, self.on_restart = on_run_now, on_pause, on_restart
        self.on_ignore, self.on_full_window = on_ignore, on_full_window
        self.on_raise_army = on_raise_army
        self.open = False
        self.suppressed = False                     # hidden while a pass runs
        self.rows: list = []                        # (army, delta, (can tick, why not)) from the last world read
        self.fin = None                             # assist/army_finance.Finance from the last read
        self.can_raise = False
        self.f_head = T.font(T.HEAD, 11, "bold")
        self.f_label = T.font(T.HEAD, 9)
        self.f_big = T.font(T.MONO, 14)
        self.f_mono = T.font(T.MONO, 9)
        self.f_body = T.font(T.BODY, 9)
        self.f_bold = T.font(T.BODY, 9, "bold")
        self.f_btn = T.font(T.HEAD, 10, "bold")

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.97)
        self.win.configure(bg=T.BASE)
        self.win.withdraw()
        tk.Frame(self.win, bg=T.BRASS, height=3).pack(fill="x")       # the brass stripe, as on the rail
        # a grip strip: the expanded widget moves from here too (player report 2026-10-19: it could not be dragged
        # while expanded, and nothing showed where to grab it); it moves the rail, and the panel follows
        grip = tk.Canvas(self.win, bg=T.PANEL2, height=12, highlightthickness=0, cursor="fleur")
        grip.pack(fill="x")
        grip.bind("<Configure>", lambda e: (grip.delete("all"), [grip.create_rectangle(
            x, y, x + 1.5, y + 1.5, fill=T.MUTED, outline="") for x in range(e.width // 2 - 24, e.width // 2 + 25, 4)
            for y in (4, 8)]))
        grip.bind("<ButtonPress-1>", lambda e: self.rail.drag_start(e.x_root, e.y_root))
        grip.bind("<B1-Motion>", lambda e: self.rail.drag_move(e.x_root, e.y_root))
        grip.bind("<ButtonRelease-1>", lambda e: self.rail.drag_end())
        self.body = tk.Frame(self.win, bg=T.PANEL, padx=18, pady=14)
        self.body.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        bar = tk.Frame(self.body, bg=T.PANEL)
        bar.pack(fill="x")
        self._button(bar, "RUN NOW", self.on_run_now).pack(side="left", padx=(0, 6))
        self.pause_btn = self._button(bar, "PAUSE", self.on_pause)
        self.pause_btn.pack(side="left", padx=(0, 6))
        self._button(bar, "RESTART", self.on_restart).pack(side="left", padx=(0, 6))
        if on_exit is not None:
            ex = self._button(bar, "EXIT", on_exit)
            ex.configure(fg=T.WARN)
            ex.pack(side="left", padx=(0, 6))
        full = tk.Label(bar, text="full window", bg=T.PANEL, fg=T.BRASS, font=self.f_body, cursor="hand2")
        full.pack(side="right")
        full.bind("<Button-1>", lambda e: self.on_full_window())

        cols = tk.Frame(self.body, bg=T.PANEL)
        cols.pack(fill="both", expand=True)
        c1, c2, c3 = (tk.Frame(cols, bg=T.PANEL, width=w) for w in (WIDTH - 36, WIDTH - 36, 0))
        for i, c in enumerate((c1, c2, c3)):
            if i:
                tk.Frame(cols, bg=T.LINE, width=1).pack(side="left", fill="y", padx=14, pady=(12, 0))
            c.pack(side="left", fill="y", anchor="n")

        # treasury - income - Warpstone
        stats = tk.Frame(c1, bg=T.PANEL)
        stats.pack(fill="x", pady=(14, 0))
        self.stat = {}
        for i, key in enumerate(("TREASURY", "INCOME", "WARPSTONE")):
            stats.columnconfigure(i, weight=1, uniform="stat")
            cell = tk.Frame(stats, bg=T.PANEL)
            cell.grid(row=0, column=i, sticky="w")
            tk.Label(cell, text=key, bg=T.PANEL, fg=T.MUTED, font=self.f_label).pack(anchor="w")
            v = tk.Label(cell, text="—", bg=T.PANEL, fg=T.INK, font=self.f_big)
            v.pack(anchor="w")
            self.stat[key] = v
        self.info = tk.Label(c1, text="", bg=T.PANEL, fg=T.MUTED, font=self.f_body, anchor="w")
        self.info.pack(fill="x", pady=(4, 0))
        self.ignore_row = tk.Frame(c1, bg=T.PANEL)
        self.ignore_row.pack(fill="x")

        self._rule(c1)
        self._heading(c1, "THIS TURN  ·  only what failed, and why")
        self.log = tk.Label(c1, text="", bg=T.PANEL, fg=T.TEXT2, font=self.f_body, anchor="nw",
                            justify="left", wraplength=WIDTH - 40)
        self.log.pack(fill="x")

        self._rule(c1)
        self._heading(c1, "ARMIES  ·  tick to refill to the template")
        self.armies = tk.Frame(c1, bg=T.PANEL)
        self.armies.pack(fill="x")
        self.army_vars: dict[int, tk.BooleanVar] = {}

        tk.Frame(c2, bg=T.PANEL, height=14).pack(fill="x")     # level with the first column's numbers
        self._heading(c2, "NEXT ARMY")
        ends = tk.Frame(c2, bg=T.PANEL)
        ends.pack(fill="x")
        self.bar_left = tk.Label(ends, text="", bg=T.PANEL, fg=T.MUTED, font=self.f_body)
        self.bar_left.pack(side="left")
        self.bar_right = tk.Label(ends, text="", bg=T.PANEL, fg=T.MUTED, font=self.f_body)
        self.bar_right.pack(side="right")
        self.bar = tk.Canvas(c2, width=BAR_W, height=14, bg=T.PANEL, highlightthickness=0, bd=0)
        self.bar.pack(fill="x", pady=(4, 4))
        self.verdict = tk.Label(c2, text="", bg=T.PANEL, fg=T.MUTED, font=self.f_bold, anchor="w",
                                justify="left", wraplength=WIDTH - 40)
        self.verdict.pack(fill="x")
        self.detail = tk.Label(c2, text="", bg=T.PANEL, fg=T.MUTED, font=self.f_body, anchor="w",
                               justify="left", wraplength=WIDTH - 40)
        self.detail.pack(fill="x")
        self.raise_btn = tk.Label(c2, text="CREATE NEW PLAYBOOK ARMY", font=self.f_btn, padx=12, pady=8)
        self.raise_btn.bind("<Button-1>", lambda e: self._raise())
        self.checks = tk.Frame(c2, bg=T.PANEL)
        if on_raise_army is not None:
            self.raise_btn.pack(fill="x", pady=(10, 6))
            self.checks.pack(fill="x")
        self._style_raise(False)

        self._rule(c2)
        self._heading(c2, "FRONTLINE  ·  you build there")
        self.front = tk.Label(c2, text="", bg=T.PANEL, fg=T.WARN, font=self.f_body, anchor="w",
                              justify="left", wraplength=WIDTH - 40)
        self.front.pack(fill="x")
        self.template = tk.Label(c2, text="", bg=T.PANEL, fg=T.MUTED, font=self.f_body, anchor="w",
                                 justify="left", wraplength=WIDTH - 40)
        self.template.pack(fill="x", pady=(6, 0))

        self.settings_head = tk.Label(c3, text="", bg=T.PANEL, fg=T.BRASS, font=self.f_head, anchor="w")
        self.settings_head.pack(fill="x", pady=(14, 4))
        self.settings_box = tk.Frame(c3, bg=T.PANEL)
        self.settings_box.pack(fill="both", expand=True)
        self._render_settings()

    # ---------------------------------------------------------------- pieces
    def _button(self, parent, text, cmd):
        b = tk.Label(parent, text=text, bg=T.PANEL, fg=T.INK, font=self.f_btn, padx=10, pady=4, cursor="hand2",
                     highlightthickness=1, highlightbackground=T.LINE, highlightcolor=T.LINE)
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg=T.PANEL2))
        b.bind("<Leave>", lambda e: b.configure(bg=T.PANEL))
        return b

    def _heading(self, parent, text: str) -> None:
        tk.Label(parent, text=text, bg=T.PANEL, fg=T.BRASS, font=self.f_head, anchor="w").pack(fill="x", pady=(0, 4))

    def _rule(self, parent) -> None:
        tk.Frame(parent, bg=T.LINE, height=1).pack(fill="x", pady=(12, 10))

    def _style_raise(self, can: bool) -> None:
        """Pressable only when every hard requirement is met (player rule 2026-10-23, replacing "never locked out" of
        2026-10-21): a Verminlord Warpseer in the Recruit Lord pool, a Warlock Engineer for it, and a province that
        recruits the template. Income going negative after the army is a warning only: it never greys the button.
        can: every hard requirement met (brass, clickable), else greyed out."""
        if can:
            self.raise_btn.configure(bg=T.BRASS, fg=T.ON_BRASS, cursor="hand2", highlightthickness=0)
        else:
            self.raise_btn.configure(bg=T.PANEL, fg=T.MUTED, cursor="arrow", highlightthickness=1,
                                     highlightbackground=T.LINE, highlightcolor=T.LINE)

    # ---------------------------------------------------------------- showing / hiding
    def toggle(self) -> None:
        self.open = not self.open
        self.rail.panel_open = self.open
        self.rail.draw()
        self.place()

    def suppress(self, on: bool) -> None:
        if on != self.suppressed:
            self.suppressed = on
            self.place()

    def place(self) -> None:
        if not self.open or self.suppressed:
            self.win.withdraw()
            return
        self.win.update_idletasks()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        w = min(sw, self.win.winfo_reqwidth())
        # the whole window's height: the stripe and the grip strip sit above the body (2026-10-23: sized from the body
        # alone, the window came out 12 px short and the last Steps row was cut off)
        h = min(sh, self.win.winfo_reqheight())
        rx, ry = self.rail.win.winfo_x(), self.rail.win.winfo_y()
        x = max(0, min(rx, sw - w))                  # under the rail where it fits, else pulled back onto the screen
        y = ry + self.rail.win.winfo_height() + 6
        if y + h > sh:                               # no room below: above the rail, else as low as it fits (it may
            y = ry - h - 6 if ry - h - 6 >= 0 else max(0, sh - h)   # then lie under the rail, which stays on top)
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.win.deiconify()
        self.win.lift()
        self.rail.win.lift()
        self._no_activate()

    def _no_activate(self) -> None:
        import ctypes
        import win32con
        try:
            hwnd = int(self.win.wm_frame(), 16)
            u = ctypes.windll.user32
            u.SetWindowLongW(hwnd, win32con.GWL_EXSTYLE,
                             u.GetWindowLongW(hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_NOACTIVATE)
        except Exception:
            pass

    # ---------------------------------------------------------------- content
    def set_paused(self, paused: bool) -> None:
        self.pause_btn.configure(text="RESUME" if paused else "PAUSE", fg=T.WARN if paused else T.INK)

    def show_log(self, lines: list[str]) -> None:
        """Only what failed this turn, each with the reason the step gave (player request 2026-10-21: the rest need
        not be read at once; the full window and runs/assistant-*.jsonl keep everything)."""
        head = next((x for x in lines if x.startswith("turn ")), None)
        bad = failures(lines)
        if not lines:
            text, col = "nothing yet", T.MUTED
        elif not bad:
            text, col = (head + ": " if head else "") + "nothing failed", T.MUTED
        else:
            text, col = "\n".join(_nice(x) for x in bad[-12:]), T.RED
        self.log.configure(text=text, fg=col)
        self.place()

    def _raise(self) -> None:
        if self.on_raise_army is not None and self.can_raise:
            self.on_raise_army()

    def show_finance(self, f: dict) -> None:
        """f: {"fin": Finance or None, "verdict", "ok", "can", "checks": [(label, met, why)], "warpstone"}."""
        fin = f.get("fin")
        self.fin = fin
        self.stat["INCOME"].configure(text=T.money(fin.income, sign=True) if fin else "—",
                                      fg=(T.GOOD if fin and fin.income >= 0 else T.WARN))
        ws = f.get("warpstone")
        self.stat["WARPSTONE"].configure(text=T.money(ws) if ws is not None else "—")
        self.verdict.configure(text=f.get("verdict", ""), fg=T.GOOD if f.get("ok") else T.WARN)
        self._draw_bar(fin)
        self.can_raise = bool(f.get("can"))
        self._style_raise(self.can_raise)
        for c in self.checks.winfo_children():
            c.destroy()
        if f.get("status"):
            tk.Label(self.checks, text=f["status"], bg=T.PANEL, fg=T.BRASS, font=self.f_body, anchor="w",
                     justify="left", wraplength=BAR_W).pack(fill="x")
        for label, met, why in f.get("checks", []):
            tk.Label(self.checks, text=("✓ " if met else "✗ ") + label + ("" if met else f"  ({why})"),
                     bg=T.PANEL, fg=T.GOOD if met else T.MUTED, font=self.f_body, anchor="w").pack(fill="x")
        self._render_armies()
        self.place()

    def _draw_bar(self, fin) -> None:
        """Income against what the ticked refills and the next army add: green what is left, red the shortfall."""
        cv = self.bar
        cv.delete("all")
        W = BAR_W
        cv.create_rectangle(0, 0, W, 14, fill="#2a2219", outline="#2a2219")
        if fin is None:
            self.bar_left.configure(text="")
            self.bar_right.configure(text="")
            self.detail.configure(text="")
            return
        cost = fin.ticked_extra + fin.next_army
        income = max(0, fin.income)
        self.bar_left.configure(text=f"Income {T.money(fin.income, sign=True)}")
        self.bar_right.configure(text=f"after it {T.money(fin.after_next, sign=True)}",
                                 fg=T.GOOD if fin.after_next >= 0 else T.WARN)
        if fin.after_next >= 0:                       # brass: what it costs, green: what is left
            spent = W * cost / income if income else 0
            cv.create_rectangle(0, 0, spent, 14, fill=T.BRASS, outline=T.BRASS)
            cv.create_rectangle(spent, 0, W, 14, fill=T.GOOD, outline=T.GOOD)
        else:                                         # green: the income, red: the shortfall
            share = W * income / cost if cost else 0
            cv.create_rectangle(0, 0, share, 14, fill=T.GOOD, outline=T.GOOD)
            cv.create_rectangle(share, 0, W, 14, fill=T.BAD, outline=T.BAD)
        parts = []
        if fin.ticked_extra:
            parts.append(f"refills {T.money(-fin.ticked_extra, sign=True)}")
        parts.append(f"next army {T.money(-fin.next_army, sign=True)} ({fin.next_own:,} its own, "
                     f"{fin.next_supply:,} Supply Lines)")
        parts.append(f"Supply Lines {fin.supply_pct}% per extra army ({fin.difficulty})")
        self.detail.configure(text=" · ".join(parts))

    def show_template(self, status) -> None:
        if not status:
            return
        ok, text = status
        self.template.configure(text=("TEMPLATE ✓ " if ok else "TEMPLATE: ") + text, fg=T.GOOD if ok else T.WARN)
        self.place()

    def show_ignorable(self, ids: list[str]) -> None:
        for c in self.ignore_row.winfo_children():
            c.destroy()
        for cid in ids:
            b = self._button(self.ignore_row, f"IGNORE {cid}", lambda c=cid: self.on_ignore(c))
            b.configure(fg=T.WARN)
            b.pack(side="left", pady=(8, 0), padx=(0, 6))
        self.place()

    def show_world(self, st, rows, blocked, heroes=()) -> None:
        if st is not None:
            self.stat["TREASURY"].configure(text=T.money(st.treasury) if st.turn is not None else "—")
            self.info.configure(text=f"Turn {st.turn}" if st.turn is not None else "no campaign loaded")
        self.rows = rows
        self._render_armies()
        if "error" in blocked:
            self.front.configure(text="could not read the campaign: " + blocked["error"], fg=T.RED)
        else:
            from .build import buildings_setting
            if not buildings_setting("never_build_in_provinces_adjacent_to_enemy_at_war", False):
                self.front.configure(text="rule off: every settlement is built (Buildings settings)", fg=T.MUTED)
            else:
                self.front.configure(text="\n".join(f"{_nice(p)}" for p in blocked) or "none", fg=T.WARN)
        self.place()

    # ---------------------------------------------------------------- settings (player rule 2026-10-21)
    def _render_settings(self) -> None:
        """Every setting (assist/settings.py) and which steps run when, changed with a click between turns: a switch
        or a choice is clicked, a number has - and +. All shown at once, the groups split over two sub-columns (one on
        a narrow screen) so the panel stays within the screen's height (player report 2026-10-23)."""
        from . import settings as S
        self.settings_head.configure(text="SETTINGS  ·  click to change")
        for c in self.settings_box.winfo_children():
            c.destroy()
        n_cols = 2 if self.win.winfo_screenwidth() >= 2 * (WIDTH + 30) + 2 * SET_COL_W else 1
        subs = [tk.Frame(self.settings_box, bg=T.PANEL, width=SET_COL_W) for _ in range(n_cols)]
        for i, f in enumerate(subs):
            self.settings_box.columnconfigure(i, minsize=SET_COL_W)
            f.grid(row=0, column=i, sticky="new", padx=(0 if i == 0 else 18, 0))

        def group(parent, text):
            tk.Label(parent, text=text.upper(), bg=T.PANEL, fg=T.MUTED, font=self.f_label,
                     anchor="w").pack(fill="x", pady=(8, 0))

        def row(parent, label, value, on_click, on_minus=None):
            r = tk.Frame(parent, bg=T.PANEL)
            r.pack(fill="x", pady=(2, 0))
            tk.Label(r, text=label, bg=T.PANEL, fg=T.INK, font=self.f_body, anchor="w").pack(side="left")
            if on_minus is not None:
                plus = tk.Label(r, text=" + ", bg=T.PANEL2, fg=T.INK, font=self.f_bold, cursor="hand2")
                plus.pack(side="right")
                plus.bind("<Button-1>", lambda e: on_click())
            v = tk.Label(r, text=value, bg=T.PANEL, fg=T.BRASS, font=self.f_mono, cursor="hand2", padx=6)
            v.pack(side="right")
            if on_minus is None:
                v.bind("<Button-1>", lambda e: on_click())
            else:
                minus = tk.Label(r, text=" − ", bg=T.PANEL2, fg=T.INK, font=self.f_bold, cursor="hand2")
                minus.pack(side="right")
                minus.bind("<Button-1>", lambda e: on_minus())

        def change(s, d):
            try:
                S.nudge(s, d)
            except Exception as ex:                    # noqa: BLE001  (shown, never a crash of the widget)
                self.settings_head.configure(text=f"SETTINGS  ·  could not save: {ex}")
                return
            self._render_settings()
            self.place()

        def flip(phase, name):
            S.set_step(phase, name, not S.step_on(phase, name))
            self._render_settings()
            self.place()

        groups: dict[str, list] = {}
        for s in S.SETTINGS:
            groups.setdefault(s.group, []).append(s)
        steps = S.step_order()
        blocks = [(g, len(items) + 1) for g, items in groups.items()] + [(None, len(steps) + 1)]
        half, done, col = sum(n for _g, n in blocks) / n_cols, 0, 0
        for g, n in blocks:                            # in order; the next sub-column once this one holds its half
            if col < n_cols - 1 and done and done + n / 2 > half * (col + 1):
                col += 1
            done += n
            parent = subs[col]
            if g is not None:
                group(parent, g)
                for s in groups[g]:
                    number = s.kind in ("int", "float")
                    row(parent, s.label, S.shown(s), lambda s=s: change(s, +1),
                        (lambda s=s: change(s, -1)) if number else None)
                continue
            group(parent, "Steps  ·  turn start / Build & End Turn")
            for name in steps:
                r = tk.Frame(parent, bg=T.PANEL)
                r.pack(fill="x", pady=(2, 0))
                tk.Label(r, text=name, bg=T.PANEL, fg=T.INK, font=self.f_body, anchor="w").pack(side="left")
                for phase, what in reversed(S.PHASES):
                    on = S.step_on(phase, name)
                    b = tk.Label(r, text=f"{what}: {'on' if on else 'off'}", bg=T.PANEL,
                                 fg=T.BRASS if on else T.MUTED, font=self.f_mono, cursor="hand2", padx=6)
                    b.pack(side="right")
                    b.bind("<Button-1>", lambda e, ph=phase, n=name: flip(ph, n))

    def _render_armies(self) -> None:
        """Rebuilt only when what it shows changed (2026-10-18: rebuilt on every refresh, a new tick box flashed
        white for a frame before its colours applied)."""
        from .army import enabled_armies, set_enabled, tick_for
        enabled = enabled_armies()
        cost = {a.cqi: a for a in (self.fin.armies if self.fin else [])}
        sig = tuple((a.cqi, a.general_name, len(a.units), len(a.queued), a.region, tick_for(a, enabled), can, why_not,
                     d.summary(), d.matches, bool(d.missing or d.heroes_missing),
                     (cost[a.cqi].now, cost[a.cqi].refilled, cost[a.cqi].removed,
                      cost[a.cqi].income_if_refilled) if a.cqi in cost else None)
                    for a, d, (can, why_not) in self.rows)
        if sig == getattr(self, "_armies_sig", None):
            return
        self._armies_sig = sig
        for c in self.armies.winfo_children():
            c.destroy()
        if not self.rows:
            tk.Label(self.armies, text="no field armies", bg=T.PANEL, fg=T.MUTED, font=self.f_body).pack(anchor="w")
        for a, d, (can, why_not) in self.rows:
            var = self.army_vars.setdefault(a.cqi, tk.BooleanVar())
            on, why = tick_for(a, enabled)
            var.set(on)
            locked = not on and not can                 # a refill that cannot happen cannot be ticked; a tick can go
            row = tk.Frame(self.armies, bg=T.PANEL)
            row.pack(fill="x", pady=(4, 0))
            tk.Checkbutton(row, variable=var, bg=T.PANEL, activebackground=T.PANEL, selectcolor=T.PANEL2,
                           fg=T.INK, highlightthickness=0, bd=0, cursor="arrow" if locked else "hand2",
                           state="disabled" if locked else "normal",
                           command=lambda a=a, var=var: set_enabled(a.cqi, a.general_name, var.get(), a.general_id, a.turn, a.rank)
                           ).pack(side="left")
            tk.Label(row, text=a.general_name, bg=T.PANEL, fg=T.INK, font=self.f_bold).pack(side="left")
            size = f"{len(a.units)}" + (f"+{len(a.queued)}" if a.queued else "")
            tk.Label(row, text=f"  {size} units · {_nice(a.region or '')}", bg=T.PANEL, fg=T.MUTED,
                     font=self.f_body).pack(side="left")
            c = cost.get(a.cqi)
            if c is not None:
                money = f"{c.now:,}" + (f" → {c.refilled:,}" if c.refilled != c.now else "")
                tk.Label(row, text=money, bg=T.PANEL, fg=T.INK, font=self.f_mono).pack(side="right")
            note = why or d.summary()
            if c is not None and c.removed:
                note += f" · {c.removed} disbanded on refill"
            if c is not None and c.refilled != c.now and not d.matches:
                inc = c.income_if_refilled
                verdict = "✓ affordable" if inc >= 0 else "✗ not affordable"
                state = ("ticked" if on else "you can tick it now" if can else
                         "can't be ticked yet: " + (why_not.replace("cannot refill: ", "") if why_not else "not possible"))
                word = "rebuilt into the playbook army" if c.removed else "refilled"     # units disbanded: rebuilt
                tk.Label(self.armies, text=f"if {word}: {c.now:,} → {c.refilled:,}/turn · income after {inc:+,}/turn"
                         f"  {verdict} · {state}", bg=T.PANEL, fg=T.GOOD if inc >= 0 else T.WARN, font=self.f_body,
                         anchor="w", justify="left", wraplength=WIDTH - 70, padx=24).pack(fill="x")
            tk.Label(self.armies, text=note, bg=T.PANEL, fg=(T.RED if why else T.GOOD if d.matches else T.MUTED),
                     font=self.f_body, anchor="w", justify="left", wraplength=WIDTH - 70, padx=24).pack(fill="x")

