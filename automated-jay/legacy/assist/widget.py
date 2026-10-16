"""Small always-on-top status widget shown over the game (the game runs windowed, so it stays visible).

States: WAITING (AI turns / no campaign), AUTOMATING, YOUR TURN, PAUSED.
Left-click toggles pause. The widget never takes focus on its own after it is created.
"""
from __future__ import annotations
import queue
import tkinter as tk

COLORS = {
    "waiting": ("#2b2b2b", "#bdbdbd"),
    "automating": ("#5a3d00", "#ffd27a"),
    "your turn": ("#123d1a", "#8dff9c"),
    "paused": ("#3a1f1f", "#ffb0b0"),
    "error": ("#4a0000", "#ff7070"),
}


class Widget:
    def __init__(self, x: int = 10, y: int = 72, on_toggle=None) -> None:
        self.q: queue.Queue = queue.Queue()
        self.on_toggle = on_toggle
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.geometry(f"+{x}+{y}")
        self.frame = tk.Frame(self.root, padx=10, pady=6)
        self.frame.pack()
        self.title = tk.Label(self.frame, font=("Segoe UI", 12, "bold"), anchor="w")
        self.title.pack(fill="x")
        self.detail = tk.Label(self.frame, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=320)
        self.detail.pack(fill="x")
        self.root.bind("<Button-1>", self._click)      # fires for every widget inside too (binding them as well toggled twice)
        self.set("waiting", "starting", "")
        self.root.after(150, self._poll)

    def _click(self, _event=None) -> None:
        if self.on_toggle:
            self.on_toggle()

    def set(self, state: str, headline: str, detail: str = "") -> None:
        bg, fg = COLORS.get(state, COLORS["waiting"])
        for w in (self.frame, self.title, self.detail):
            w.configure(bg=bg)
        self.root.configure(bg=bg)
        self.title.configure(text=headline, fg=fg)
        self.detail.configure(text=detail, fg="#e8e8e8")

    def post(self, state: str, headline: str, detail: str = "") -> None:
        """Thread-safe update."""
        self.q.put((state, headline, detail))

    def _poll(self) -> None:
        try:
            while True:
                self.set(*self.q.get_nowait())
        except queue.Empty:
            pass
        self.root.after(150, self._poll)

    def run(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        self.root.after(0, self.root.destroy)
