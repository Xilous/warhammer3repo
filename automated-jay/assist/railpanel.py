"""The rail's fold-out panel: everything the main window offers, without leaving the game (player request 2026-10-17:
"make the app's interface be entirely on the widget ... so i can control it without having to alt tab").

Opened and closed with the rail's expand button; sits under the rail and follows it when it is dragged. Like the
rail it never takes focus (the game stays in front while armies are ticked or buttons pressed), and it hides itself
while a pass runs, so it can never be under a click the assistant makes.

Contents: Run now / Pause / Restart, turn and treasury, this turn's step results, the armies with their army-builder
tick boxes (saved exactly as the main window does: assist/army.py set_enabled), "Ignore <id>" for popups that block
a pass, the frontline provinces, and a link to the full window.
"""
from __future__ import annotations
import tkinter as tk

BG, BG2 = "#10120f", "#171a15"
INK, MUTED, DIM = "#dfe5da", "#8e978a", "#6f786b"
GREEN, AMBER, RED, ORANGE = "#8fe678", "#ffce54", "#ff8b80", "#ffb877"
BORDER = "#2b2f29"
WIDTH = 494                     # the compact rail's width: the panel lines up under it
FONT = ("Segoe UI", 9)
FONT_B = ("Segoe UI Semibold", 9)
FONT_H = ("Bahnschrift SemiBold Condensed", 11, "bold")


def _nice(text: str) -> str:
    from .app import nice
    return nice(text)


class RailPanel:
    def __init__(self, root: tk.Tk, rail, on_run_now, on_pause, on_restart, on_ignore, on_full_window,
                 on_exit=None) -> None:
        self.rail = rail
        self.on_run_now, self.on_pause, self.on_restart = on_run_now, on_pause, on_restart
        self.on_ignore, self.on_full_window = on_ignore, on_full_window
        self.open = False
        self.suppressed = False                     # hidden while a pass runs
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.96)
        self.win.configure(bg=BORDER)
        self.win.withdraw()
        self.body = tk.Frame(self.win, bg=BG, padx=12, pady=10)
        self.body.pack(fill="both", expand=True, padx=1, pady=1)

        bar = tk.Frame(self.body, bg=BG)
        bar.pack(fill="x")
        self.pause_btn = self._button(bar, "PAUSE", self._pause)
        self._button(bar, "RUN NOW", self.on_run_now).pack(side="left", padx=(0, 6))
        self.pause_btn.pack(side="left", padx=(0, 6))
        self._button(bar, "RESTART", self.on_restart).pack(side="left", padx=(0, 6))
        if on_exit is not None:
            ex = self._button(bar, "EXIT", on_exit)
            ex.configure(fg="#d99a92")
            ex.pack(side="left", padx=(0, 6))
        full = tk.Label(bar, text="full window", bg=BG, fg=MUTED, font=FONT, cursor="hand2")
        full.pack(side="right")
        full.bind("<Button-1>", lambda e: self.on_full_window())

        self.info = tk.Label(self.body, text="", bg=BG, fg=MUTED, font=FONT, anchor="w")
        self.info.pack(fill="x", pady=(8, 0))
        # at a glance: can any province recruit the whole army template? (assist/app.py template_status)
        self.template = tk.Label(self.body, text="", bg=BG2, fg=MUTED, font=FONT, anchor="w", justify="left",
                                 wraplength=WIDTH - 40, padx=8, pady=5)
        self.template.pack(fill="x", pady=(6, 0))
        self.ignore_row = tk.Frame(self.body, bg=BG)
        self.ignore_row.pack(fill="x")

        self._heading("THIS TURN")
        self.log = tk.Label(self.body, text="", bg=BG2, fg=INK, font=("Consolas", 8), anchor="nw", justify="left",
                            wraplength=WIDTH - 40, padx=8, pady=6)
        self.log.pack(fill="x")

        self._heading("ARMIES  (tick: build to the template)")
        self.armies = tk.Frame(self.body, bg=BG)
        self.armies.pack(fill="x")
        self.army_vars: dict[int, tk.BooleanVar] = {}

        self._heading("FRONTLINE  (you build there)")
        self.front = tk.Label(self.body, text="", bg=BG, fg=ORANGE, font=FONT, anchor="w", justify="left",
                              wraplength=WIDTH - 30)
        self.front.pack(fill="x")

    # ---------------------------------------------------------------- pieces
    def _button(self, parent, text, cmd):
        b = tk.Label(parent, text=text, bg="#23271f", fg=INK, font=FONT_B, padx=10, pady=4, cursor="hand2")
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg="#2e3329"))
        b.bind("<Leave>", lambda e: b.configure(bg="#23271f"))
        return b

    def _heading(self, text: str) -> None:
        tk.Label(self.body, text=text, bg=BG, fg=DIM, font=FONT_H, anchor="w").pack(fill="x", pady=(10, 3))

    def _pause(self) -> None:
        self.on_pause()

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
        x, y = self.rail.win.winfo_x(), self.rail.win.winfo_y() + self.rail.win.winfo_height() + 6
        h = self.body.winfo_reqheight() + 2
        sh = self.win.winfo_screenheight()
        if y + h > sh:                               # no room below: open above the rail
            y = max(0, self.rail.win.winfo_y() - h - 6)
        self.win.geometry(f"{WIDTH}x{h}+{x}+{y}")
        self.win.deiconify()
        self.win.lift()
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
        self.pause_btn.configure(text="RESUME" if paused else "PAUSE", fg=ORANGE if paused else INK)

    def show_log(self, lines: list[str]) -> None:
        self.log.configure(text="\n".join(_nice(x) for x in lines[-12:]) or "nothing yet")
        self.place()

    def show_template(self, status) -> None:
        if not status:
            return
        ok, text = status
        self.template.configure(text=("✓ " if ok else "") + text, fg=GREEN if ok else ORANGE)
        self.place()

    def show_ignorable(self, ids: list[str]) -> None:
        for c in self.ignore_row.winfo_children():
            c.destroy()
        for cid in ids:
            b = self._button(self.ignore_row, f"IGNORE {cid}", lambda c=cid: self.on_ignore(c))
            b.configure(fg=ORANGE)
            b.pack(side="left", pady=(6, 0), padx=(0, 6))
        self.place()

    def show_world(self, st, rows, blocked, heroes=()) -> None:
        from .army import enabled_armies, set_enabled, tick_for
        if st is not None:
            self.info.configure(text=f"Turn {st.turn}   ·   Treasury {st.treasury}" if st.turn is not None
                                else "no campaign loaded")
        for c in self.armies.winfo_children():
            c.destroy()
        enabled = enabled_armies()
        if not rows:
            tk.Label(self.armies, text="no field armies", bg=BG, fg=MUTED, font=FONT).pack(anchor="w")
        for a, d in rows:
            var = self.army_vars.setdefault(a.cqi, tk.BooleanVar())
            on, why = tick_for(a, enabled)
            var.set(on)
            row = tk.Frame(self.armies, bg=BG)
            row.pack(fill="x", pady=(2, 0))
            tk.Checkbutton(row, variable=var, bg=BG, activebackground=BG, selectcolor=BG2, fg=INK,
                           highlightthickness=0, bd=0, cursor="hand2",
                           command=lambda a=a, var=var: set_enabled(a.cqi, a.general_name, var.get(), a.general_id)
                           ).pack(side="left")
            size = f"{len(a.units)}" + (f"+{len(a.queued)}" if a.queued else "")
            tk.Label(row, text=f"{a.general_name}", bg=BG, fg=INK, font=FONT_B).pack(side="left")
            tk.Label(row, text=f"  {size} units · {_nice(a.region or '')}", bg=BG, fg=MUTED, font=FONT).pack(side="left")
            note = why or d.summary()
            tk.Label(self.armies, text=note, bg=BG, fg=(RED if why else GREEN if d.matches else MUTED), font=FONT,
                     anchor="w", justify="left", wraplength=WIDTH - 60, padx=26).pack(fill="x")
        if "error" in blocked:
            self.front.configure(text="could not read the campaign: " + blocked["error"], fg=RED)
        else:
            self.front.configure(text="\n".join(f"{_nice(p)}" for p in blocked) or "none", fg=ORANGE)
        self.place()
