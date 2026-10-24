"""Wait on game state, never on the clock.

Every wait here polls a condition on the UI tree or on memory, tightly (POLL_S, with time.sleep: on this machine
threading.Event.wait bottoms out at the 15.6 ms system tick, time.sleep(0.002) takes about 2 ms), until it holds or
a timeout passes. A timeout is never silent: with must=True (the default) it raises WaitTimeout naming what was
waited for; with must=False it returns None, and either way it is counted as a timeout in the timing trace
(tools/timing.py), so the time still lost to timeouts shows up per step.

Frames. The game writes the current time in ms (u32 at component +0x334) into every UI component it updates, twice
per rendered frame (measured 2026-10-16, 9.0.4: about 330 stamps/s; during a camera pan the camera eye changes
exactly once every 2 stamps, about 150 frames/s). next_frame(n) waits for 2n stamp changes of the root: n rendered
frames. The game samples input once per rendered frame: a key held for one stamp (half a frame) was seen 13/20
times, held 2 stamps 60/60 (tools/inputcal.py). FRAME_S is only the fallback when the stamp cannot be read.

    wait_until(pred, timeout, what)            pred() truthy -> its value
    next_frame(n)                              n UI frames
    appears(ui, cid, under=, start=)           a visible component -> Comp
    gone(ui, target)                           ptr / Comp / id no longer effectively visible (or freed)
    stable(read, n)                            read() unchanged for n consecutive frames -> value
    stable_rect(ui, ptr)                       the component's rectangle stable -> Comp
    state_is(ui, ptr, prefix)                  the component's state name starts with prefix ("hover", ...)
    value_changes(read, before)                read() != before -> new value
    camera_settled(s)                          the campaign camera still on screen (< 0.1 px/frame) -> Camera
    root_children_stable(ui, ms)               the set of visible root panels unchanged for ms -> ids
    pause(seconds, why)                        the only fixed sleep allowed; logged with its reason
"""
from __future__ import annotations
import operator
import struct
import time

from tools import timing

POLL_S = 0.002                 # tight poll; time.sleep is about 1 ms accurate here
FRAME_S = 1 / 120              # fallback frame length when the frame stamp cannot be read
FRAME_STAMP = 0x334            # u32 ms stamp the UI writes into each component it updates, twice per frame
STAMPS_PER_FRAME = 2

_sleep = timing.real_sleep
_perf = time.perf_counter
_MISSING = object()


class WaitTimeout(RuntimeError):
    """A condition on game state did not hold in time. The message says what was waited for and for how long."""


def _focus_check() -> None:
    """Inside a game_focus block (a pass), a wait aborts as soon as the player switches away from the game."""
    from bot import focus
    if getattr(focus._tls, "depth", 0):
        focus.require_game_front()


def wait_until(pred, timeout: float = 2.0, what: str = "", poll: float = POLL_S, must: bool = True,
               focus: bool | None = None):
    """Call pred() until it returns something truthy and return that. On timeout: WaitTimeout (must=True) or
    None. Exceptions from pred count as "not yet" (a read can fail while a panel is being torn down), but the
    last one is named in the timeout message."""
    t0 = _perf()
    end = t0 + timeout
    polls = 0
    last_ex = None
    next_focus = t0 + 0.05
    while True:
        polls += 1
        try:
            v = pred()
        except Exception as ex:          # noqa: BLE001  (a torn-down component reads as garbage for a moment)
            v, last_ex = None, ex
        now = _perf()
        if v:
            timing.wait_event(what or getattr(pred, "__name__", "?"), (now - t0) * 1000, True, polls)
            return v
        if now >= end:
            timing.wait_event(what or getattr(pred, "__name__", "?"), (now - t0) * 1000, False, polls,
                              timeout=timeout)
            if must:
                raise WaitTimeout(f"timed out after {timeout:.2f} s waiting for {what or pred}"
                                  + (f" (last error: {last_ex})" if last_ex else ""))
            return None
        if focus is not False and now >= next_focus:
            _focus_check()
            next_focus = now + 0.05
        _sleep(poll)


def pause(seconds: float, why: str) -> None:
    """A deliberate fixed delay (the measured minimum the game needs to register input). Recorded with `why`."""
    t = _perf()
    _sleep(seconds)
    timing.input_event("pause", (_perf() - t) * 1000, why=why)


# ------------------------------------------------------------------ frames

_default_ui = None


def _ui(ui=None):
    global _default_ui
    if ui is not None:
        return ui
    if _default_ui is None:
        from bot.sensor.ui import UI
        _default_ui = UI()
    return _default_ui


def frame_stamp(ui=None) -> int | None:
    """The UI's frame stamp (ms), or None when there is no UI root."""
    ui = _ui(ui)
    r = ui.find_root()
    if not r:
        return None
    return struct.unpack("<I", ui.pm.read_bytes(r + FRAME_STAMP, 4))[0]


def next_frame(n: int = 1, ui=None, timeout: float = 1.0) -> int:
    """Wait until the game has rendered n more frames (2n changes of the root's UI stamp). Returns n, or 0 when the
    stamp could not be read (then n * FRAME_S was slept instead). WaitTimeout when the UI stops updating for
    `timeout` (the game is frozen or loading)."""
    if n <= 0:
        return 0
    ui = _ui(ui)
    t0 = _perf()
    try:
        r = ui.find_root()
        if not r:
            raise RuntimeError("no UI root")
        rb = ui.rb
        a = r + FRAME_STAMP
        last = rb(a, 4)
    except Exception:                    # noqa: BLE001  (no game / no UI: fall back to time)
        _sleep(n * FRAME_S)
        return 0
    need = n * STAMPS_PER_FRAME
    seen = 0
    end = t0 + timeout
    while True:
        cur = rb(a, 4)
        if cur != last:
            seen += 1
            if seen >= need:
                return n
            last = cur
            continue
        if _perf() > end:
            timing.wait_event(f"{n} frame(s)", (_perf() - t0) * 1000, False, seen, timeout=timeout)
            raise WaitTimeout(f"timed out after {timeout:.2f} s waiting for {n} frame(s): the game UI stopped "
                              "updating (frozen or loading?)")
        _sleep(0.0003)


QUIET_SKIP = ("3d_ui_parent", "ai_attack_targets_parent", "mission_indicator_parent", "tutorial_halo_group")


def layout_sig(ui=None, depth: int = 3) -> tuple:
    """The open panels' layout from memory: (id, rect, visible) of every component down to `depth` under the root's
    children, leaving out the map labels (they move with the camera), the halo and the hover tooltips (they come and go
    with the cursor). 318 components, ~4 ms (2026-10-23)."""
    ui = _ui(ui)
    out = []

    def rec(c, d):
        k = ui.comp(c)
        out.append((k.id, int(k.x), int(k.y), int(k.w), int(k.h), k.visible))
        if d < depth:
            for ch in ui.children(c):
                rec(ch, d + 1)
    for c, n in ui.root_children():
        if n not in QUIET_SKIP and not (n or "").startswith("tooltip"):
            rec(c, 0)
    return tuple(out)


def ui_quiet(ui=None, frames: int = 3, cap: float = 3.0, stall: float = 0.25) -> bool:
    """Hands off until the game says it is done reacting: its UI layout (layout_sig) unchanged over `frames` rendered
    frames in a row, each on time (a frame later than `stall` starts the count again), at most `cap`. True once quiet.
    Used after every game action (player request 2026-10-23: let the game dictate the pace from memory instead of a
    fixed settle time; an action makes the game rebuild the panels it touched, then the layout holds still)."""
    if frames <= 0:
        return True
    ui = _ui(ui)
    t_end = _perf() + cap
    last, calm = None, 0
    while _perf() < t_end:
        t = _perf()
        try:
            next_frame(1, ui, timeout=1.0)
            cur = layout_sig(ui)
        except Exception:                # noqa: BLE001  (frozen, loading or a panel torn down: not quiet yet)
            last, calm = None, 0
            continue
        calm = calm + 1 if (cur == last and _perf() - t <= stall) else 0
        last = cur
        if calm >= frames:
            timing.wait_event("game quiet", (_perf() - t_end + cap) * 1000, True, calm)
            return True
    timing.wait_event("game quiet", cap * 1000, False, calm, timeout=cap)
    return False


def frames_until(pred, max_frames: int, ui=None) -> bool:
    """pred() becomes true within max_frames rendered frames (checked between stamp changes). False when the frames
    ran out first. For short input-registration checks (hover); not recorded as a wait."""
    ui = _ui(ui)
    if pred():
        return True
    try:
        r = ui.find_root()
        rb = ui.rb
        a = r + FRAME_STAMP
        last = rb(a, 4)
    except Exception:                    # noqa: BLE001
        _sleep(max_frames * FRAME_S)
        return bool(pred())
    need = max_frames * STAMPS_PER_FRAME
    seen = 0
    end = _perf() + max(0.25, max_frames * 0.05)
    while True:
        if pred():
            return True
        cur = rb(a, 4)
        if cur != last:
            seen += 1
            last = cur
            if seen >= need:
                return bool(pred())
        elif _perf() > end:
            return bool(pred())
        else:
            _sleep(0.0003)


def ui_live(ui=None, ms: float = 500, max_gap_ms: float = 100, timeout: float = 120.0, must: bool = True):
    """The game is rendering: the UI stamp has advanced with no gap over max_gap_ms for `ms`. After a save load the
    campaign UI tree (End Turn button included) exists while the game is still frozen for seconds (11.8 s measured
    on ENDGAME SKAVEN, 2026-10-16); input sent then is lost."""
    ui = _ui(ui)
    st = {"last": None, "t_last": 0.0, "since": None}

    def probe():
        now = _perf()
        cur = frame_stamp(ui)
        if cur is None:
            st.update(last=None, since=None)
            return False
        if cur != st["last"]:
            if st["last"] is None or (now - st["t_last"]) * 1000 > max_gap_ms:
                st["since"] = now
            st["last"], st["t_last"] = cur, now
        elif (now - st["t_last"]) * 1000 > max_gap_ms:
            st["since"] = None
        return st["since"] is not None and (now - st["since"]) * 1000 >= ms
    return wait_until(probe, timeout, f"game rendering smoothly for {ms:.0f} ms", poll=0.001, must=must)


# ------------------------------------------------------------------ UI conditions

def appears(ui, cid: str, under: str | int | None = None, timeout: float = 2.0, inside=None, must: bool = True,
            start: int | None = None, what: str | None = None):
    """The first visible component with this id (scoped by `under` / `start`, see UI.first) -> Comp.
    inside: a Comp the component's rectangle must lie in (lists whose off-clip items still read visible)."""
    def probe():
        c = ui.first(cid, under=under, start=start)
        if c is None:
            return None
        k = ui.comp(c)
        if inside is not None and not _inside(k, inside):
            return None
        return k
    return wait_until(probe, timeout, what or f"{cid} appears" + (f" under {under}" if under else ""), must=must)


def _inside(k, clip, margin: float = 0.0) -> bool:
    return (clip.x + margin <= k.x and k.x + k.w <= clip.x + clip.w - margin
            and clip.y + margin <= k.y and k.y + k.h <= clip.y + clip.h - margin)


def gone(ui, target, timeout: float = 2.0, must: bool = True, what: str | None = None) -> bool:
    """target: a component pointer or Comp (gone = it or an ancestor is hidden, or it was detached / freed), or an
    id string (gone = no visible component with that id is left)."""
    if isinstance(target, str):
        probe = lambda: ui.first(target) is None
        name = target
    else:
        ptr = getattr(target, "ptr", target)
        probe = lambda: not ui.effective_visible(ptr)
        name = getattr(target, "id", None) or ui.id(ptr) or hex(ptr)
    return bool(wait_until(probe, timeout, what or f"{name} gone", must=must))


def stable(read, n: int = 3, eps: float = 0.5, timeout: float = 2.0, what: str = "", must: bool = True, ui=None):
    """read() gives the same value (numbers or tuples of numbers within eps; anything else by ==) for n consecutive
    UI frames. Returns the value. Sampling once per frame matters: polling faster than the game updates would see
    "stable" between two frames of an animation."""
    ui = _ui(ui)
    state = {"v": _MISSING, "same": 0}

    def close(a, b) -> bool:
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(a - b) <= eps
        if isinstance(a, tuple) and isinstance(b, tuple) and len(a) == len(b):
            return all(close(x, y) for x, y in zip(a, b))
        return a == b

    def probe():
        try:
            v = read()
        except Exception:                   # noqa: BLE001  (torn down mid-animation: not stable yet)
            state["v"], state["same"] = _MISSING, 0
            next_frame(1, ui)
            return None
        if state["v"] is not _MISSING and close(v, state["v"]):
            state["same"] += 1
        else:
            state["same"] = 0
        state["v"] = v
        if state["same"] >= n:
            return (v,)
        next_frame(1, ui)
        return None
    r = wait_until(probe, timeout, what or f"stable {getattr(read, '__name__', 'value')}", poll=0, must=must)
    return r[0] if r else None


def stable_rect(ui, ptr, n: int = 3, eps: float = 0.5, timeout: float = 2.0, must: bool = True, what: str = ""):
    """The component's (x, y, w, h) unchanged for n frames (a slide-in, fade or scroll has finished) -> Comp."""
    ptr = getattr(ptr, "ptr", ptr)

    def rect():
        k = ui.comp(ptr)
        return (k.x, k.y, k.w, k.h)
    r = stable(rect, n, eps, timeout, what or f"{ui.id(ptr)} rect stable", must, ui)
    return ui.comp(ptr) if r else None


def state_is(ui, ptr, prefix: str, timeout: float = 1.0, must: bool = True, what: str = ""):
    """The component's state name starts with prefix ("hover", "selected", "active", ...) -> the state name."""
    ptr = getattr(ptr, "ptr", ptr)

    def probe():
        st = ui.state(ptr) or ""
        return st if st.startswith(prefix) else None
    return wait_until(probe, timeout, what or f"{ui.id(ptr)} state {prefix}", must=must)


def value_changes(read, before=_MISSING, timeout: float = 1.0, cmp=operator.ne, what: str = "", must: bool = True,
                  poll: float = POLL_S):
    """read() differs from `before` (read now when not given) -> the new value. cmp(new, before) decides."""
    if before is _MISSING:
        before = read()
    box = []

    def probe():
        v = read()
        if cmp(v, before):
            box.append(v)
            return True
        return False
    ok = wait_until(probe, timeout, what or f"{getattr(read, '__name__', 'value')} changes", poll=poll, must=must)
    return box[-1] if ok else None


def camera_settled(s, still_px: float = 0.1, n: int = 3, moving_first: float = 0.0, timeout: float = 4.0,
                   must: bool = True, what: str = "", ui=None):
    """The campaign camera has stopped, in screen terms: the map point at the screen centre moved less than still_px
    pixels per frame for n frames in a row. With moving_first > 0, first wait (up to that many seconds) for the
    camera to start moving, so a wait right after the click cannot see "still" before the pan began. -> Camera.

    Measured 2026-10-16: a Lords & Heroes double-click and a minimap click both pan with easing, ~1.9 s until the
    target is within 1 px (4 px at ~1.77 s, 50 px at ~1.5 s); neither is instant. Read camera.py for the block."""
    from bot.sensor.camera import read_camera
    import numpy as np
    W, H = 1920, 1080
    st = {"prev": None, "still": 0, "moved": False}

    def motion() -> float | None:
        cam = read_camera(s)
        prev, st["prev"] = st["prev"], cam
        if prev is None:
            return None
        gx, gy = prev.ground_at_center()
        p = cam.project(gx, gy)
        return 1e9 if p is None else float(np.hypot(p[0] - W / 2, p[1] - H / 2))

    if moving_first > 0:
        e0 = tuple(read_camera(s).eye)
        wait_until(lambda: tuple(read_camera(s).eye) != e0, moving_first, "camera starts moving", must=False)

    def probe():
        try:
            d = motion()
        except Exception:                    # noqa: BLE001  (block briefly unreadable after some UI actions)
            d = None
            st["prev"] = None
        if d is not None and d < still_px:
            st["still"] += 1
        else:
            st["still"] = 0
        if st["still"] >= n:
            return st["prev"]
        next_frame(1, ui)
        return None
    return wait_until(probe, timeout, what or f"camera still (< {still_px} px/frame)", poll=0, must=must)


def root_children(ui) -> tuple[str, ...]:
    """Ids of the visible children of the UI root, in order (cheap: one array read plus cached ids)."""
    return tuple(cid for _c, cid in ui.root_children())


def root_children_stable(ui, ms: float = 150, timeout: float = 3.0, must: bool = True, what: str = ""):
    """No root panel appeared or disappeared for `ms` (popups slide in on their own schedule) -> the ids."""
    state = {"v": None, "since": 0.0}

    def probe():
        v = root_children(ui)
        now = _perf()
        if v != state["v"]:
            state["v"], state["since"] = v, now
            return None
        return v if (now - state["since"]) * 1000 >= ms else None
    return wait_until(probe, timeout, what or f"root panels stable {ms:.0f} ms", must=must)
