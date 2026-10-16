"""The game's UI tree, read from memory: find any component by id and read its screen rectangle.

Layout from the UIComponent Lua bindings (decompiled, 9.0.4):
    C + 0x1CC   u32  child count            C + 0x1D0  ptr  child array (entry = component)
    C + 0x2A0   ptr  id string object       C + 0x2E8  ptr  parent (0 at the root)
    C + 0x2C0   f32  x  (screen px)         C + 0x2C4  f32  y
    [C + 0x2F0] + 0x11C / 0x120  f32 width / height (1.0 when unset)
    C + 0x353   u8   visible
    [C + 0x2F0] + 0x18  string object: the current state name ("active", "inactive", "hover", ...)
The root is found once by walking up from any component; a static pointer to it is then cached in
anchors.json (ui_root_ptr) when one exists.

The root is re-read through that static pointer on every lookup (the front end and each loaded campaign
build their own tree), and a cached root is dropped whenever the sensor re-attaches to a restarted game or
sees a new campaign model (MemorySensor.epoch). The string-scan bootstrap reads the heap, so it runs at most
every BOOTSTRAP_MIN_INTERVAL seconds.
"""
from __future__ import annotations
import json
import re
import struct
import time
from dataclasses import dataclass

import pymem

from .. import config
from . import memscan
from .memory import MemorySensor
from .world import string_object

BOOTSTRAP_MIN_INTERVAL = 30.0


def _anchors() -> dict:
    try:
        return json.loads(config.ANCHORS_FILE.read_text())
    except (OSError, ValueError):
        return {}


@dataclass
class Comp:
    ptr: int
    id: str
    x: float
    y: float
    w: float
    h: float
    visible: bool

    @property
    def center(self) -> tuple[int, int]:
        return int(self.x + self.w / 2), int(self.y + self.h / 2)


class UI:
    def __init__(self, s: MemorySensor | None = None) -> None:
        self.s = s or MemorySensor()
        self._root: int | None = None
        self._root_off: int | None = None
        self._epoch = None
        self._next_bootstrap = 0.0

    @property
    def pm(self):
        """Always the sensor's current process handle (it changes when the game is restarted)."""
        return self.s.pm

    @property
    def root(self) -> int | None:
        return self.find_root()

    # ---------------------------------------------------------------- raw fields
    def q(self, a: int) -> int:
        return self.pm.read_ulonglong(a)

    def comp(self, c: int) -> Comp:
        x, y = struct.unpack("<2f", self.pm.read_bytes(c + 0x2C0, 8))
        dims = self.q(c + 0x2F0)
        w, h = struct.unpack("<2f", self.pm.read_bytes(dims + 0x11C, 8)) if dims else (1.0, 1.0)
        vis = self.pm.read_bytes(c + 0x353, 1)[0] != 0
        return Comp(c, self.id(c) or "", x, y, w, h, vis)

    def id(self, c: int) -> str | None:
        try:
            return string_object(self.pm, self.q(c + 0x2A0))
        except Exception:
            return None

    def parent(self, c: int) -> int:
        return self.q(c + 0x2E8)

    def children(self, c: int) -> list[int]:
        n = struct.unpack("<I", self.pm.read_bytes(c + 0x1CC, 4))[0]
        if not 0 < n < 5000:
            return []
        arr = self.q(c + 0x1D0)
        return list(struct.unpack(f"<{n}Q", self.pm.read_bytes(arr, 8 * n)))

    def state(self, c: int) -> str | None:
        """The component's current state name ("active", "inactive", "hover", ...)."""
        try:
            st = self.q(c + 0x2F0)
            return string_object(self.pm, st + 0x18) if st else None
        except Exception:
            return None

    def visible(self, c: int) -> bool:
        try:
            return self.pm.read_bytes(c + 0x353, 1)[0] != 0
        except Exception:
            return False

    def looks_like_component(self, c: int) -> bool:
        try:
            p = self.parent(c)
            if p and c not in self.children(p):
                return False
            return self.id(c) is not None
        except Exception:
            return False

    # ---------------------------------------------------------------- finding the root
    def _is_root(self, r: int) -> bool:
        try:
            return bool(r) and self.parent(r) == 0 and bool(self.children(r))
        except Exception:
            return False

    def find_root(self) -> int | None:
        """The UI root, re-resolved on every call: static pointer first, then the root found before (only while
        the sensor's epoch is unchanged), then a rate-limited heap bootstrap. None when the game is not running."""
        if not self.s.attached:
            self._root = None
            return None
        if self._epoch != self.s.epoch:          # re-attached or another campaign: nothing found before is valid
            self._epoch = self.s.epoch
            self._root = None
            self._next_bootstrap = 0.0
            self._root_off = _anchors().get("ui_root_ptr")
        off = self._root_off
        if off is not None:
            try:
                r = self.q(self.s.base + off)
                if self._is_root(r):
                    self._root = r
                    return r
            except Exception:
                pass
        if self._root is not None and self._is_root(self._root):
            return self._root
        self._root = None
        if time.monotonic() < self._next_bootstrap:
            return None
        self._next_bootstrap = time.monotonic() + BOOTSTRAP_MIN_INTERVAL
        return self._bootstrap()

    def _bootstrap(self) -> int | None:
        # debug strings "CcoComponent<id>(0x<address>)" name live components
        for hit in memscan.scan_bytes(self.pm, b"CcoComponent", private_only=True, limit=200):
            try:
                raw = self.pm.read_bytes(hit, 160)
            except Exception:
                continue
            m = re.match(rb"CcoComponent[^\(\x00]*\(0x([0-9a-fA-F]{8,16})\)", raw)
            if not m:
                continue
            c = int(m.group(1), 16)
            if not self.looks_like_component(c):
                continue
            seen = 0
            while self.parent(c) and seen < 200:
                c = self.parent(c)
                seen += 1
            self._root = c
            self._cache_root(c)
            return c
        return None

    def _cache_root(self, root: int) -> None:
        ptrs = memscan.scan_pointers_in_module(self.pm, self.s.base, self.s.size, root, root)
        if not ptrs:
            return
        a = _anchors()
        a["ui_root_ptr"] = self._root_off = ptrs[0][0] - self.s.base
        tmp = config.ANCHORS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(a, indent=2))
        tmp.replace(config.ANCHORS_FILE)

    # ---------------------------------------------------------------- queries
    def walk(self, start: int | None = None, visible_only: bool = True, max_nodes: int = 200_000):
        """Depth-first over the tree, yielding (component ptr, path of ids). Nothing when there is no root."""
        start = start or self.find_root()
        if not start:
            return
        stack = [(start, ())]
        n = 0
        while stack and n < max_nodes:
            c, path = stack.pop()
            n += 1
            try:
                if visible_only and self.pm.read_bytes(c + 0x353, 1)[0] == 0:
                    continue
                cid = self.id(c) or "?"
                yield c, path + (cid,)
                for ch in reversed(self.children(c)):
                    stack.append((ch, path + (cid,)))
            except pymem.exception.MemoryReadError:
                continue

    def find(self, *path: str, visible_only: bool = True) -> list[Comp]:
        """Components whose id is path[-1] and whose ancestors contain path[:-1] in order."""
        out = []
        for c, ids in self.walk(visible_only=visible_only):
            if ids[-1] != path[-1]:
                continue
            i = 0
            for anc in ids[:-1]:
                if i < len(path) - 1 and anc == path[i]:
                    i += 1
            if i == len(path) - 1:
                out.append(self.comp(c))
        return out
