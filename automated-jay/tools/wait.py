"""Wait on game state, never on the clock.

Every wait here polls a condition on the UI tree or on memory, tightly (POLL_S, with time.sleep: on this machine
threading.Event.wait bottoms out at the 15.6 ms system tick, time.sleep(0.002) takes about 2 ms), until it holds or
a timeout passes. A timeout is never silent: with must=True (the default) it raises WaitTimeout naming what was
waited for; with must=False it returns None, and either way it is counted as a timeout in the timing trace
(tools/timing.py), so the time still lost to timeouts shows up per step.

Frames. The game writes the current time in ms (u32 at component +0x334) into every UI component it updates,
once per UI frame (measured 2026-10-16, 9.0.4: about 330 updates/s on the campaign map and in menus, in front
or behind). The root's stamp changing is the next frame: next_frame(n) waits for n of them. FRAME_S is only the
fallback when the stamp cannot be read.

    wait_until(pred, timeout, what)            pred() truthy -> its value
    next_frame(n)                              n UI frames
    appears(ui, cid, under=, start=)           a visible component -> Comp
    gone(ui, target)                           ptr / Comp / id no longer effectively visible (or freed)
    stable(read, n)                            read() unchanged for n consecutive frames -> value
    stable_rect(ui, ptr)                       the component's rectangle stable -> Comp
    state_is(ui, ptr, prefix)                  the component's state name starts with prefix ("hover", ...)
    value_changes(read, before)                read() != before -> new value
    camera_settled(s, near=)                   the campaign camera eye still for n frames -> Camera
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
FRAME_STAMP = 0x334            # u32 ms stamp the UI writes into each component it updates, once per frame

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
    """Wait until the UI has updated n more times. Returns the frames seen (n), or 0 when the stamp could not be
    read (then n * FRAME_S was slept instead)."""
    if n <= 0:
        return 0
    ui = _ui(ui)
    t0 = _perf()
    try:
        r = ui.find_root()
        if not r:
            raise RuntimeError("no UI root")
        pm = ui.pm
        last = pm.read_bytes(r + FRAME_STAMP, 4)
        seen = 0
        end = t0 + timeout
        while seen < n:
            cur = pm.read_bytes(r + FRAME_STAMP, 4)
            if cur != last:
                seen += 1
                last = cur
                continue
            if _perf() > end:
                raise WaitTimeout(f"timed out after {timeout:.2f} s waiting for {n} UI frame(s) (game frozen?)")
            _sleep(0.0005)
        return n
    except WaitTimeout:
        raise
    except Exception:
        _sleep(n * FRAME_S)
        return 0


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


def camera_settled(s, near: tuple[float, float] | None = None, tol: float = 1.0, n: int = 3, eps: float = 1e-3,
                   timeout: float = 3.0, must: bool = True, what: str = "", ui=None):
    """The campaign camera has stopped: eye unchanged (within eps) for n frames, and with `near` (map x, y) the
    ground point at the screen centre within tol of it. -> Camera."""
    from bot.sensor.camera import read_camera

    def eye():
        return tuple(float(v) for v in read_camera(s).eye)
    if near is not None:
        def ok():
            cam = read_camera(s)
            gx, gy = cam.ground_at_center()
            return cam if ((gx - near[0]) ** 2 + (gy - near[1]) ** 2) ** 0.5 <= tol else None
        wait_until(ok, timeout, what or f"camera near {near[0]:.1f},{near[1]:.1f}", must=must)
    v = stable(eye, n, eps, timeout, what or "camera settled", must, ui)
    return read_camera(s) if v is not None else None


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
