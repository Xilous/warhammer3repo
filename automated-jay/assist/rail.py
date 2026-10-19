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
COMPACT = (494, 70)                 # + a strip at the bottom: can any province build the template?
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
        self._spin, self._spinning = 0, False
        self.template: tuple[bool, str] | None = None
        self.signal: str | None = None               # an army decision is open (assist/app.py army_signal)
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
    WAIT_HEADLINES = ("END TURN QUEUED", "ENDING TURN", "RUN NOW QUEUED")

    def set_status(self, state: str, headline: str, detail: str = "") -> None:
        self.state, self.headline = state, headline
        # player request 2026-10-19: the End Turn button shows that the press was taken and the assistant is
        # waiting for the game (a pending action, End Turn greyed); a pass in progress keeps it too, until the
        # turn has ended or the request ended otherwise
        if (headline.startswith(self.WAIT_HEADLINES) or (self.end_wait and state == "automating")
                or "queued" in (detail or "").lower()[:120]):
            self.end_wait = True
        else:
            self.end_wait = False
        self.sub = next((ln for ln in (detail or "").splitlines() if ln.strip()), "")
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
        # only while automations run (player feedback 2026-10-17: expanding on hover moved the End Turn button
        # away from the cursor); compact whenever the player has control
        return self.state == "automating"

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

    def _segment(self, x0, x1, cy, status, h):
        """One step as a flat bar (Clan Brass): done brass, running amber, failed red, later outlined, pending dim."""
        cv = self.cv
        y0, y1 = cy - h / 2, cy + h / 2
        if status == "done":
            cv.create_rectangle(x0, y0, x1, y1, fill=T.BRASS, outline=T.BRASS)
        elif status == "active":
            cv.create_rectangle(x0, y0, x1, y1, fill=T.AMBER, outline=T.AMBER)
        elif status == "failed":
            cv.create_rectangle(x0, y0, x1, y1, fill=T.RED, outline=T.RED)
        elif status == "later":
            cv.create_rectangle(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 0.5, fill="", outline=T.DIM, dash=(2, 2))
        else:
            cv.create_rectangle(x0, y0, x1, y1, fill=T.LINE, outline=T.LINE)

    def _rail(self, x0, x1, cy, h, labels: bool):
        """The steps as a row of bars, a gap between turn start and end of turn (NODES' None)."""
        steps = [n for n in NODES if n is not None]
        gap = 10 if labels else 6
        space = 3 if not labels else 6
        seg = (x1 - x0 - gap - space * (len(steps) - 1)) / len(steps)
        x = x0
        for node in NODES:
            if node is None:
                x += gap - space
                continue
            key, label = node
            st = self.steps.get(key, "pending")
            self._segment(x, x + seg, cy, st, h)
            if labels:
                col = {"done": T.INK, "active": T.AMBER, "failed": T.RED}.get(st, T.DIM)
                self.cv.create_text(x + seg / 2, cy + h / 2 + 11, text=label.upper(), fill=col, font=self.f_node)
            x += seg + space

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
            self.draw()

    def _draw_icons(self, W: int) -> None:
        """Expand (the fold-out panel), restart (a fresh copy with the latest code), exit: right on the bar."""
        cv = self.cv
        self._icons = []
        col, cy = T.MUTED, 27
        specs = [("panel", self.on_toggle_panel), ("restart", self.on_restart), ("exit", self.on_exit)]
        x = 426
        for kind, fn in specs:
            box = (x - 11, cy - 11, x + 11, cy + 11)
            cv.create_rectangle(*box, outline=T.LINE, fill=T.PANEL2)
            if kind == "panel":
                d = -1 if self.panel_open else 1                       # chevron down (open) / up (close)
                cv.create_line(x - 5, cy - 2 * d, x, cy + 3 * d, x + 5, cy - 2 * d, fill=col, width=2,
                               capstyle="round", joinstyle="round")
            elif kind == "restart":
                cv.create_arc(x - 6, cy - 6, x + 6, cy + 6, start=60, extent=280, style="arc", outline=col, width=2)
                cv.create_line(x + 3, cy - 8, x + 6, cy - 4, x + 1, cy - 3, fill=col, width=2, capstyle="round")
            else:
                cv.create_line(x - 5, cy - 5, x + 5, cy + 5, fill=T.WARN, width=2, capstyle="round")
                cv.create_line(x + 5, cy - 5, x - 5, cy + 5, fill=T.WARN, width=2, capstyle="round")
            if fn is not None:
                self._icons.append((box, fn))
            x += 24

    def _frame(self, W, H, stripe):
        """Clan Brass: a flat dark plate with a 3 px stripe on top in the state's colour."""
        self._round_rect(1, 1, W - 1, H - 1, RADIUS, fill=T.PANEL, outline=T.BASE, width=1)
        self.cv.create_rectangle(2, 1, W - 2, 4, fill=stripe, outline=stripe)

    def draw(self) -> None:
        cv = self.cv
        cv.delete("all")
        self._icons = []
        stripe, title_fg = STATE.get(self.state, STATE["waiting"])
        if self.full:
            W, H = FULL
            self._place(W, H)
            self._frame(W, H, stripe)
            self._grip(H)
            cv.create_text(18, 27, text=self.headline.upper(), anchor="w", fill=title_fg, font=self.f_title)
            cv.create_text(18, 39, text=self._fit(self.sub, self.f_sub, 190, 2), anchor="nw", fill=T.MUTED,
                           font=self.f_sub)
            self._rail(232, 812, 28, 6, labels=True)
            self._button((836, 16, W - 12, H - 14), small=False)
        else:
            W, H = COMPACT
            self._place(W, H)
            self._frame(W, H, stripe)
            self._grip(H)
            cv.create_text(14, 20, text=self.headline.upper(), anchor="w", fill=title_fg, font=self.f_title_s)
            # (player report 2026-10-19: a long reason wrapped to three lines, centred on y 39, ran into the
            # headline and the line below: now from the headline down, two lines at most)
            cv.create_text(14, 28, text=self._fit(self.sub, self.f_sub_s, 152, 2), anchor="nw", fill=T.MUTED,
                           font=self.f_sub_s)
            self._rail(176, 302, 28, 6, labels=False)
            self._button((314, 13, 408, 43), small=True)
            self._draw_icons(W)
            # bottom strip, always visible: can any province recruit the whole army template?
            cv.create_line(12, 53, W - 12, 53, fill=T.LINE)
            if self.signal:                            # an army decision first: it is something to do
                cv.create_text(14, 61, anchor="w", font=self.f_sub_s,
                               text=self._fit("ARMY ▲ " + self.signal, self.f_sub_s, W - 28, 1), fill=T.BRASS_HI)
            elif self.template is not None:
                ok, text = self.template
                cv.create_text(14, 61, anchor="w", font=self.f_sub_s,
                               text=self._fit(("TEMPLATE ✓ " if ok else "TEMPLATE: ") + text, self.f_sub_s, W - 28, 1),
                               fill=T.GOOD if ok else T.WARN)
            else:
                cv.create_text(14, 61, anchor="w", font=self.f_sub_s, text="TEMPLATE: checking...", fill=T.MUTED)

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
                    self.end_wait = True             # at once: the press was taken (the runner's status follows)
                    self.draw()
                fn()
            return
        self.on_pause()
