"""Focus discipline: the game is only raised while input is being sent, and the user's terminal
is ALWAYS put back in front afterwards, verified, with retries. If another non-game window (such as the
assistant's own window) was in front, that one is restored instead; the terminal is the fallback.

The terminal window is remembered in runs/terminal_hwnd the first time it is seen (Windows Terminal,
class CASCADIA_HOSTING_WINDOW_CLASS). Use:

    with game_focus():
        ...send clicks / keys...
    # terminal is back in front here, even if the block raised

game_focus also holds a system-wide mutex (input_lock), so only one of this project's processes (the
assistant, a test harness, tools/ui.py) sends input to the game at a time: one process's clicks cannot land
while another has just handed focus back, and nobody raises the game in the middle of someone else's pass.

The player always wins: every input primitive (tools/ui.py) calls require_game_front() first, and when the
game is no longer the foreground window (the player alt-tabbed away mid-pass) it raises InputAborted instead of
sending anything. A nested game_focus never pulls the game back in front, and the outer one leaves the focus
wherever the player put it.
"""
from __future__ import annotations
import contextlib
import threading
import time

import pydirectinput
import win32con
import win32gui

from . import config, killswitch

killswitch.install()          # Shift+Esc ends any process that can send input (bot/killswitch.py)

TERMINAL_CLASSES = ("CASCADIA_HOSTING_WINDOW_CLASS", "ConsoleWindowClass")
HWND_FILE = config.RUNS_DIR / "terminal_hwnd"
INPUT_MUTEX = "Local\\automated-jay-input"   # system-wide name: every process of this project shares it
INPUT_LOCK_TIMEOUT = 900.0      # seconds; a full turn-start pass can take minutes

_tls = threading.local()        # depth of game_focus blocks in this thread


class InputAborted(BaseException):
    """The player took the focus away from the game during a pass. A BaseException (like KeyboardInterrupt) so
    that the steps' broad `except Exception` handlers cannot swallow it: the whole pass stops, `finally` blocks
    still run (and their own input raises this again instead of landing in the player's window)."""


def game_hwnd() -> int:
    return win32gui.FindWindow(None, config.WINDOW_TITLE)


def require_game_front(at: tuple[int, int] | None = None) -> None:
    """Raise InputAborted unless the game is the foreground window. Called before every click, key and move.
    With `at`, the window under that point must be the game too: a mouse button or wheel event goes to the window
    under the cursor, and a topmost window (a notification, a chat overlay, another app the player is bringing up)
    can cover the game while the game still has the focus. Our own overlay lets clicks through while automating,
    so it is not in the way."""
    g = game_hwnd()
    if not g:
        raise InputAborted("the game window is gone")
    if win32gui.GetForegroundWindow() != g:
        raise InputAborted("the game is not in front (you switched windows)")
    if at is not None:
        h = win32gui.WindowFromPoint((int(at[0]), int(at[1])))
        top = win32gui.GetAncestor(h, win32con.GA_ROOT) if h else 0
        if top != g:
            name = win32gui.GetWindowText(top) if top else ""
            raise InputAborted(f"another window{f' ({name!r})' if name else ''} covers the game at {at[0]},{at[1]}")


def idle_seconds() -> float:
    """Seconds since the last keyboard or mouse input anywhere on the desktop (GetLastInputInfo)."""
    import ctypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    li = LASTINPUTINFO()
    li.cbSize = ctypes.sizeof(li)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li)):
        return 0.0
    now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
    return ((now - li.dwTime) & 0xFFFFFFFF) / 1000.0


def _valid_terminal(h: int) -> bool:
    return bool(h) and win32gui.IsWindow(h) and win32gui.GetClassName(h) in TERMINAL_CLASSES


def terminal_hwnd() -> int | None:
    """The user's terminal: the remembered one if still open, else the current foreground terminal,
    else any visible terminal window."""
    if HWND_FILE.exists():
        try:
            h = int(HWND_FILE.read_text().strip())
            if _valid_terminal(h):
                return h
        except ValueError:
            pass
    f = win32gui.GetForegroundWindow()
    if _valid_terminal(f):
        _remember(f)
        return f
    found: list[int] = []
    win32gui.EnumWindows(lambda h, _: found.append(h) if win32gui.IsWindowVisible(h) and _valid_terminal(h) else None, None)
    if found:
        _remember(found[0])
        return found[0]
    return None


def _remember(h: int) -> None:
    config.RUNS_DIR.mkdir(exist_ok=True)
    HWND_FILE.write_text(str(h))


def _force_foreground(h: int) -> None:
    """Attach to the current foreground thread's input queue so Windows allows the switch
    (the foreground lock otherwise refuses SetForegroundWindow from a background process)."""
    import ctypes
    import win32process
    user32 = ctypes.windll.user32
    fg = win32gui.GetForegroundWindow()
    cur = ctypes.windll.kernel32.GetCurrentThreadId()
    fg_thread = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
    attached = False
    if fg_thread and fg_thread != cur:
        attached = bool(user32.AttachThreadInput(fg_thread, cur, True))
    try:
        user32.keybd_event(0x12, 0, 0, 0)            # Alt down/up also satisfies the foreground rule
        user32.keybd_event(0x12, 0, 2, 0)
        if win32gui.IsIconic(h):
            win32gui.ShowWindow(h, win32con.SW_RESTORE)
        user32.BringWindowToTop(h)
        user32.SetForegroundWindow(h)
    finally:
        if attached:
            user32.AttachThreadInput(fg_thread, cur, False)


FOCUS_SETTLE_FRAMES = 2         # after the game came to the front: keys sent 0 frames after the switch were lost (0/15),
                                # 1 frame after it worked 10/10, 2 frames 30/30; clicks worked at once (20/20)
                                # (tools/inputcal.py focus and a key variant, 2026-10-16): 1 frame minimum + 1 margin


def _raise(h: int) -> bool:
    """Bring h to the front; returns True once it is the foreground window. After each attempt the foreground is
    polled every 2 ms (the switch usually lands at once) before the next, stronger, attempt."""
    for attempt in range(8):
        if win32gui.GetForegroundWindow() == h:
            return True
        try:
            if attempt < 2:
                if win32gui.IsIconic(h):
                    win32gui.ShowWindow(h, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(h)
            else:
                _force_foreground(h)
        except Exception:
            try:
                _force_foreground(h)
            except Exception:
                pass
        end = time.perf_counter() + 0.15 + 0.1 * attempt
        while time.perf_counter() < end:
            if win32gui.GetForegroundWindow() == h:
                return True
            time.sleep(0.002)
    return win32gui.GetForegroundWindow() == h


def return_to_terminal() -> bool:
    t = terminal_hwnd()
    if t is None:
        return False
    return _raise(t)


@contextlib.contextmanager
def input_lock(timeout: float = INPUT_LOCK_TIMEOUT):
    """System-wide mutex around sending input. Re-entrant in the same thread (a Windows mutex), so nested
    game_focus blocks are fine; another process waits until the holder has handed focus back."""
    import win32event
    h = win32event.CreateMutex(None, False, INPUT_MUTEX)
    r = win32event.WaitForSingleObject(h, int(timeout * 1000))
    if r not in (win32event.WAIT_OBJECT_0, win32event.WAIT_ABANDONED):     # abandoned: holder died, we own it
        h.Close()
        raise RuntimeError("another process is still sending input to the game")
    try:
        yield
    finally:
        win32event.ReleaseMutex(h)
        h.Close()


def _settle_after_raise() -> None:
    try:
        from tools import wait
        wait.next_frame(FOCUS_SETTLE_FRAMES)
    except Exception:                        # noqa: BLE001  (UI not readable: fall back to time)
        time.sleep(0.02)


@contextlib.contextmanager
def game_focus():
    with input_lock():
        # the outermost holder takes the mouse away from the player for as long as the assistant has the game
        # (player request 2026-10-17: "ensure I don't interrupt it"); bot/killswitch.py swallows their physical
        # mouse events meanwhile, Shift+Esc still works, and the hold ends here whatever happens
        outer = getattr(_tls, "depth", 0) == 0
        if outer:
            killswitch.hold_mouse(True)
        try:
            terminal_hwnd()                     # remember it before we take focus away
            g = game_hwnd()
            if not g:
                raise RuntimeError("game window not found")
            prev = win32gui.GetForegroundWindow()
            depth = getattr(_tls, "depth", 0)
            if prev == g:
                # already in front (an outer game_focus owns the restore): do not hand focus back here
                _tls.depth = depth + 1
                try:
                    yield g
                finally:
                    _tls.depth = depth
                return
            if depth:
                # inside a pass and the game has lost the front: the player switched windows. Never pull it back.
                raise InputAborted("the game is not in front (you switched windows)")
            back_to = prev if prev and win32gui.IsWindow(prev) else None
            _tls.depth = 1
            try:
                if not _raise(g):
                    raise RuntimeError("could not bring the game to the front")
                _settle_after_raise()
                yield g
            finally:
                _tls.depth = 0
                if win32gui.GetForegroundWindow() == g:     # otherwise the player already moved on: leave it there
                    ok = _raise(back_to) if back_to else return_to_terminal()
                    if not ok:
                        ok = return_to_terminal()
                    if not ok:
                        print("WARNING: could not return focus to the terminal")
        finally:
            if outer:
                killswitch.hold_mouse(False)
