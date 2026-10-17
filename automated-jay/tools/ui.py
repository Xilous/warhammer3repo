"""Drive the game from the command line: screenshots, clicks, keys.

Screenshots never touch focus (window capture works while the game is behind other windows).
The game only accepts real input while it is the foreground window, so a chain that clicks or presses
keys raises the game for the duration of the chain and then ALWAYS puts the user's terminal back in
front (bot/focus.py), verified with retries, even if a command fails.

Every input primitive here first checks that the game is the foreground window and raises
bot.focus.InputAborted when it is not (the player alt-tabbed away): input never lands in another window.
Held keys and mouse buttons are always released in `finally`.

  python -X utf8 -m tools.ui shot OUT.png [--scale 0.6667]   # full screenshot (optionally downscaled)
  python -X utf8 -m tools.ui crop OUT.png x0 y0 x1 y1 [--zoom 2]
  python -X utf8 -m tools.ui click X Y [--right] [--double]   # full-resolution coordinates
  python -X utf8 -m tools.ui move X Y
  python -X utf8 -m tools.ui key NAME [--hold MOD]
  python -X utf8 -m tools.ui type TEXT                       # types text into the focused field
  python -X utf8 -m tools.ui wait SECONDS
Several commands can be chained with ' + ', e.g.  click 960 540 + wait 2 + shot a.png
"""
from __future__ import annotations
import contextlib
import functools
import sys
import time

import pydirectinput
import win32api
import win32con
import win32gui
from PIL import Image

from bot import config
from bot import killswitch
from bot.focus import InputAborted, game_focus, idle_seconds, require_game_front   # noqa: F401  (InputAborted re-exported)
from tools import timing, wait

pydirectinput.PAUSE = 0          # no sleeps inside pydirectinput: every gap below is explicit and measured

# The only fixed delays left in the input path, in rendered frames (tools/wait.py next_frame; the game samples
# input once per frame, about 150 frames/s here). Each is the measured minimum plus one frame of margin
# (tools/inputcal.py, 2026-10-16, 9.0.4, borderless 1920x1080):
HOVER_MAX_FRAMES = 2     # cursor arrival -> hover registered: 0.5-1.5 frames (130 trials, max 12 ms). A click whose
                         # button goes down before the hover registered is lost: 10/30 at once, 22/30 after half a
                         # frame, 220/220 once the target's state object had switched to a hover state. With a known
                         # target the click waits for exactly that; without one (or a target without hover states)
                         # it waits this long.
HOVER_WAIT_FRAMES = 40   # cap on waiting for a known target's hover state. Normally 0.5-1.5 frames; longer only right
                         # after a panel opened (the esc menu ignored a blind click 2 frames after it appeared).
HOVER_NUDGE_FRAMES = 4   # no hover after this long: nudge the cursor 1 px and back (see _await_hover)
CLICK_HOLD_FRAMES = 1    # button down -> up: 0 frames worked 100/100 once hover had registered
DC_HOLD_FRAMES = 1       # double-click: down -> up for each click; 0 worked 10/10
DC_GAP_FRAMES = 1        # double-click: first up -> second down; 0 worked 10/10
KEY_HOLD_FRAMES = 2      # key down -> up: 1 frame 60/60 and 1.5 frames 100/100; half a frame 13/20, 0 frames 0/20
WHEEL_GAP_FRAMES = 2     # between wheel notches: notches in the same frame count once (3 sent, 1 scrolled); 1 frame
                         # apart 20/20 (60 notches), 2 frames 30/30
DRAG_STEP_FRAMES = 2     # button down -> jump -> button up: 0 frames 12/24, 1 frame 24/24 (tech scrollbar); +1 margin
DRAG_STEPS = 1           # one jump: the game needs no intermediate cursor positions for a scrollbar drag


STALL_TIMEOUT = 10.0     # s: the game can stop rendering for seconds (after a load: 11.8 s measured); input sent
                         # during a stall lands in one frame and is lost, so the frame waits ride it out


def _frames(n: int) -> None:
    """Wait n rendered frames (through a stall of up to STALL_TIMEOUT); without a readable UI, n * FRAME_S."""
    if n <= 0:
        return
    try:
        wait.next_frame(n, timeout=STALL_TIMEOUT)
    except wait.WaitTimeout:
        time.sleep(n * wait.FRAME_S)


def _await_hover(probe, at=None, target=None) -> bool:
    """Until the game has registered the cursor over the target: the probe component's state object is one of its
    hover states. The game only re-checks hover when the mouse moves: a move it processed before a just-opened panel
    took input is never re-evaluated (seen on the esc menu: no hover for 1.2 s with the cursor on the button). So
    after HOVER_NUDGE_FRAMES without hover the cursor is nudged 1 px and back, as a hand would. At most
    HOVER_WAIT_FRAMES frames (a timeout is recorded). Stops early, returning False, when the target no longer covers
    the cursor (a panel sliding in). Without a probe: HOVER_MAX_FRAMES frames, True."""
    if probe is None:
        _frames(HOVER_MAX_FRAMES)
        return True
    ui = wait._ui()
    p, hs = probe
    t = time.perf_counter()
    left = HOVER_WAIT_FRAMES
    ok = False
    try:
        while left > 0 and not ok:
            n = min(HOVER_NUDGE_FRAMES, left)
            ok = wait.frames_until(lambda: ui.state_ptr(p) in hs, n)
            left -= n
            if ok or at is None:
                continue
            if target is not None and not _covers(ui, target, at):
                timing.wait_event(f"hover on {ui.id(p)}: target moved", (time.perf_counter() - t) * 1000, False, 0)
                return False
            if left > 0:
                require_game_front()
                win32api.SetCursorPos((at[0] + 1, at[1]))
                _frames(1)
                win32api.SetCursorPos(at)
                timing.input_event("nudge", 0.0, at=list(at))
    except InputAborted:
        raise
    except Exception:                    # noqa: BLE001  (the target was torn down: nothing to wait for)
        ok = False
    if not ok:
        timing.wait_event(f"hover on {ui.id(p)}", (time.perf_counter() - t) * 1000, False, 0)
    return ok


def _covers(ui, target, at) -> bool:
    try:
        k = ui.comp(getattr(target, "ptr", target))
    except Exception:                    # noqa: BLE001
        return True
    return k.x <= at[0] <= k.x + k.w and k.y <= at[1] <= k.y + k.h


def _probe(target, at) -> tuple[int, frozenset] | None:
    if target is None:
        return None
    try:
        return wait._ui().hover_probe(getattr(target, "ptr", target), at)
    except Exception:                    # noqa: BLE001
        return None


def _timed(kind: str):
    """Record the primitive into the active timing trace (tools/timing.py): kind, ms, where."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            if not timing.active():
                return fn(*a, **kw)
            t = time.perf_counter()
            k = "rclick" if kw.get("right") or (len(a) > 2 and a[2] is True and kind == "click") else kind
            with timing.quiet():
                try:
                    return fn(*a, **kw)
                finally:
                    timing.input_event(k, (time.perf_counter() - t) * 1000,
                                       at=[int(v) for v in a[:2]] if len(a) >= 2 and kind not in ("key", "hold") else a[:1])
        return wrapper
    return deco


def _hover_to(x: int, y: int, target=None) -> bool:
    """Move the cursor to (x, y) and wait until the game has registered it there (see _await_hover)."""
    require_game_front()
    probe = _probe(target, (x, y))
    if probe is not None and tuple(win32api.GetCursorPos()) == (x, y):
        try:
            if wait._ui().state_ptr(probe[0]) in probe[1]:
                return True              # already there and hovered
        except Exception:                # noqa: BLE001
            pass
    win32api.SetCursorPos((x, y))
    return _await_hover(probe, (x, y), target)


def _aim(x: int, y: int, target=None) -> tuple[int, int]:
    """Hover (x, y); when the target slid away under the cursor (a panel animating in), wait until its rectangle is
    still and aim again at the same point of it. Returns the point finally hovered."""
    if target is None:
        _hover_to(x, y)
        return x, y
    ui = wait._ui()
    ptr = getattr(target, "ptr", target)
    try:
        k0 = ui.comp(ptr)
        dx, dy = x - k0.x, y - k0.y
    except Exception:                    # noqa: BLE001
        _hover_to(x, y, target)
        return x, y
    for _ in range(3):
        if _hover_to(x, y, target) or _covers(ui, ptr, (x, y)):
            return x, y
        k = wait.stable_rect(ui, ptr, n=2, timeout=2.0, must=False, what=f"{k0.id} still before the click")
        if k is None:
            break
        x, y = int(k.x + dx), int(k.y + dy)
    return x, y


# ------------------------------------------------------------------ the player's hands
# Player report (2026-10-17): moving the mouse during a pass made a building click land elsewhere (a click goes
# wherever the cursor is when the button goes down). So right before every button press the cursor must still be
# exactly where it was aimed, and no key may have been pressed just now; if the player is busy, the pass holds
# still until mouse and keyboard have been left alone for YIELD_IDLE_S, then aims again. A pass never clicks where
# the player's cursor went. (Physical keys come from bot/killswitch.py; the mouse from the cursor position.)
YIELD_IDLE_S = 1.0
YIELD_TIMEOUT_S = 120.0       # the player kept going this long: stop the pass (InputAborted) rather than wait forever
CURSOR_SLACK_PX = 2
PLAYER_YIELDS = 0             # how often passes waited for the player (the runner reports it)
SUSPECT_CLICKS = 0            # clicks during which the player moved the cursor (the runner's verification redoes them)


def _player_busy(at=None) -> bool:
    if at is not None:
        cx, cy = win32api.GetCursorPos()
        if abs(cx - at[0]) > CURSOR_SLACK_PX or abs(cy - at[1]) > CURSOR_SLACK_PX:
            return True
    return killswitch.physical_key_age() < YIELD_IDLE_S


def yield_to_player(why: str = "") -> None:
    """Hold still until the player has left mouse and keyboard alone for YIELD_IDLE_S (this process sends nothing
    meanwhile, so the system's last-input time is theirs). InputAborted after YIELD_TIMEOUT_S or if they left the
    game."""
    global PLAYER_YIELDS
    PLAYER_YIELDS += 1
    print(f"  pass paused: you are using the mouse/keyboard{f' ({why})' if why else ''}; it goes on when you stop",
          flush=True)
    end = time.monotonic() + YIELD_TIMEOUT_S
    while idle_seconds() < YIELD_IDLE_S or killswitch.physical_key_age() < YIELD_IDLE_S:
        if time.monotonic() > end:
            raise InputAborted("you kept using the mouse/keyboard, so the pass stopped")
        time.sleep(0.05)
    require_game_front()


def _aim_clear(x: int, y: int, target=None) -> tuple[int, int]:
    """_aim, then make sure the player's hand is off the mouse and keyboard; after waiting for them, aim again."""
    for _ in range(4):
        ax, ay = _aim(x, y, target)
        if not _player_busy((ax, ay)):
            return ax, ay
        yield_to_player()
    raise InputAborted("the cursor kept being moved by the player")


def _after_click(at) -> None:
    """The player moved the cursor while the button was down: the click may have gone astray (counted; the runner's
    verification round redoes what did not happen)."""
    global SUSPECT_CLICKS
    if _player_busy(at):
        SUSPECT_CLICKS += 1


@_timed("click")
def click_at(x: int, y: int, right: bool = False, target=None) -> None:
    """Click at (x, y): move, wait until the game registered the cursor there (the target component's hover state
    when `target` is given, else HOVER_MAX_FRAMES frames), button down, CLICK_HOLD_FRAMES, up. No delay after:
    the caller waits for the click's effect (tools/wait.py).
    The game ignores pydirectinput/SendInput button events but accepts legacy mouse_event after a SetCursorPos
    (verified 2026-10-16). Raises InputAborted when the game is not in front."""
    down, up = ((win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP) if right
                else (win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP))
    x, y = _aim_clear(int(x), int(y), target)
    require_game_front(at=(x, y))            # again right before the button: the player may have just left
    win32api.mouse_event(down, 0, 0, 0, 0)
    try:
        _frames(CLICK_HOLD_FRAMES)
    finally:
        win32api.mouse_event(up, 0, 0, 0, 0)
    _after_click((x, y))


def click(ui, target, right: bool = False):
    """Click the centre of a component (pointer or Comp), waiting for its hover state before the button goes down.
    Returns the Comp clicked."""
    ptr = getattr(target, "ptr", target)
    k = ui.comp(ptr)
    if not _on_screen(k.center):             # a panel still sliding in from off screen: wait until it is still
        k = wait.stable_rect(ui, ptr, n=2, timeout=2.0, what=f"{k.id} still (was off screen)")
        if not _on_screen(k.center):
            raise RuntimeError(f"{k.id} is off screen at {k.center}")
    click_at(*k.center, right=right, target=ptr)
    return k


def _on_screen(p) -> bool:
    return 0 <= p[0] < config.RESOLUTION[0] and 0 <= p[1] < config.RESOLUTION[1]


def move_to(x: int, y: int) -> None:
    """Move the cursor (hover, park). No delay: a caller that needs the hover waits for it.
    Raises InputAborted when the game is not in front."""
    require_game_front()
    win32api.SetCursorPos((int(x), int(y)))


@_timed("move")
def move_path(points, frames: int = HOVER_MAX_FRAMES) -> None:
    """Jump the cursor through waypoints, `frames` rendered frames at each so the game registers it there (hover
    chains: a popup that stays open while the cursor is over its parent or itself). No interpolated moves: the game
    samples the cursor once per frame, so in-between positions only add time (and time in gaps between panels)."""
    for x, y in points:
        require_game_front()
        win32api.SetCursorPos((int(x), int(y)))
        _frames(frames)


@_timed("dclick")
def double_click(x: int, y: int, target=None) -> None:
    """Two clicks DC_GAP_FRAMES apart, after the hover registered (as click_at)."""
    x, y = _aim_clear(int(x), int(y), target)
    require_game_front(at=(x, y))
    for i in range(2):
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        try:
            _frames(DC_HOLD_FRAMES)
        finally:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        if i == 0:
            _frames(DC_GAP_FRAMES)


@_timed("drag")
def drag(x0: int, y0: int, x1: int, y1: int, steps: int = DRAG_STEPS, target=None) -> None:
    """Left-drag from (x0, y0) to (x1, y1) in `steps` moves one frame apart; the button is released even if the drag
    is interrupted. No delay after release: the caller waits until what it scrolled is stable."""
    x1, y1 = int(x1), int(y1)
    x0, y0 = _aim_clear(int(x0), int(y0), target)
    require_game_front(at=(x0, y0))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    try:
        _frames(DRAG_STEP_FRAMES)
        for i in range(1, steps + 1):
            win32api.SetCursorPos((x0 + (x1 - x0) * i // steps, y0 + (y1 - y0) * i // steps))
            _frames(DRAG_STEP_FRAMES)
    finally:
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


@_timed("wheel")
def wheel(x: int, y: int, notches: int, pause: float | None = None) -> None:
    """Mouse wheel over (x, y): positive notches scroll up / left. Notches go WHEEL_GAP_FRAMES apart (or `pause`
    seconds, for callers not converted yet). No delay after: the caller waits for the list to move."""
    x, y = int(x), int(y)
    _hover_to(x, y)
    if _player_busy((x, y)):
        yield_to_player()
        _hover_to(x, y)
    for i in range(abs(notches)):
        require_game_front(at=(x, y))        # a wheel event goes to the window under the cursor
        win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, 120 if notches > 0 else -120, 0)
        if pause is not None:
            time.sleep(pause)
        elif i < abs(notches) - 1:
            _frames(WHEEL_GAP_FRAMES)


@_timed("key")
def press(key: str) -> None:
    """Key down, KEY_HOLD_FRAMES rendered frames, key up (the game samples keys once per frame)."""
    if _player_busy():
        yield_to_player()
    require_game_front()
    pydirectinput.keyDown(key, _pause=False)
    try:
        _frames(KEY_HOLD_FRAMES)
    finally:
        pydirectinput.keyUp(key, _pause=False)


@contextlib.contextmanager
def held(key: str):
    """Hold a key for the duration of the block (registered by the game before the block runs: KEY_HOLD_FRAMES);
    it is released even if the block raises."""
    if _player_busy():
        yield_to_player()
    require_game_front()
    pydirectinput.keyDown(key, _pause=False)
    try:
        _frames(KEY_HOLD_FRAMES)
        yield
    finally:
        pydirectinput.keyUp(key, _pause=False)


@_timed("hold")
def hold_key(key: str, seconds: float) -> None:
    """Hold a key for a duration (WASD camera pans): a duration, not a delay."""
    with held(key):
        time.sleep(seconds)


def type_text(text: str) -> None:
    """Slow, held key presses: the game drops characters typed at normal automation speed,
    and ignores shifted capitals, so text should be lowercase."""
    for ch in text:
        hold_key("space" if ch == " " else ch, 0.04)
        time.sleep(0.09)


def grab() -> Image.Image:
    """Capture the game window itself (PrintWindow), so it works with the game in the background."""
    import ctypes
    import win32ui
    h = win32gui.FindWindow(None, config.WINDOW_TITLE)
    l, t, r, b = win32gui.GetClientRect(h)
    w, hh = r - l, b - t
    hdc = win32gui.GetWindowDC(h)
    mdc = win32ui.CreateDCFromHandle(hdc)
    sdc = mdc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mdc, w, hh)
    sdc.SelectObject(bmp)
    ctypes.windll.user32.PrintWindow(h, sdc.GetSafeHdc(), 0x2 | 0x1)   # full content, client area
    info = bmp.GetInfo()
    im = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1)
    win32gui.DeleteObject(bmp.GetHandle())
    sdc.DeleteDC()
    mdc.DeleteDC()
    win32gui.ReleaseDC(h, hdc)
    return im.copy()


def run(args: list[str]) -> None:
    cmd, rest = args[0], args[1:]
    opt = lambda name, default=None: rest[rest.index(name) + 1] if name in rest else default
    if cmd == "shot":
        im = grab()
        s = float(opt("--scale", 1))
        if s != 1:
            im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        im.save(rest[0])
    elif cmd == "crop":
        x0, y0, x1, y1 = (int(v) for v in rest[1:5])
        z = float(opt("--zoom", 1))
        im = grab().crop((x0, y0, x1, y1))
        if z != 1:
            im = im.resize((int(im.width * z), int(im.height * z)), Image.LANCZOS)
        im.save(rest[0])
    elif cmd == "click":
        x, y = int(rest[0]), int(rest[1])
        right = "--right" in rest
        for _ in range(2 if "--double" in rest else 1):
            click_at(x, y, right)
    elif cmd == "move":
        move_to(int(rest[0]), int(rest[1]))
    elif cmd == "key":
        mod = opt("--hold")
        with held(mod) if mod else contextlib.nullcontext():
            time.sleep(0.05 if mod else 0)
            press(rest[0])
            time.sleep(0.05 if mod else 0)
    elif cmd == "type":
        type_text(" ".join(rest))
    elif cmd == "wait":
        time.sleep(float(rest[0]))
    else:
        sys.exit(f"unknown command {cmd}")


INPUT_CMDS = {"click", "move", "key", "type"}


def main() -> int:
    chunks, cur = [], []
    for a in sys.argv[1:]:
        if a == "+":
            chunks.append(cur)
            cur = []
        else:
            cur.append(a)
    if cur:
        chunks.append(cur)
    if any(c[0] in INPUT_CMDS for c in chunks):
        with game_focus():
            for c in chunks:
                run(c)
    else:
        for c in chunks:
            run(c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
