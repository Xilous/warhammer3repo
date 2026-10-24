"""The full-screen view behind the collapsed bar (player request 2026-10-17: "make the app's interface be entirely on
the widget ... so i can control it without having to alt tab"; redesigned 2026-10-24 after the player's review of
https://claude.ai/artifact/2siWTbdSqXSmnzky6z2CXr: "the expanded ui could take the entire screen", plain words,
a section for what the army builder has in progress and one for the armies' composition, settings shown only when
asked for).

Opened and closed from the bar's arrow (or this view's own); it covers the screen, never takes focus (the game stays
in front), and hides itself while a pass runs, so it can never be under a click the assistant makes.

Layout: a top bar (the state in one sentence, Gold / Income per turn / Warpstone, the buttons), then three columns:
  NEEDS YOU + THIS TURN    what waits on the player, then one plain line per step (assist/widget_data.py)
  ARMY BUILDER             in progress (each refill or asked-for army: what it does now, what is next), then new
                           armies (asked for, can be raised now, the three limits, Ask for one more army, the
                           upkeep numbers: the player decides what is affordable)
  ARMIES                   each army's units against the playbook, its upkeep, its refill switch
SETTINGS is a drawer over the right side, opened from its button (every setting of assist/settings.py and which
steps run when, changed with a click).

Look: Clan Brass (player's pick 2026-10-18, assist/theme.py).
"""
from __future__ import annotations
import tkinter as tk

from . import theme as T

WIDTH = 494                     # (kept for callers: the collapsed bar's width)
BAR_W = WIDTH - 40
COL1, COL2 = 420, 560           # the first two columns; the armies take the rest
DRAWER_W = 940


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


class Scroll(tk.Frame):
    """A column that scrolls with the mouse wheel when its content is taller than the screen."""

    def __init__(self, parent, width: int | None = None, **kw) -> None:
        super().__init__(parent, bg=T.BASE, **kw)
        self.cv = tk.Canvas(self, bg=T.BASE, highlightthickness=0, bd=0, width=width or 1)
        self.cv.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.cv, bg=T.BASE)
        self._win = self.cv.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfigure(self._win, width=e.width))
        for wdg in (self.cv, self.inner):
            wdg.bind("<Enter>", lambda e: self.cv.bind_all("<MouseWheel>", self._wheel))
            wdg.bind("<Leave>", lambda e: self.cv.unbind_all("<MouseWheel>"))

    def _wheel(self, e) -> None:
        if self.inner.winfo_reqheight() > self.cv.winfo_height():
            self.cv.yview_scroll(int(-e.delta / 120) * 3, "units")


class RailPanel:
    def __init__(self, root: tk.Tk, rail, on_run_now, on_pause, on_restart, on_ignore, on_full_window,
                 on_exit=None, on_raise_army=None, on_end_turn=None) -> None:
        self.rail = rail
        self.on_run_now, self.on_pause, self.on_restart = on_run_now, on_pause, on_restart
        self.on_ignore, self.on_full_window = on_ignore, on_full_window
        self.on_raise_army, self.on_end_turn, self.on_exit = on_raise_army, on_end_turn, on_exit
        self.open = False
        self.suppressed = False                     # hidden while a pass runs
        self.rows: list = []                        # (army, delta, (can tick, why not)) from the last world read
        self.fin = None
        self.can_raise = False
        self.paused = False
        self.status = ("waiting", "WAITING", "")
        self.ignorable: list[str] = []
        self.log_lines: list[str] = []
        self.builder: dict = {}                     # {"progress": [...], "status": army_status()}
        self._sigs: dict = {}
        self.f_title = T.font(T.HEAD, 22, "bold")
        self.f_head = T.font(T.HEAD, 14, "bold")
        self.f_small = T.font(T.BODY, 9, "bold")
        self.f_big = T.font(T.MONO, 18)
        self.f_mono = T.font(T.MONO, 10)
        self.f_body = T.font(T.BODY, 11)
        self.f_body_s = T.font(T.BODY, 10)
        self.f_bold = T.font(T.BODY, 11, "bold")
        self.f_name = T.font(T.BODY, 12, "bold")
        self.f_btn = T.font(T.HEAD, 11, "bold")

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=T.BASE)
        self.win.withdraw()

        # ---- top bar
        tk.Frame(self.win, bg=T.BRASS, height=4).pack(fill="x")
        top = tk.Frame(self.win, bg=T.PANEL, padx=24, pady=14)
        top.pack(fill="x")
        st = tk.Frame(top, bg=T.PANEL)
        st.pack(side="left")
        self.title = tk.Label(st, text="WAITING", bg=T.PANEL, fg=T.TITLE, font=self.f_title, anchor="w")
        self.title.pack(anchor="w")
        self.subtitle = tk.Label(st, text="", bg=T.PANEL, fg=T.TEXT2, font=self.f_body, anchor="w")
        self.subtitle.pack(anchor="w")
        stats = tk.Frame(top, bg=T.PANEL)
        stats.pack(side="left", padx=(40, 0))
        self.stat = {}
        for key in ("Gold", "Income per turn", "Warpstone"):
            cell = tk.Frame(stats, bg=T.PANEL)
            cell.pack(side="left", padx=(0, 32))
            tk.Label(cell, text=key, bg=T.PANEL, fg=T.MUTED, font=self.f_body_s).pack(anchor="w")
            v = tk.Label(cell, text="—", bg=T.PANEL, fg=T.TITLE, font=self.f_big)
            v.pack(anchor="w")
            self.stat[key] = v
        acts = tk.Frame(top, bg=T.PANEL)
        acts.pack(side="right")
        if on_end_turn is not None:
            self._button(acts, "BUILD & END TURN", on_end_turn, primary=True).pack(side="left", padx=(0, 8))
        self._button(acts, "RUN NOW", self.on_run_now).pack(side="left", padx=(0, 8))
        self.pause_btn = self._button(acts, "PAUSE", self.on_pause)
        self.pause_btn.pack(side="left", padx=(0, 8))
        self._button(acts, "RESTART", self.on_restart).pack(side="left", padx=(0, 8))
        self.set_btn = self._button(acts, "SETTINGS", self._toggle_settings)
        self.set_btn.pack(side="left", padx=(0, 8))
        if on_exit is not None:
            ex = self._button(acts, "EXIT", on_exit)
            ex.configure(fg=T.WARN)
            ex.pack(side="left", padx=(0, 8))
        self._button(acts, "  ▲  ", self.toggle).pack(side="left")
        tk.Frame(self.win, bg=T.LINE, height=1).pack(fill="x")

        # ---- three columns
        self.body = tk.Frame(self.win, bg=T.BASE)
        self.body.pack(fill="both", expand=True)
        c1 = Scroll(self.body, width=COL1)
        c1.pack(side="left", fill="y")
        tk.Frame(self.body, bg=T.LINE, width=1).pack(side="left", fill="y")
        c2 = Scroll(self.body, width=COL2)
        c2.pack(side="left", fill="y")
        tk.Frame(self.body, bg=T.LINE, width=1).pack(side="left", fill="y")
        c3 = Scroll(self.body)
        c3.pack(side="left", fill="both", expand=True)
        self.c1, self.c2, self.c3 = (self._pad(c.inner) for c in (c1, c2, c3))

        self._heading(self.c1, "NEEDS YOU")
        self.needs_box = tk.Frame(self.c1, bg=T.BASE)
        self.needs_box.pack(fill="x", pady=(0, 24))
        self._heading(self.c1, "THIS TURN")
        self.steps_box = tk.Frame(self.c1, bg=T.BASE)
        self.steps_box.pack(fill="x")
        tk.Label(self.c1, text="Brass: done. Amber: waiting on you or the game. Red: failed, with why.",
                 bg=T.BASE, fg=T.MUTED, font=self.f_body_s, anchor="w", justify="left",
                 wraplength=COL1 - 60).pack(fill="x", pady=(10, 0))

        self._heading(self.c2, "ARMY BUILDER")
        self._sub(self.c2, "IN PROGRESS")
        self.prog_box = tk.Frame(self.c2, bg=T.BASE)
        self.prog_box.pack(fill="x")
        tk.Frame(self.c2, bg=T.LINE, height=1).pack(fill="x", pady=(20, 16))
        self._sub(self.c2, "NEW ARMIES")
        tiles = tk.Frame(self.c2, bg=T.BASE)
        tiles.pack(fill="x")
        self.tile = {}
        for i, key in enumerate(("Asked for", "Can be raised now")):
            tiles.columnconfigure(i, weight=1, uniform="tile")
            cell = tk.Frame(tiles, bg=T.PANEL, highlightthickness=1, highlightbackground=T.LINE, padx=14, pady=10)
            cell.grid(row=0, column=i, sticky="ew", padx=(0, 12 if i == 0 else 0))
            tk.Label(cell, text=key, bg=T.PANEL, fg=T.MUTED, font=self.f_body_s).pack(anchor="w")
            v = tk.Label(cell, text="0", bg=T.PANEL, fg=T.TITLE, font=self.f_big)
            v.pack(anchor="w")
            self.tile[key] = v
        tk.Label(self.c2, text="The lowest of these sets how many can be raised now:", bg=T.BASE, fg=T.TEXT2,
                 font=self.f_body, anchor="w").pack(fill="x", pady=(12, 4))
        self.limits_box = tk.Frame(self.c2, bg=T.BASE)
        self.limits_box.pack(fill="x")
        self.raise_btn = tk.Label(self.c2, text="ASK FOR ONE MORE ARMY", font=self.f_btn, padx=12, pady=12)
        self.raise_btn.bind("<Button-1>", lambda e: self._raise())
        if on_raise_army is not None:
            self.raise_btn.pack(fill="x", pady=(14, 6))
        self.raise_note = self._text(self.c2, "", T.MUTED, small=True)
        self.money_box = tk.Frame(self.c2, bg=T.BASE)
        self.money_box.pack(fill="x", pady=(8, 0))
        self._text(self.c2, "You decide what you can afford; these are the numbers.", T.MUTED, small=True)
        self._style_raise(False)

        head3 = tk.Frame(self.c3, bg=T.BASE)
        head3.pack(fill="x")
        tk.Label(head3, text="ARMIES", bg=T.BASE, fg=T.BRASS, font=self.f_head).pack(side="left")
        self.playbook = tk.Label(head3, text="", bg=T.BASE, fg=T.MUTED, font=self.f_body_s)
        self.playbook.pack(side="left", padx=(16, 0))
        self.armies = tk.Frame(self.c3, bg=T.BASE)
        self.armies.pack(fill="both", expand=True, pady=(12, 0))

        # ---- settings drawer (shown on request)
        self.drawer = tk.Frame(self.win, bg=T.PANEL, highlightthickness=2, highlightbackground=T.BRASS)
        dh = tk.Frame(self.drawer, bg=T.PANEL, padx=28, pady=18)
        dh.pack(fill="x")
        self.settings_head = tk.Label(dh, text="SETTINGS", bg=T.PANEL, fg=T.BRASS, font=self.f_head)
        self.settings_head.pack(side="left")
        self._button(dh, "DONE", self._toggle_settings).pack(side="right")
        tk.Label(dh, text="Applies from the next pass.", bg=T.PANEL, fg=T.MUTED, font=self.f_body_s).pack(
            side="right", padx=12)
        tk.Frame(self.drawer, bg=T.LINE, height=1).pack(fill="x")
        self.settings_box = tk.Frame(self.drawer, bg=T.PANEL, padx=28, pady=12)
        self.settings_box.pack(fill="both", expand=True)
        self.drawer_open = False

    # ---------------------------------------------------------------- pieces
    def _pad(self, inner):
        f = tk.Frame(inner, bg=T.BASE, padx=28, pady=24)
        f.pack(fill="both", expand=True)
        return f

    def _button(self, parent, text, cmd, primary: bool = False):
        bg, fg = (T.BRASS, T.ON_BRASS) if primary else (T.PANEL, T.INK)
        b = tk.Label(parent, text=text, bg=bg, fg=fg, font=self.f_btn, padx=14, pady=8, cursor="hand2",
                     highlightthickness=0 if primary else 1, highlightbackground=T.LINE, highlightcolor=T.LINE)
        b.bind("<Button-1>", lambda e: cmd() if cmd else None)
        hover = T.BRASS_HI if primary else T.PANEL2
        b.bind("<Enter>", lambda e: b.configure(bg=hover))
        b.bind("<Leave>", lambda e: b.configure(bg=bg))
        return b

    def _heading(self, parent, text: str) -> None:
        tk.Label(parent, text=text, bg=T.BASE, fg=T.BRASS, font=self.f_head, anchor="w").pack(fill="x", pady=(0, 10))

    def _sub(self, parent, text: str) -> None:
        tk.Label(parent, text=text, bg=T.BASE, fg=T.MUTED, font=self.f_small, anchor="w").pack(fill="x", pady=(0, 8))

    def _text(self, parent, text, fg=None, small=False, width=COL2 - 60, bg=None):
        lb = tk.Label(parent, text=text, bg=bg or T.BASE, fg=fg or T.INK, font=self.f_body_s if small else self.f_body,
                      anchor="w", justify="left", wraplength=width)
        lb.pack(fill="x")
        return lb

    def _clear(self, frame) -> None:
        for c in frame.winfo_children():
            c.destroy()

    def _changed(self, key, sig) -> bool:
        """Rebuilt only when what it shows changed (2026-10-18: a rebuilt tick box flashed white for a frame)."""
        if self._sigs.get(key) == sig:
            return False
        self._sigs[key] = sig
        return True

    def _style_raise(self, can: bool) -> None:
        """Brass and clickable while one more army can be asked for (the hard requirements, new_army.capacity), greyed
        once every army that can be raised now is asked for. Affordability never greys it: the player decides."""
        if can:
            self.raise_btn.configure(text="ASK FOR ONE MORE ARMY", bg=T.BRASS, fg=T.ON_BRASS, cursor="hand2",
                                     highlightthickness=0)
        else:
            self.raise_btn.configure(bg=T.PANEL, fg=T.DIM, cursor="arrow", highlightthickness=1,
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
            if not self.rail.win.winfo_viewable():
                self.rail.win.deiconify()
            return
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"{sw}x{sh}+0+0")
        if self.drawer_open:
            self.drawer.place(in_=self.body, relx=1.0, y=0, anchor="ne", width=min(DRAWER_W, sw), relheight=1.0)
            self.drawer.lift()
        else:
            self.drawer.place_forget()
        self.win.deiconify()
        self.win.lift()
        self.rail.win.withdraw()                     # the full view covers the screen; the bar comes back on close
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

    def _toggle_settings(self) -> None:
        self.drawer_open = not self.drawer_open
        self.set_btn.configure(bg=T.BRASS if self.drawer_open else T.PANEL,
                               fg=T.ON_BRASS if self.drawer_open else T.INK)
        if self.drawer_open:
            self._render_settings()
        self.place()

    # ---------------------------------------------------------------- content
    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        self.pause_btn.configure(text="RESUME" if paused else "PAUSE", fg=T.WARN if paused else T.INK)
        self._render_top()
        self._render_needs()

    def show_status(self, state: str, headline: str, detail: str) -> None:
        self.status = (state, headline, detail)
        self._render_top()
        self._render_needs()

    def show_log(self, lines: list[str]) -> None:
        """THIS TURN: one plain line per step of the last pass (assist/widget_data.steps)."""
        self.log_lines = list(lines or [])
        from .widget_data import steps
        rows = steps(self.log_lines)
        if self._changed("steps", tuple((r["name"], r["state"], r["text"]) for r in rows)):
            self._clear(self.steps_box)
            if not rows:
                self._text(self.steps_box, "No pass has run this turn yet.", T.MUTED, width=COL1 - 60)
            col = {"done": T.BRASS, "wait": T.AMBER, "failed": T.RED}
            for r in rows:
                row = tk.Frame(self.steps_box, bg=T.BASE)
                row.pack(fill="x")
                tk.Label(row, text=r["name"].upper(), bg=T.BASE, fg=col.get(r["state"], T.MUTED), font=self.f_btn,
                         width=10, anchor="nw").pack(side="left", anchor="n", pady=8)
                tk.Label(row, text=r["text"], bg=T.BASE, fg=T.INK, font=self.f_body, anchor="w", justify="left",
                         wraplength=COL1 - 160).pack(side="left", fill="x", pady=8)
                tk.Frame(self.steps_box, bg=T.LINE, height=1).pack(fill="x")
        self._render_needs()
        self.place()

    def _render_top(self) -> None:
        state, headline, detail = self.status
        self.title.configure(text=headline.upper())
        from .widget_data import needs
        waiting = needs(state, headline, detail)
        if self.paused:
            sub = "Paused: nothing runs until you press RESUME."
        elif state == "automating":
            sub = "Working. Hands off the mouse until it is done; Shift+Esc stops it."
        elif waiting:
            sub = f"{waiting[0]['title']}. {waiting[0]['text']}"
        else:
            first = next((ln for ln in (detail or "").splitlines() if ln.strip()), "")
            sub = _nice(first)[:140]
            sub = sub[:1].upper() + sub[1:]
        self.subtitle.configure(text=sub)

    def _render_needs(self) -> None:
        from .widget_data import needs, steps
        state, headline, detail = self.status
        bad = [s for s in steps(self.log_lines) if s["state"] == "failed"]
        items = needs("paused" if self.paused and state != "paused" else state, headline, detail, self.ignorable, bad)
        if not self._changed("needs", tuple((i["title"], i["text"], i["ignore"]) for i in items)):
            return
        self._clear(self.needs_box)
        if not items:
            self._text(self.needs_box, "Nothing needs you.", T.MUTED, width=COL1 - 60)
            return
        for it in items:
            card = tk.Frame(self.needs_box, bg=T.PANEL2, highlightthickness=1, highlightbackground="#5c4c22",
                            padx=14, pady=12)
            card.pack(fill="x", pady=(0, 8))
            tk.Label(card, text=it["title"], bg=T.PANEL2, fg=T.AMBER, font=self.f_name, anchor="w", justify="left",
                     wraplength=COL1 - 90).pack(fill="x")
            tk.Label(card, text=it["text"], bg=T.PANEL2, fg=T.TEXT2, font=self.f_body, anchor="w", justify="left",
                     wraplength=COL1 - 90).pack(fill="x", pady=(4, 0))
            if it["ignore"]:
                b = self._button(card, "IGNORE IT", lambda c=it["ignore"]: self.on_ignore(c))
                b.pack(anchor="w", pady=(8, 0))

    def show_ignorable(self, ids: list[str]) -> None:
        self.ignorable = list(ids)
        self._render_needs()
        self.place()

    def show_template(self, status) -> None:
        pass                                          # (the playbook line under ARMIES and the limits say it now)

    def show_world(self, st, rows, blocked, heroes=()) -> None:
        if st is not None:
            self.stat["Gold"].configure(text=T.money(st.treasury) if st.turn is not None else "—")
        self.rows = rows
        self._render_armies()
        self.place()

    def show_builder(self, progress: list[dict], status: dict) -> None:
        """ARMY BUILDER: in progress, and the new-army numbers (assist/widget_data.progress, army_finance.army_status)."""
        self.builder = {"progress": progress, "status": status}
        if self._changed("progress", tuple((p["name"], p["kind"], p["now"], p["next"], tuple(p["chips"]))
                                           for p in progress)):
            self._clear(self.prog_box)
            if not progress:
                self._text(self.prog_box, "Nothing in progress. Tick an army under ARMIES to refill it, or ask for a "
                           "new one below.", T.MUTED)
            for p in progress:
                card = tk.Frame(self.prog_box, bg=T.PANEL, highlightthickness=1, highlightbackground=T.LINE,
                                padx=16, pady=12)
                card.pack(fill="x", pady=(0, 10))
                h = tk.Frame(card, bg=T.PANEL)
                h.pack(fill="x")
                tk.Label(h, text=p["name"], bg=T.PANEL, fg=T.TITLE, font=self.f_name).pack(side="left")
                tk.Label(h, text=p["kind"].upper(), bg=T.PANEL, fg=T.MUTED, font=self.f_small).pack(side="right")
                self._text(card, p["now"], T.INK, width=COL2 - 100, bg=T.PANEL)
                if p["next"]:
                    self._text(card, p["next"], T.TEXT2, small=True, width=COL2 - 100, bg=T.PANEL)
                chips = tk.Frame(card, bg=T.PANEL)
                chips.pack(fill="x", pady=(6, 0))
                for text, ok in p["chips"]:
                    tk.Label(chips, text=text, bg=T.PANEL, fg=T.GOOD if ok else T.WARN, font=self.f_body_s,
                             highlightthickness=1, highlightbackground="#5a6b3e" if ok else "#6b4a3a",
                             padx=8, pady=2).pack(side="left", padx=(0, 6))
        req, can = status.get("requested", 0), status.get("can_raise", 0)
        self.tile["Asked for"].configure(text=str(req))
        self.tile["Can be raised now"].configure(text=str(max(0, can - req)))
        lim = status.get("limits", {})
        labels = {"provinces": "Free provinces that recruit the whole playbook",
                  "engineers": "Warlock Engineers (free, plus room under the cap)",
                  "warpseers": "Verminlord Warpseers in the Recruit Lord pool"}
        if self._changed("limits", tuple(sorted(lim.items()))):
            self._clear(self.limits_box)
            low = min(lim.values()) if lim else 0
            for k, v in lim.items():
                r = tk.Frame(self.limits_box, bg=T.BASE)
                r.pack(fill="x")
                tk.Label(r, text=labels.get(k, k), bg=T.BASE, fg=T.INK, font=self.f_body).pack(side="left", pady=5)
                tk.Label(r, text=str(v), bg=T.BASE, font=self.f_mono,
                         fg=T.RED if v <= 0 else T.AMBER if v == low else T.GOOD).pack(side="right")
                tk.Frame(self.limits_box, bg="#2a2219", height=1).pack(fill="x")
        self.can_raise = can > req
        self._style_raise(self.can_raise)
        if not self.can_raise:
            self.raise_btn.configure(text="NONE CAN BE RAISED NOW" if can <= 0 else
                                     "EVERY ARMY THAT CAN BE RAISED IS ASKED FOR")
        self.raise_note.configure(text="Raised at your next Build & End Turn, in a free recruiting province."
                                  if can > 0 else "Raised once a free recruiting province, a Warlock Engineer and a "
                                  "Warpseer are there.")
        self.place()

    def show_finance(self, f: dict) -> None:
        """Income and the upkeep numbers for the next army; the decision is the player's."""
        fin = f.get("fin")
        self.fin = fin
        self.stat["Income per turn"].configure(text=T.money(fin.income, sign=True) if fin else "—",
                                               fg=(T.GOOD if fin and fin.income >= 0 else T.WARN))
        ws = f.get("warpstone")
        self.stat["Warpstone"].configure(text=T.money(ws) if ws is not None else "—")
        req = self.builder.get("status", {}).get("requested", 0)
        sig = (fin.income, fin.ticked_extra, fin.next_army, fin.next_own, fin.next_supply, fin.after_next,
               req) if fin else None
        if self._changed("money", sig):
            self._clear(self.money_box)
            if fin is not None:
                rows = [("Upkeep the ticked refills add", T.money(-fin.ticked_extra, sign=True) + " / turn"),
                        (f"Upkeep one new army adds ({fin.next_own:,} its own, {fin.next_supply:,} Supply Lines)",
                         T.money(-fin.next_army, sign=True) + " / turn"),
                        ("Income after the refills and one new army", T.money(fin.after_next, sign=True) + " / turn")]
                if req > 1:
                    rows.append((f"Income after the {req} armies asked for",
                                 T.money(fin.income - fin.ticked_extra - fin.next_army * req, sign=True) + " / turn"))
                for k, v in rows:
                    r = tk.Frame(self.money_box, bg=T.BASE)
                    r.pack(fill="x")
                    tk.Label(r, text=v, bg=T.BASE, fg=T.INK, font=self.f_mono).pack(side="right", anchor="n", pady=4)
                    tk.Label(r, text=k, bg=T.BASE, fg=T.INK, font=self.f_body_s, anchor="w", justify="left",
                             wraplength=COL2 - 230).pack(side="left", fill="x", pady=4)
        self._render_armies()
        self.place()

    def _raise(self) -> None:
        if self.on_raise_army is not None and self.can_raise:
            self.on_raise_army()

    # ---------------------------------------------------------------- ARMIES
    def _set_tick(self, a, on: bool) -> None:
        from .army import set_enabled
        set_enabled(a.cqi, a.general_name, on, a.general_id, a.turn, a.rank)
        self._sigs.pop("armies", None)
        self._render_armies()

    def _render_armies(self) -> None:
        from .army import load_automation
        from .widget_data import army_cards, unit_label
        err = ""
        try:
            cards = army_cards(self.rows, self.fin)
        except Exception as ex:                       # noqa: BLE001  (shown, never fatal)
            cards, err = [], str(ex)
        try:
            t = load_automation()["army_builder"]["template"]
            self.playbook.configure(text="Playbook: " + ", ".join(f"{n} {unit_label(k)}" for k, n in t["units"].items())
                                    + "".join(f", {n} Warlock Engineer" for _h, n in t["heroes"].items()))
        except Exception:
            pass
        sig = (err,) + tuple((c["cqi"], c["name"], c["size"], c["where"], tuple((u["unit"], u["count"], u["state"])
                             for u in c["units"]), c["status"], c["upkeep"], c["ticked"], c["can"], c["why_not"])
                             for c in cards)
        if not self._changed("armies", sig):
            return
        self._clear(self.armies)
        if err:
            self._text(self.armies, "Could not read the armies: " + err, T.RED)
            return
        if not cards:
            self._text(self.armies, "No field armies.", T.MUTED)
            return
        cols = 2 if self.win.winfo_screenwidth() - COL1 - COL2 >= 800 else 1
        for i in range(cols):
            self.armies.columnconfigure(i, weight=1, uniform="army")
        tone = {"good": T.GOOD, "muted": T.MUTED, "ink": T.INK}
        for n, c in enumerate(cards):
            card = tk.Frame(self.armies, bg=T.PANEL, highlightthickness=1,
                            highlightbackground=T.BRASS if c["ticked"] else T.LINE, padx=18, pady=14)
            card.grid(row=n // cols, column=n % cols, sticky="new", padx=(0, 16), pady=(0, 16))
            h = tk.Frame(card, bg=T.PANEL)
            h.pack(fill="x")
            tk.Label(h, text=c["name"], bg=T.PANEL, fg=T.TITLE, font=self.f_name).pack(side="left")
            tk.Label(h, text=c["size"], bg=T.PANEL, fg=T.TEXT2, font=self.f_mono).pack(side="right")
            tk.Label(card, text=c["where"], bg=T.PANEL, fg=T.MUTED, font=self.f_body_s, anchor="w").pack(fill="x")
            ub = tk.Frame(card, bg=T.PANEL)
            ub.pack(fill="x", pady=(8, 4))
            for u in c["units"]:
                fg = {"ok": T.GOOD, "short": T.WARN, "extra": T.MUTED}[u["state"]]
                r = tk.Frame(ub, bg=T.PANEL)
                r.pack(fill="x")
                tk.Label(r, text=u["unit"], bg=T.PANEL, fg=fg, font=self.f_body).pack(side="left", pady=2)
                tk.Label(r, text=u["count"], bg=T.PANEL, fg=fg, font=self.f_mono).pack(side="right")
            tk.Label(card, text=c["status"], bg=T.PANEL, fg=tone.get(c["tone"], T.INK), font=self.f_body, anchor="w",
                     justify="left", wraplength=360).pack(fill="x", pady=(4, 8))
            tk.Frame(card, bg="#2a2219", height=1).pack(fill="x")
            foot = tk.Frame(card, bg=T.PANEL)
            foot.pack(fill="x", pady=(10, 0))
            tk.Label(foot, text="Upkeep " + c["upkeep"], bg=T.PANEL, fg=T.TEXT2, font=self.f_body_s).pack(side="left")
            a = c["army"]
            if c["ticked"]:
                b = self._button(foot, "REFILLING - CLICK TO STOP", lambda a=a: self._set_tick(a, False), primary=True)
            elif c["matches"]:
                b = tk.Label(foot, text="NOTHING TO REFILL", bg=T.PANEL, fg=T.DIM, font=self.f_btn, padx=12, pady=8,
                             highlightthickness=1, highlightbackground="#2a2219")
            elif c["can"]:
                b = self._button(foot, "REFILL TO PLAYBOOK", lambda a=a: self._set_tick(a, True))
            else:
                b = tk.Label(foot, text="CAN'T REFILL YET", bg=T.PANEL, fg=T.DIM, font=self.f_btn, padx=12, pady=8,
                             highlightthickness=1, highlightbackground="#2a2219")
            b.pack(side="right")
            if not c["can"] and not c["ticked"] and not c["matches"] and c["why_not"]:
                tk.Label(card, text=c["why_not"], bg=T.PANEL, fg=T.MUTED, font=self.f_body_s, anchor="w",
                         justify="left", wraplength=360).pack(fill="x", pady=(6, 0))

    # ---------------------------------------------------------------- SETTINGS (player rule 2026-10-21)
    def _render_settings(self) -> None:
        """Every setting (assist/settings.py) and which steps run when, changed with a click between turns: a switch
        or a choice is clicked, a number has - and +. Two columns in the drawer."""
        from . import settings as S
        self._clear(self.settings_box)
        subs = [tk.Frame(self.settings_box, bg=T.PANEL) for _ in range(2)]
        for i, f in enumerate(subs):
            self.settings_box.columnconfigure(i, weight=1, uniform="set")
            f.grid(row=0, column=i, sticky="new", padx=(0 if i == 0 else 24, 0))

        def group(parent, text):
            tk.Label(parent, text=text.upper(), bg=T.PANEL, fg=T.MUTED, font=self.f_small,
                     anchor="w").pack(fill="x", pady=(12, 4))

        def row(parent, label, value, on_click, on_minus=None, off=False):
            r = tk.Frame(parent, bg=T.PANEL)
            r.pack(fill="x", pady=(1, 0))
            tk.Label(r, text=label, bg=T.PANEL, fg=T.INK, font=self.f_body_s, anchor="w", justify="left",
                     wraplength=230).pack(side="left", pady=3)
            if on_minus is not None:
                plus = tk.Label(r, text=" + ", bg=T.PANEL2, fg=T.INK, font=self.f_bold, cursor="hand2")
                plus.pack(side="right")
                plus.bind("<Button-1>", lambda e: on_click())
            v = tk.Label(r, text=value, bg=T.PANEL, fg=T.DIM if off else T.BRASS_HI, font=self.f_mono,
                         cursor="hand2", padx=6, width=13)
            v.pack(side="right")
            if on_minus is None:
                v.bind("<Button-1>", lambda e: on_click())
            else:
                minus = tk.Label(r, text=" − ", bg=T.PANEL2, fg=T.INK, font=self.f_bold, cursor="hand2")
                minus.pack(side="right")
                minus.bind("<Button-1>", lambda e: on_minus())
            tk.Frame(parent, bg="#2a2219", height=1).pack(fill="x")

        def change(s, d):
            try:
                S.nudge(s, d)
            except Exception as ex:                    # noqa: BLE001  (shown, never a crash of the widget)
                self.settings_head.configure(text=f"SETTINGS  ·  could not save: {ex}")
                return
            self._render_settings()

        def flip(phase, name):
            S.set_step(phase, name, not S.step_on(phase, name))
            self._render_settings()

        groups: dict[str, list] = {}
        for s in S.SETTINGS:
            groups.setdefault(s.group, []).append(s)
        steps = S.step_order()
        blocks = [(g, len(items) + 1) for g, items in groups.items()] + [(None, len(steps) + 1)]
        half, done, col = sum(n for _g, n in blocks) / 2, 0, 0
        for g, n in blocks:
            if col == 0 and done and done + n / 2 > half:
                col = 1
            done += n
            parent = subs[col]
            if g is not None:
                group(parent, g)
                for s in groups[g]:
                    number = s.kind in ("int", "float")
                    shown = S.shown(s)
                    row(parent, s.label, shown, lambda s=s: change(s, +1),
                        (lambda s=s: change(s, -1)) if number else None, off=shown == "off")
                continue
            group(parent, "Which steps run when")
            hdr = tk.Frame(parent, bg=T.PANEL)
            hdr.pack(fill="x")
            for _phase, what in reversed(S.PHASES):
                tk.Label(hdr, text=what, bg=T.PANEL, fg=T.MUTED, font=self.f_body_s, width=16).pack(side="right")
            for name in steps:
                r = tk.Frame(parent, bg=T.PANEL)
                r.pack(fill="x", pady=(1, 0))
                tk.Label(r, text=name.capitalize(), bg=T.PANEL, fg=T.INK, font=self.f_body_s,
                         anchor="w").pack(side="left", pady=3)
                for phase, _what in reversed(S.PHASES):
                    on = S.step_on(phase, name)
                    b = tk.Label(r, text="on" if on else "off", bg=T.PANEL, fg=T.BRASS_HI if on else T.DIM,
                                 font=self.f_mono, cursor="hand2", width=16)
                    b.pack(side="right")
                    b.bind("<Button-1>", lambda e, ph=phase, n=name: flip(ph, n))
                tk.Frame(parent, bg="#2a2219", height=1).pack(fill="x")
