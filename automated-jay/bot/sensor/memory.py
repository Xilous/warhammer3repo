"""Memory sensor: reads the allowlisted State from the running game.

Anchor strategy (patch-resilient):
  1. A static pointer in the exe's data section -> campaign model (found by tools/probe.py,
     stored in anchors.json as an offset from the module base).
  2. Field offsets from that object, also in anchors.json.
If the static pointer is missing or stale, the reader falls back to a heap scan for the
campaign_variables array and re-derives the model base.

Robust for day-to-day use:
  - Creating a sensor never fails: with the game closed it is simply detached (read() returns ok=False,
    `pm` raises GameNotRunning). It re-attaches by itself once the game runs again, and notices when the
    game process exits or is replaced (restart), at most every ALIVE_CHECK_SECONDS.
  - The model is re-resolved through the static pointer on every read, so the main menu (no campaign) and a
    different save (a new model object) are seen at once. Nothing is cached beyond one validation.
  - The heap fallback scans GBs of memory: at most every HEAP_SCAN_MIN_INTERVAL seconds (backing off to
    HEAP_SCAN_MAX_INTERVAL while it keeps failing), and a candidate is only accepted when the exe holds a static
    pointer to it AND its turn fields read sanely. The DB and engine copies of the same float array have neither.
  - `epoch` goes up whenever the process or the model changes; holders of derived caches (the UI root in
    bot/sensor/ui.py) drop them when it moves.
  - Every sensor in this Python process shares one process handle (the app, the runner and each step create
    sensors; one handle each leaked a handle per refresh).

Only fields a player could see on screen are exposed. The reader can technically see
everything; the schema is the guard, not the reader.
"""
from __future__ import annotations
import ctypes
import ctypes.wintypes as wt
import json
import struct
import threading
import time

import pymem

from .. import config
from ..schema import State
from . import memscan, cvtable

ATTACH_RETRY_SECONDS = 2.0      # a detached sensor looks for the game process at most this often
ALIVE_CHECK_SECONDS = 1.0       # an attached sensor checks at most this often that the process still runs
HEAP_SCAN_MIN_INTERVAL = 30.0   # the heap fallback reads GBs: never more often than this
HEAP_SCAN_MAX_INTERVAL = 300.0  # ...and backs off to this while it keeps failing
MAX_TURN = 5000

_STILL_ACTIVE = 259
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
_k32.GetExitCodeProcess.restype = wt.BOOL


class GameNotRunning(RuntimeError):
    pass


# ------------------------------------------------------------------ the shared process handle

_lock = threading.Lock()
_att: dict = {}          # pid, pm, base, size, checked (monotonic time of the last alive check)
_last_try = 0.0
_heap_lock = threading.Lock()
_heap = {"pid": None, "next": 0.0, "wait": HEAP_SCAN_MIN_INTERVAL}     # heap-scan rate limit, per game process


def _save_anchor(key: str, value) -> None:
    try:
        a = json.loads(config.ANCHORS_FILE.read_text()) if config.ANCHORS_FILE.exists() else {}
        a[key] = value
        tmp = config.ANCHORS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(a, indent=2))
        tmp.replace(config.ANCHORS_FILE)
    except (OSError, ValueError):
        pass


def _alive(pm: pymem.Pymem) -> bool:
    code = wt.DWORD()
    if not pm.process_handle or not _k32.GetExitCodeProcess(pm.process_handle, ctypes.byref(code)):
        return False
    return code.value == _STILL_ACTIVE


def _close(att: dict) -> None:
    try:
        att["pm"].close_process()
    except Exception:
        pass


def attachment() -> dict | None:
    """{pid, pm, base, size} of the running game, or None. Re-opens the process after it exited or was restarted;
    while the game is closed, looks again at most every ATTACH_RETRY_SECONDS."""
    global _last_try
    with _lock:
        now = time.monotonic()
        if _att:
            if now - _att["checked"] < ALIVE_CHECK_SECONDS:
                return dict(_att)
            if _alive(_att["pm"]):
                _att["checked"] = now
                return dict(_att)
            _close(_att)                          # the game exited (or crashed): forget its handle
            _att.clear()
            _last_try = 0.0
        if now - _last_try < ATTACH_RETRY_SECONDS:
            return None
        _last_try = now
        try:
            pm, base, size = memscan.attach(config.PROCESS_NAME)
        except Exception:                         # not running, or still starting (module not loaded yet)
            return None
        _att.update(pid=pm.process_id, pm=pm, base=base, size=size, checked=now)
        return dict(_att)


class MemorySensor:
    name = "memory"

    def __init__(self) -> None:
        self.anchors: dict = {}
        if config.ANCHORS_FILE.exists():
            self.anchors = json.load(open(config.ANCHORS_FILE))
        self.pid: int | None = None
        self.epoch = 0                        # bumped when the game process or the campaign model changes
        self._model: int | None = None        # the model the last resolve found (only to notice changes)
        self._sync()

    # ---- process ---------------------------------------------------------
    def _sync(self) -> dict | None:
        a = attachment()
        pid = a["pid"] if a else None
        if pid != self.pid:                   # attached, detached or a new game process: start over
            self.pid = pid
            self._model = None
            self.epoch += 1
        return a

    @property
    def attached(self) -> bool:
        return self._sync() is not None

    def _need(self) -> dict:
        a = self._sync()
        if a is None:
            raise GameNotRunning(f"{config.PROCESS_NAME} is not running")
        return a

    @property
    def pm(self) -> pymem.Pymem:
        a = _att                              # fast path, taken by nearly every read: no lock, no copy
        pm = a.get("pm")
        if pm is not None and a.get("pid") == self.pid and time.monotonic() - a.get("checked", 0) < ALIVE_CHECK_SECONDS:
            return pm
        return self._need()["pm"]

    @property
    def base(self) -> int:
        return self._need()["base"]

    @property
    def size(self) -> int:
        return self._need()["size"]

    # ---- anchoring -------------------------------------------------------
    @property
    def model(self) -> int | None:
        """The live campaign model, re-resolved on every access (None at the main menu / with no game)."""
        return self.locate()

    def locate(self) -> int | None:
        """Resolve the campaign-model base: static pointer first, rate-limited heap scan second."""
        a = self._sync()
        if a is None:
            return None
        pm, base = a["pm"], a["base"]
        ptr_off = self.anchors.get("model_static_ptr_offset")
        cand = None
        if ptr_off is not None:
            try:
                cand = pm.read_ulonglong(base + ptr_off)
            except Exception:
                cand = None
            if cand and self._is_live_model(pm, cand, strict=False):
                return self._set_model(cand)
            if ptr_off is not None and cand == 0:
                return self._set_model(None)     # the pointer is there and empty: no campaign loaded
        return self._set_model(self._heap_locate(pm, a["base"], a["size"]))

    def _set_model(self, m: int | None) -> int | None:
        if m != self._model:
            self._model = m
            self.epoch += 1
        return m

    def _heap_locate(self, pm, base: int, size: int) -> int | None:
        """Heap fallback for a stale static pointer (game patched). Rate-limited for the whole process (every step
        makes its own sensor), one scan at a time, and only accepts a candidate the exe points at whose turn fields
        read sanely, so a DB or engine copy of the array is never taken. The static pointer it finds is saved to
        anchors.json, so the scan is not repeated."""
        if _heap["pid"] != self.pid:
            _heap.update(pid=self.pid, next=0.0, wait=HEAP_SCAN_MIN_INTERVAL)
        if time.monotonic() < _heap["next"] or not _heap_lock.acquire(blocking=False):
            return None
        try:
            hits = memscan.scan_bytes(pm, cvtable.needle(), limit=8)
            for cand in (h - config.CV_OFFSET_MODEL for h in hits):
                if not self._is_live_model(pm, cand, strict=True):
                    continue
                ptrs = memscan.scan_pointers_in_module(pm, base, size, cand, cand)
                if ptrs:
                    self.anchors["model_static_ptr_offset"] = off = ptrs[0][0] - base
                    _save_anchor("model_static_ptr_offset", off)
                    _heap.update(next=0.0, wait=HEAP_SCAN_MIN_INTERVAL)
                    return cand
        except Exception:
            pass
        finally:
            _heap_lock.release()
        _heap["next"] = time.monotonic() + _heap["wait"]
        _heap["wait"] = min(HEAP_SCAN_MAX_INTERVAL, _heap["wait"] * 2)
        return None

    def _is_live_model(self, pm, cand: int, strict: bool) -> bool:
        """The campaign_variables array at the model offset, and a turn counter that reads like one. Strict (heap
        candidates) also needs the turn + 1 cross-check field to agree; the static pointer's target is not held to
        that, so a moment where the two disagree (end of turn) cannot make the campaign look unloaded."""
        if not self._looks_like_model(pm, cand):
            return False
        turn = self._field("turn", "<i", cand, pm)
        if turn is None or not 0 < turn < MAX_TURN:
            return False
        if not strict:
            return True
        return self._field("turn_plus_one", "<i", cand, pm) == turn + 1

    def _looks_like_model(self, pm, cand: int) -> bool:
        if cand <= 0x10000:
            return False
        try:
            blob = pm.read_bytes(cand + config.CV_OFFSET_MODEL, config.CV_COUNT * 4)
        except Exception:
            return False
        ok, _ = cvtable.match_score(blob)
        return ok >= config.CV_COUNT - 32   # tolerate a few modded variables

    # ---- reading ---------------------------------------------------------
    def _field(self, key: str, fmt: str, model: int | None = None, pm=None):
        """A field is an offset from the model, or a pointer path [o1, o2, ..., final]:
        read pointer at model+o1, then pointer at that+o2, ..., then the value at last+final."""
        path = self.anchors.get("fields", {}).get(key)
        if model is None:
            model = self.model
        if path is None or model is None:
            return None
        if isinstance(path, int):
            path = [path]
        try:
            pm = pm or self.pm
            addr = model
            for off in path[:-1]:
                addr = pm.read_ulonglong(addr + off)
                if addr < 0x10000:
                    return None
            raw = pm.read_bytes(addr + path[-1], struct.calcsize(fmt))
        except Exception:
            return None
        return struct.unpack(fmt, raw)[0]

    def _treasury(self):
        """Treasury = int at player faction + 0xD58 (faction 'treasury' Lua binding, 9.0.4)."""
        try:
            from .world import World, find_player_faction
            F = find_player_faction(World(self))
            if F:
                return struct.unpack("<i", self.pm.read_bytes(F + 0xD58, 4))[0]
        except Exception:
            pass
        return None

    def read(self) -> State:
        """Never raises: with no game or no campaign it returns ok=False."""
        s = State(source=self.name)
        try:
            model = self.locate()
        except Exception:
            model = None
        if model is None:
            s.extras["attached"] = self.pid is not None
            return s
        s.turn = self._field("turn", "<i", model)
        check = self._field("turn_plus_one", "<i", model)
        if s.turn is not None and check is not None and check != s.turn + 1:
            s.extras["turn_mismatch"] = check
        s.treasury = self._treasury()
        s.income = None          # projected income is computed by the game, not stored
        s.ok = s.turn is not None
        s.extras["model"] = hex(model)
        s.extras["pid"] = self.pid
        return s
