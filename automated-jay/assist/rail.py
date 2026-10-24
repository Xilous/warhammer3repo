"""The overlay over the game: the "Turn rail" (player's pick, 2026-10-17, design option D of
https://claude.ai/artifact/1FrWVzY4nT9yF1JEe94vF4).

Two sizes (player feedback 2026-10-17: the full rail across the top centre was in the way):
  compact  (default) a small bar: the state, a row of step dots, the button that fits the moment
  full     the whole rail, one labelled node per step (turn start | end of turn); shown only while a pass runs, so
           the End Turn button never moves under the player's cursor
It can be dragged anywhere; the spot is remembered (runs/rail.json). A click (no drag) toggles pause, or presses the
button under it. Drawn on a Tk canvas; the window's corners are cut out with a transparent colour key. While a pass
runs it lets clicks through and never takes focus (assist/app.py sets the window styles).

Steps are bars (Clan Brass, 2026-10-18, assist/theme.py): done brass, active amber, pending dim, later (dashed: runs at Build & End Turn),
failed red.
"""
from __future__ import annotations
import json
import tkinter as tk
import tkinter.font as tkfont

from bot import config

FULL = (1000, 76)
COMPACT = (560, 84)                 # one title, one or two lines of plain words, one button, the open arrow
HOME = (10, 72)                 # default top-left corner (where the first overlay sat)
POS_FILE = config.RUNS_DIR / "rail.json"
DRAG_PX = 4                     # a press that moves further than this is a drag, not a click
_MEASURE: dict = {}              # font description -> tkfont.Font, for _fit
GRIP_W = 12                     # the drag handle on the left edge (move cursor)
KEY = "#010203"                 # transparent colour key (the cut-out corners)
NODES = [("events", "Events"), ("rites", "Rites"), ("workshop", "Shop"), ("tech", "Tech"), ("skills", "Skills"),
         ("masterplans", "Plans"), None,
         ("buildings", "Build"), ("army", "Army"), ("end", "End")]

from . import theme as T

BG = T.PANEL
INK = T.INK
MUTED = T.MUTED
LINE = T.LINE
RING = T.LINE
GREEN, GREEN_DARK = T.BRASS, T.ON_BRASS
AMBER, AMBER_DIM = T.AMBER, "#5c4c22"
RED = T.RED
STATE = {s: (c, T.TITLE) for s, c in T.STATE.items()}      # state -> (stripe, title colour)
RADIUS = 4


def _font(families, size, weight="normal"):
    have = set(tkfont.families())
    fam = next((f for f in families if f in have), "Segoe UI")
    return (fam, size, weight)


class TurnRail:
    def __init__(self, root: tk.Tk, on_pause, on_end_turn=None, on_run_now=None, on_restart=None, on_exit=None) -> None:
        self.on_pause, self.on_end_turn, self.on_run_now = on_pause, on_end_turn, on_run_now
        self.on_restart, self.on_exit = on_restart, on_exit
        self.on_toggle_panel = None                   # set by the app (assist/railpanel.py)
        self.on_moved = None
        self.panel_open = False
        self._icons: list[tuple[tuple, object]] = []   # (box, callback) of the small buttons on the compact bar
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.94)
        self.win.configure(bg=KEY)
        try:
            self.win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        self.pos = self._load_pos()
        self.cv = tk.Canvas(self.win, width=COMPACT[0], height=COMPACT[1], bg=KEY, highlightthickness=0, bd=0)
        self.cv.pack()
        self.f_title = _font(["Bahnschrift SemiBold Condensed", "Bahnschrift", "Segoe UI Semibold"], 15, "bold")
        self.f_title_s = _font(["Bahnschrift SemiBold Condensed", "Bahnschrift", "Segoe UI Semibold"], 12, "bold")
        self.f_sub = _font(["Segoe UI"], 9)
        self.f_sub_s = _font(["Segoe UI"], 8)
        self.f_node = _font(["Bahnschrift SemiCondensed", "Bahnschrift", "Segoe UI"], 9)
        self.f_btn = _font(["Bahnschrift SemiBold Condensed", "Bahnschrift", "Segoe UI Semibold"], 12, "bold")
        self.f_btn_s = _font(["Bahnschrift SemiBold Condensed", "Bahnschrift", "Segoe UI Semibold"], 10, "bold")
        self.state, self.headline, self.sub = "waiting", "WAITING", ""
        self.end_wait = False                        # Build & End Turn taken, waiting for the game (spinner)
        self.view: dict = {}                         # the runner's state (set_view)
        self.press_seq = 0                           # Build & End Turn presses so far
        self.pending_press = 0                       # the press the runner has not handled yet (0: none)
        self._spin, self._spinning = 0, False
        self.template: tuple[bool, str] | None = None
        self.signal: str | None = None               # an army decision is open (assist/app.py army_signal)
        self.line: str = ""                          # the one line under the title (assist/widget_data.bar_line)
        self.steps: dict[str, str] = {}
        self.hover = False
        self._press = None
        self._btn_box = None
        self.btn = None
        self.cv.bind("<ButtonPress-1>", self._on_press)
        self.cv.bind("<B1-Motion>", self._on_drag)
        self.cv.bind("<ButtonRelease-1>", self._on_release)
        self.cv.bind("<Motion>", lambda e: self.cv.configure(cursor="fleur" if e.x < GRIP_W else ""))
        self.draw()

    # ---------------------------------------------------------------- model
    def set_status(self, state: str, headline: str, detail: str = "") -> None:
        self.state, self.headline = state, headline
        self.sub = next((ln for ln in (detail or "").splitlines() if ln.strip()), "")
        self.draw()

    def set_view(self, view: dict) -> None:
        """The runner's own state (Runner.publish): the QUEUED spinner is drawn from it, never guessed from the wording
        of a status (2026-10-20: the button and the runner went out of step several times: QUEUED kept after the
        request was gone, or dropped while it stood)."""
        self.view = view
        if view.get("ack", 0) >= self.pending_press:
            self.pending_press = 0                   # the runner has handled the press
        self._derive()
        self.draw()

    def _derive(self) -> None:
        # player request 2026-10-19: the End Turn button shows that the press was taken and the assistant is waiting
        # for the game; from the press until the runner has handled it, then for as long as the runner owes it
        v = self.view
        self.end_wait = bool(self.pending_press or v.get("owed") or v.get("run_owed"))

    def set_line(self, text: str) -> None:
        if text != self.line:
            self.line = text or ""
            self.draw()

    def set_signal(self, text: str | None) -> None:
        if text != self.signal:
            self.signal = text
            self.draw()

    def set_template(self, ok: bool, text: str) -> None:
        if (ok, text) != self.template:
            self.template = (ok, text)
            self.draw()

    def set_steps(self, steps: dict[str, str]) -> None:
        self.steps = dict(steps)
        self.draw()

    @property
    def full(self) -> bool:
        # never since 2026-10-24 (the redesign: the bar keeps its size, a progress line shows the pass instead of the
        # wide rail of step bars, player: "visualizations arent really that helpful")
        return False

    # ---------------------------------------------------------------- position
    def _load_pos(self) -> tuple[int, int]:
        try:
            d = json.loads(POS_FILE.read_text(encoding="utf-8"))
            return int(d["x"]), int(d["y"])
        except Exception:
            return HOME

    def _save_pos(self) -> None:
        try:
            POS_FILE.parent.mkdir(parents=True, exist_ok=True)
            POS_FILE.write_text(json.dumps({"x": self.pos[0], "y": self.pos[1]}), encoding="utf-8")
        except Exception:
            pass

    def _place(self, w: int, h: int) -> None:
        sw, shh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        x = max(0, min(self.pos[0], sw - w))          # the full rail grows to the right; keep it on screen
        y = max(0, min(self.pos[1], shh - h))
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.cv.configure(width=w, height=h)

    # ---------------------------------------------------------------- drawing
    def _round_rect(self, x0, y0, x1, y1, r, **kw):
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1,
               x0, y1 - r, x0, y0 + r, x0, y0]
        return self.cv.create_polygon(pts, smooth=True, **kw)

    def _button(self, box, small: bool):
        cv = self.cv
        bx0, by0, bx1, by1 = box
        self.btn, self._btn_box = None, None
        f = self.f_btn_s if small else self.f_btn
        if self.state == "automating":
            cv.create_text((bx0 + bx1) / 2, by0 + (by1 - by0) * .35, text="MOUSE HELD", fill=T.AMBER, font=self.f_node)
            cv.create_text((bx0 + bx1) / 2, by0 + (by1 - by0) * .72, text="Shift+Esc stops", fill=MUTED,
                           font=self.f_sub_s)
        elif self.state == "error" and self.on_run_now is not None:
            self.btn = "run"
            self._round_rect(bx0, by0, bx1, by1, 3, fill=T.PANEL, outline=T.BRASS, width=1.5)
            cv.create_text((bx0 + bx1) / 2, (by0 + by1) / 2, text="RUN NOW", fill=T.BRASS, font=f)
        elif self.on_end_turn is not None and self.end_wait:
            self.btn = "end"                         # (another press while queued changes nothing)
            self._round_rect(bx0, by0, bx1, by1, 3, fill=T.PANEL, outline=T.BRASS, width=1.5)
            r = min(7, (by1 - by0) / 2 - 4)
            cx, cy = bx0 + 6 + r, (by0 + by1) / 2
            cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline=T.LINE, width=2)
            cv.create_arc(cx - r, cy - r, cx + r, cy + r, start=-(self._spin * 30) % 360, extent=100, style="arc",
                          outline=T.BRASS_HI, width=2)
            cv.create_text((bx0 + bx1) / 2 + r, cy, text="QUEUED", fill=T.BRASS, font=f)
            self._spin_later()
        elif self.on_end_turn is not None:
            self.btn = "end"
            self._round_rect(bx0, by0, bx1, by1, 3, fill=T.BRASS, outline=T.BRASS)
            cv.create_text((bx0 + bx1) / 2, (by0 + by1) / 2, text="BUILD & END TURN" if not small else "END TURN",
                           fill=T.ON_BRASS, font=f)
        if self.btn:
            self._btn_box = box

    def _spin_later(self) -> None:
        if not self._spinning:
            self._spinning = True
            self.cv.after(90, self._spin_step)

    def _spin_step(self) -> None:
        self._spinning = False
        if self.end_wait:
            self._spin += 1
            try:
                self.draw()
            except Exception:                        # (logged; the next status redraws it)
                import traceback
                traceback.print_exc()

    def _draw_icons(self, W: int, H: int) -> None:
        """The open arrow on the right of the bar (the full-screen view has Restart and Exit)."""
        cv = self.cv
        self._icons = []
        x0, y0, x1, y1 = W - 56, H / 2 - 22, W - 12, H / 2 + 22
        cv.create_rectangle(x0, y0, x1, y1, outline=T.LINE, fill=T.PANEL2)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        d = -1 if self.panel_open else 1                       # chevron down (open) / up (close)
        cv.create_line(cx - 6, cy - 3 * d, cx, cy + 3 * d, cx + 6, cy - 3 * d, fill=T.INK, width=2,
                       capstyle="round", joinstyle="round")
        if self.on_toggle_panel is not None:
            self._icons.append(((x0, y0, x1, y1), self.on_toggle_panel))

    def _frame(self, W, H, stripe):
        """Clan Brass: a flat dark plate with a 4 px stripe on top in the state's colour."""
        self._round_rect(1, 1, W - 1, H - 1, RADIUS, fill=T.PANEL, outline=T.BASE, width=1)
        self.cv.create_rectangle(2, 1, W - 2, 5, fill=stripe, outline=stripe)

    def _progress(self) -> tuple[int, int, str]:
        """(steps done, steps in the pass, the step running now) from the step states."""
        keys = [n[0] for n in NODES if n is not None and self.steps.get(n[0]) not in (None, "later")]
        done = sum(1 for k in keys if self.steps.get(k) in ("done", "failed"))
        active = next((lbl for k, lbl in (n for n in NODES if n) if self.steps.get(k) == "active"), "")
        return done, len(keys), active

    def draw(self) -> None:
        """The collapsed bar (redesigned 2026-10-24, player-approved prototype): the state as a title, one line of
        plain words (what needs you, what failed, or what is in progress), at most one button, the open arrow; while a
        pass runs, the step and a progress line instead of a button."""
        cv = self.cv
        cv.delete("all")
        self._icons = []
        stripe, title_fg = STATE.get(self.state, STATE["waiting"])
        W, H = COMPACT
        self._place(W, H)
        self._frame(W, H, stripe)
        self._grip(H)
        title = self.headline.upper()
        line = self.line or self.sub
        if self.state == "automating":
            done, total, active = self._progress()
            title = f"WORKING - {active.upper()}" + (f"  ({done} of {total} steps)" if total else "") if active                 else "WORKING"
            line = "Hands off the mouse until it is done. Shift+Esc stops it."
        text_w = W - 16 - 56 - (192 if self.state != "automating" else 0) - 24
        cv.create_text(18, 24, text=self._fit(title, self.f_title_s, text_w, 1), anchor="w", fill=title_fg,
                       font=self.f_title_s)
        cv.create_text(18, 38, text=self._fit(line, self.f_sub, text_w, 2), anchor="nw",
                       fill=T.AMBER if self.state in ("automating", "paused") else T.RED if self.state == "error"
                       else T.TEXT2, font=self.f_sub)
        if self.state != "automating":
            self._button((W - 56 - 12 - 180, H / 2 - 22, W - 56 - 12, H / 2 + 22), small=False)
        else:
            self.btn, self._btn_box = None, None
            done, total, _a = self._progress()
            cv.create_rectangle(2, H - 5, W - 2, H - 2, fill=T.LINE, outline=T.LINE)
            if total:
                cv.create_rectangle(2, H - 5, 2 + (W - 4) * done / total, H - 2, fill=T.AMBER, outline=T.AMBER)
        self._draw_icons(W, H)

    @staticmethod
    def _fit(text: str, font, width: int, lines: int) -> str:
        """text word-wrapped to `width` pixels in `font`, at most `lines` lines; the last one ends in an ellipsis
        when the text does not fit (the full text stays in the fold-out panel)."""
        if not hasattr(font, "measure"):            # the rail's fonts are (family, size, ...) descriptions
            font = _MEASURE.setdefault(font, tkfont.Font(font=font))
        words, out, cur = (text or "").split(), [], ""
        for i, wd in enumerate(words):
            nxt = f"{cur} {wd}".strip()
            if font.measure(nxt) <= width:
                cur = nxt
                continue
            out.append(cur)
            cur = wd
            if len(out) == lines:
                break
        else:
            out.append(cur)
            return "\n".join(x for x in out if x)
        last = out[-1]
        while last and font.measure(last + "…") > width:
            last = last[:-1]
        out[-1] = last.rstrip() + "…"
        return "\n".join(out[:lines])

    # ---------------------------------------------------------------- input
    def _set_hover(self, on: bool) -> None:
        if self._press is not None:                    # dragging: keep the size steady
            return
        if on != self.hover:
            self.hover = on
            self.draw()

    def _grip(self, H: int) -> None:
        """The drag handle (player report 2026-10-19: nothing showed where to grab the widget): two columns of dots on
        the left edge; the whole bar still drags, the handle only shows it (and gives the move cursor)."""
        for col in (4, 8):
            for y in range(H // 2 - 9, H // 2 + 10, 4):
                self.cv.create_rectangle(col, y, col + 1.5, y + 1.5, fill=T.MUTED, outline="")

    # moving the rail from elsewhere (the fold-out panel's grip): the same drag as on the bar
    def drag_start(self, x_root: int, y_root: int) -> None:
        self._press = (x_root, y_root, self.pos, False)

    def drag_move(self, x_root: int, y_root: int) -> None:
        class E:
            pass
        e = E()
        e.x_root, e.y_root = x_root, y_root
        self._on_drag(e)

    def drag_end(self) -> None:
        press, self._press = self._press, None
        if press is not None and press[3]:
            self.pos = (max(0, self.pos[0]), max(0, self.pos[1]))
            self._save_pos()

    def _on_press(self, e) -> None:
        self._press = (e.x_root, e.y_root, self.pos, False)

    def _on_drag(self, e) -> None:
        if self._press is None:
            return
        x0, y0, (px, py), moved = self._press
        dx, dy = e.x_root - x0, e.y_root - y0
        if moved or abs(dx) > DRAG_PX or abs(dy) > DRAG_PX:
            self.pos = (px + dx, py + dy)
            self._press = (x0, y0, (px, py), True)
            self.win.geometry(f"+{max(0, self.pos[0])}+{max(0, self.pos[1])}")
            if self.on_moved:
                self.on_moved()

    def _on_release(self, e) -> None:
        press, self._press = self._press, None
        if press is None:
            return
        if press[3]:                                   # it was a drag: remember the spot
            self.pos = (max(0, self.pos[0]), max(0, self.pos[1]))
            self._save_pos()
            return
        for (x0, y0, x1, y1), fn in self._icons:
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                fn()
                return
        if self._btn_box and self._btn_box[0] <= e.x <= self._btn_box[2] and self._btn_box[1] <= e.y <= self._btn_box[3]:
            fn = self.on_end_turn if self.btn == "end" else self.on_run_now
            if fn:
                if self.btn == "end":
                    self.press_seq += 1              # at once: the press was taken, until the runner acks it
                    self.pending_press = self.press_seq
                    self._derive()
                    self.draw()
                fn()
            return
        self.on_pause()
