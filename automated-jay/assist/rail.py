"""The overlay over the game: the "Turn rail" (player's pick, 2026-10-17, design option D of
https://claude.ai/artifact/1FrWVzY4nT9yF1JEe94vF4).

Two sizes (player feedback 2026-10-17: the full rail across the top centre was in the way):
  compact  (default) a small bar: the state, a row of step dots, the button that fits the moment
  full     the whole rail, one labelled node per step (turn start | end of turn); shown only while a pass runs, so
           the End Turn button never moves under the player's cursor
It can be dragged anywhere; the spot is remembered (runs/rail.json). A click (no drag) toggles pause, or presses the
button under it. Drawn on a Tk canvas; the window's corners are cut out with a transparent colour key. While a pass
runs it lets clicks through and never takes focus (assist/app.py sets the window styles).

Node states: done (green tick), active (amber ring), pending (grey ring), later (dashed: runs at Build & End Turn),
failed (red cross).
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
KEY = "#010203"                 # transparent colour key (the cut-out corners)
RADIUS = 10
NODES = [("events", "Events"), ("rites", "Rites"), ("workshop", "Shop"), ("tech", "Tech"), ("skills", "Skills"),
         ("masterplans", "Plans"), None,
         ("buildings", "Build"), ("army", "Army"), ("end", "End")]

BG = "#10120f"
INK = "#c9d0c4"
MUTED = "#8e978a"
LINE = "#3b4238"
RING = "#4e564b"
GREEN, GREEN_DARK = "#5fc94a", "#0e1a0b"
AMBER, AMBER_DIM = "#ffce54", "#5c4c22"
RED = "#ff685c"
STATE = {            # state -> (border, title colour)
    "waiting": ("#2b2f29", "#c9d0c4"),
    "automating": ("#6b5a2a", AMBER),
    "your turn": ("#3d6b33", "#8fe678"),
    "paused": ("#7a5326", "#ffb877"),
    "error": ("#7a3029", "#ff8b80"),
}


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
        self.template: tuple[bool, str] | None = None
        self.steps: dict[str, str] = {}
        self.hover = False
        self._press = None
        self._btn_box = None
        self.btn = None
        self.cv.bind("<ButtonPress-1>", self._on_press)
        self.cv.bind("<B1-Motion>", self._on_drag)
        self.cv.bind("<ButtonRelease-1>", self._on_release)
        self.draw()

    # ---------------------------------------------------------------- model
    def set_status(self, state: str, headline: str, detail: str = "") -> None:
        self.state, self.headline = state, headline
        self.sub = next((ln for ln in (detail or "").splitlines() if ln.strip()), "")[:60]
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

    def _node(self, cx, cy, status, r=11):
        cv = self.cv
        if status == "done":
            cv.create_oval(cx - r, cy - r, cx + r, cy + r, fill=GREEN, outline=GREEN)
            if r >= 8:
                cv.create_line(cx - r * .45, cy, cx - r * .1, cy + r * .36, cx + r * .55, cy - r * .36,
                               fill=GREEN_DARK, width=2.6, capstyle="round", joinstyle="round")
        elif status == "active":
            cv.create_oval(cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4, outline=AMBER_DIM, width=3)
            cv.create_oval(cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1, outline=AMBER, width=3 if r >= 8 else 2)
        elif status == "failed":
            cv.create_oval(cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1, outline=RED, width=2)
            k = r * .36
            cv.create_line(cx - k, cy - k, cx + k, cy + k, fill=RED, width=2)
            cv.create_line(cx + k, cy - k, cx - k, cy + k, fill=RED, width=2)
        elif status == "later":
            cv.create_oval(cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1, outline="#5d6659", width=2, dash=(3, 3))
        else:
            cv.create_oval(cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1, outline=RING, width=2)

    def _rail(self, x0, x1, cy, r, labels: bool):
        slots = len(NODES)
        xs = [x0 + (x1 - x0) * i / (slots - 1) for i in range(slots)]
        prev = None
        for node, x in zip(NODES, xs):
            if node is None:
                self.cv.create_line(x, cy - r - 6, x, cy + r + (22 if labels else 6), fill="#2f342d", width=1)
                prev = None
                continue
            key, label = node
            st = self.steps.get(key, "pending")
            if prev is not None:
                px, pst = prev
                col = GREEN if (pst == "done" and st in ("done", "active")) else LINE
                self.cv.create_line(px + r + 3, cy, x - r - 3, cy, fill=col, width=2)
            self._node(x, cy, st, r)
            if labels:
                col = {"done": INK, "active": AMBER, "failed": RED}.get(st, "#6f786b")
                self.cv.create_text(x, cy + r + 13, text=label.upper(), fill=col, font=self.f_node)
            prev = (x, st)

    def _button(self, box, small: bool):
        cv = self.cv
        bx0, by0, bx1, by1 = box
        self.btn, self._btn_box = None, None
        f = self.f_btn_s if small else self.f_btn
        if self.state == "automating":
            cv.create_text((bx0 + bx1) / 2, by0 + (by1 - by0) * .35, text="MOUSE HELD", fill=AMBER, font=self.f_node)
            cv.create_text((bx0 + bx1) / 2, by0 + (by1 - by0) * .72, text="Shift+Esc stops", fill=MUTED,
                           font=self.f_sub_s)
        elif self.state == "error" and self.on_run_now is not None:
            self.btn = "run"
            self._round_rect(bx0, by0, bx1, by1, 8, fill=BG, outline="#6b6f69", width=1.5)
            cv.create_text((bx0 + bx1) / 2, (by0 + by1) / 2, text="RUN NOW", fill="#eef1ea", font=f)
        elif self.on_end_turn is not None:
            self.btn = "end"
            self._round_rect(bx0, by0, bx1, by1, 8, fill="#7fdc66", outline="#7fdc66")
            cv.create_text((bx0 + bx1) / 2, (by0 + by1) / 2, text="BUILD & END TURN" if not small else "END TURN",
                           fill="#0d1d09", font=f)
        if self.btn:
            self._btn_box = box

    def _draw_icons(self, W: int) -> None:
        """Expand (the fold-out panel), restart (a fresh copy with the latest code), exit: right on the bar."""
        cv = self.cv
        self._icons = []
        col, cy = "#aeb7a8", 27
        specs = [("panel", self.on_toggle_panel), ("restart", self.on_restart), ("exit", self.on_exit)]
        x = 426
        for kind, fn in specs:
            box = (x - 11, cy - 11, x + 11, cy + 11)
            cv.create_rectangle(*box, outline="#2b2f29", fill="#171a15")
            if kind == "panel":
                d = -1 if self.panel_open else 1                       # chevron down (open) / up (close)
                cv.create_line(x - 5, cy - 2 * d, x, cy + 3 * d, x + 5, cy - 2 * d, fill=col, width=2,
                               capstyle="round", joinstyle="round")
            elif kind == "restart":
                cv.create_arc(x - 6, cy - 6, x + 6, cy + 6, start=60, extent=280, style="arc", outline=col, width=2)
                cv.create_line(x + 3, cy - 8, x + 6, cy - 4, x + 1, cy - 3, fill=col, width=2, capstyle="round")
            else:
                cv.create_line(x - 5, cy - 5, x + 5, cy + 5, fill="#d99a92", width=2, capstyle="round")
                cv.create_line(x + 5, cy - 5, x - 5, cy + 5, fill="#d99a92", width=2, capstyle="round")
            if fn is not None:
                self._icons.append((box, fn))
            x += 24

    def draw(self) -> None:
        cv = self.cv
        cv.delete("all")
        self._icons = []
        border, title_fg = STATE.get(self.state, STATE["waiting"])
        if self.full:
            W, H = FULL
            self._place(W, H)
            self._round_rect(1, 1, W - 1, H - 1, RADIUS, fill=BG, outline=border, width=1.5)
            cv.create_text(18, 26, text=self.headline.upper(), anchor="w", fill=title_fg, font=self.f_title)
            cv.create_text(18, 50, text=self.sub, anchor="w", fill=MUTED, font=self.f_sub, width=190)
            self._rail(232, 812, 30, 11, labels=True)
            self._button((836, 14, W - 12, H - 14), small=False)
        else:
            W, H = COMPACT
            self._place(W, H)
            self._round_rect(1, 1, W - 1, H - 1, RADIUS, fill=BG, outline=border, width=1.5)
            cv.create_text(14, 18, text=self.headline.upper(), anchor="w", fill=title_fg, font=self.f_title_s)
            cv.create_text(14, 38, text=self.sub, anchor="w", fill=MUTED, font=self.f_sub_s, width=150)
            self._rail(180, 300, 27, 5, labels=False)
            self._button((314, 11, 408, 43), small=True)
            self._draw_icons(W)
            # bottom strip, always visible: can any province recruit the whole army template?
            cv.create_line(12, 53, W - 12, 53, fill="#23271f")
            if self.template is not None:
                ok, text = self.template
                cv.create_text(14, 61, anchor="w", font=self.f_sub_s, width=W - 28,
                               text=("TEMPLATE ✓ " if ok else "TEMPLATE: ") + text,
                               fill="#8fe678" if ok else "#ffb877")
            else:
                cv.create_text(14, 61, anchor="w", font=self.f_sub_s, text="TEMPLATE: checking...", fill=MUTED)

    # ---------------------------------------------------------------- input
    def _set_hover(self, on: bool) -> None:
        if self._press is not None:                    # dragging: keep the size steady
            return
        if on != self.hover:
            self.hover = on
            self.draw()

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
                fn()
            return
        self.on_pause()
