"""The overlay over the game: the "Turn rail" (player's pick, 2026-10-17, design option D of
https://claude.ai/artifact/1FrWVzY4nT9yF1JEe94vF4).

A slim rounded bar at the top centre of the screen, under the game's top HUD and above the area the assistant clicks
on the map: the state on the left, one node per step in the middle (turn start | end of turn), the button that fits
the moment on the right. Drawn on a Tk canvas; the window's corners are cut out with a transparent colour key.

Node states: done (green tick), active (amber ring), pending (grey ring), later (dashed: runs at Build & End Turn),
failed (red cross). Clicking the bar toggles pause, except on its button; while a pass runs it lets clicks through
and never takes focus (assist/app.py sets the window styles).
"""
from __future__ import annotations
import tkinter as tk
import tkinter.font as tkfont

W, H = 1000, 76
TOP = 64                        # px from the top of the screen: under the game's top bar
KEY = "#010203"                 # transparent colour key (the cut-out corners)
RADIUS = 10
NODES = [("events", "Events"), ("rites", "Rites"), ("tech", "Tech"), ("skills", "Skills"), None,
         ("buildings", "Build"), ("army", "Army"), ("end", "End")]
START = {"events", "rites", "tech", "skills"}

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
    def __init__(self, root: tk.Tk, on_pause, on_end_turn=None, on_run_now=None) -> None:
        self.on_pause, self.on_end_turn, self.on_run_now = on_pause, on_end_turn, on_run_now
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.94)
        self.win.configure(bg=KEY)
        try:
            self.win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        sw = self.win.winfo_screenwidth()
        self.win.geometry(f"{W}x{H}+{(sw - W) // 2}+{TOP}")
        self.cv = tk.Canvas(self.win, width=W, height=H, bg=KEY, highlightthickness=0, bd=0)
        self.cv.pack()
        self.f_title = _font(["Bahnschrift SemiBold Condensed", "Bahnschrift", "Segoe UI Semibold"], 15, "bold")
        self.f_sub = _font(["Segoe UI"], 9)
        self.f_node = _font(["Bahnschrift SemiCondensed", "Bahnschrift", "Segoe UI"], 9)
        self.f_btn = _font(["Bahnschrift SemiBold Condensed", "Bahnschrift", "Segoe UI Semibold"], 12, "bold")
        self.state, self.headline, self.sub = "waiting", "WAITING", ""
        self.steps: dict[str, str] = {}
        self.cv.bind("<Button-1>", self._click)
        self.draw()

    # ---------------------------------------------------------------- model
    def set_status(self, state: str, headline: str, detail: str = "") -> None:
        self.state, self.headline = state, headline
        first = next((ln for ln in (detail or "").splitlines() if ln.strip()), "")
        self.sub = first[:60]
        if state == "waiting" and not any(v in ("active",) for v in self.steps.values()):
            pass
        self.draw()

    def set_steps(self, steps: dict[str, str]) -> None:
        self.steps = dict(steps)
        self.draw()

    # ---------------------------------------------------------------- drawing
    def _round_rect(self, x0, y0, x1, y1, r, **kw):
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1,
               x0, y1 - r, x0, y0 + r, x0, y0]
        return self.cv.create_polygon(pts, smooth=True, **kw)

    def _node(self, cx, cy, status):
        r = 11
        if status == "done":
            self.cv.create_oval(cx - r, cy - r, cx + r, cy + r, fill=GREEN, outline=GREEN)
            self.cv.create_line(cx - 5, cy + 0, cx - 1, cy + 4, cx + 6, cy - 4, fill=GREEN_DARK, width=2.6,
                                capstyle="round", joinstyle="round")
        elif status == "active":
            self.cv.create_oval(cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4, outline=AMBER_DIM, width=3)
            self.cv.create_oval(cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1, outline=AMBER, width=3)
        elif status == "failed":
            self.cv.create_oval(cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1, outline=RED, width=2)
            self.cv.create_line(cx - 4, cy - 4, cx + 4, cy + 4, fill=RED, width=2)
            self.cv.create_line(cx + 4, cy - 4, cx - 4, cy + 4, fill=RED, width=2)
        elif status == "later":
            self.cv.create_oval(cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1, outline="#5d6659", width=2, dash=(3, 3))
        else:
            self.cv.create_oval(cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1, outline=RING, width=2)

    def draw(self) -> None:
        cv = self.cv
        cv.delete("all")
        border, title_fg = STATE.get(self.state, STATE["waiting"])
        self._round_rect(1, 1, W - 1, H - 1, RADIUS, fill=BG, outline=border, width=1.5)
        # left: the state
        cv.create_text(18, 26, text=self.headline.upper(), anchor="w", fill=title_fg, font=self.f_title)
        cv.create_text(18, 50, text=self.sub, anchor="w", fill=MUTED, font=self.f_sub, width=190)
        # middle: the rail
        x0, x1, cy = 232, 812, 30
        slots = len(NODES)
        xs = [x0 + (x1 - x0) * i / (slots - 1) for i in range(slots)]
        prev = None
        for (node, x) in zip(NODES, xs):
            if node is None:
                cv.create_line(x, 14, x, 62, fill="#2f342d", width=1)
                prev = None
                continue
            key, label = node
            st = self.steps.get(key, "pending")
            if prev is not None:
                px, pst = prev
                col = GREEN if (pst == "done" and st in ("done", "active")) else LINE
                cv.create_line(px + 14, cy, x - 14, cy, fill=col, width=2)
            self._node(x, cy, st)
            col = {"done": INK, "active": AMBER, "failed": RED}.get(st, "#6f786b")
            cv.create_text(x, cy + 24, text=label.upper(), fill=col, font=self.f_node)
            prev = (x, st)
        # right: what the player can do now
        bx0, by0, bx1, by1 = 836, 14, W - 12, H - 14
        self.btn = None
        if self.state == "automating":
            cv.create_text((bx0 + bx1) / 2, 30, text="MOUSE HELD", fill=AMBER, font=self.f_node)
            cv.create_text((bx0 + bx1) / 2, 48, text="Shift+Esc stops", fill=MUTED, font=self.f_sub)
        elif self.state == "error" and self.on_run_now is not None:
            self.btn = ("run", self._round_rect(bx0, by0, bx1, by1, 8, fill=BG, outline="#6b6f69", width=1.5))
            cv.create_text((bx0 + bx1) / 2, (by0 + by1) / 2, text="RUN NOW", fill="#eef1ea", font=self.f_btn)
        elif self.on_end_turn is not None:
            self.btn = ("end", self._round_rect(bx0, by0, bx1, by1, 8, fill="#7fdc66", outline="#7fdc66"))
            cv.create_text((bx0 + bx1) / 2, (by0 + by1) / 2, text="BUILD & END TURN", fill="#0d1d09",
                           font=self.f_btn)
        self._btn_box = (bx0, by0, bx1, by1) if self.btn else None

    # ---------------------------------------------------------------- input
    def _click(self, e) -> None:
        if self._btn_box and self._btn_box[0] <= e.x <= self._btn_box[2] and self._btn_box[1] <= e.y <= self._btn_box[3]:
            kind = self.btn[0]
            fn = self.on_end_turn if kind == "end" else self.on_run_now
            if fn:
                fn()
            return
        self.on_pause()
