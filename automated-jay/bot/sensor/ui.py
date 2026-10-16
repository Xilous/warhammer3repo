"""The game's UI tree, read from memory: find any component by id and read its screen rectangle.

Layout from the UIComponent Lua bindings (decompiled, 9.0.4):
    C + 0x1CC   u32  child count            C + 0x1D0  ptr  child array (entry = component)
    C + 0x2A0   ptr  id string object       C + 0x2E8  ptr  parent (0 at the root)
    C + 0x2C0   f32  x  (screen px)         C + 0x2C4  f32  y
    C + 0x2F0   ptr  current state object: +0x11C / +0x120 f32 width / height (1.0 when unset),
                     +0x18 string object: the state name ("active", "inactive", "hover", "down", "selected", ...),
                     [+0x138] wide string object: the text shown (UI.text)
    C + 0x1D8   u32  state count            C + 0x1E0  ptr  state array (entry = state object, name at +0x18)
    C + 0x334   u32  ms time stamp written twice per rendered frame (tools/wait.py next_frame)
    C + 0x353   u8   visible
Hovering a component swaps its state object (C + 0x2F0) for one of its hover states ("hover", "selected_hover",
"complete_hover", ...) within 0.5-1.5 frames of the cursor arriving (measured 2026-10-16). A click is only taken
once that happened, so tools/ui.py waits for it (hover_probe / hover_states) instead of a fixed delay.

Fast reads (2026-10-16): every field a lookup needs is in C + 0x1C8 .. C + 0x358, so a node costs one read_bytes
of that span plus one read of its child array. Ids are cached by (component, id string object); a cached id is
re-read before a lookup returns it, so a stale entry can never produce a wrong match. Lookups start from the
narrowest place known: a root child (popups and panels are root children), a component pointer (`under=ptr`),
or the root. `first()` is the one lookup every step uses. `cached()` re-uses a pointer found before after
checking its id, parent and effective visibility (own visible byte and every ancestor's, still attached).

Visibility trap (kept on purpose): list items scrolled outside their list_clip still read visible, at off-screen
coordinates. `first()` returns them like the game reports them; callers check `in_clip()` before clicking.

The root is re-read through a static pointer on every lookup (the front end and each loaded campaign build their
own tree), and every cache is dropped whenever the sensor re-attaches to a restarted game or sees a new campaign
model (MemorySensor.epoch) or the root moves. The string-scan bootstrap reads the heap, so it runs at most every
BOOTSTRAP_MIN_INTERVAL seconds.
"""
from __future__ import annotations
import ctypes
import ctypes.wintypes as wt
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

# one read covers every field a lookup needs
_BASE, _SPAN = 0x1C8, 0x190
O_NCH, O_ARR, O_ID = 0x1CC - _BASE, 0x1D0 - _BASE, 0x2A0 - _BASE
O_NST, O_STA = 0x1D8 - _BASE, 0x1E0 - _BASE
O_XY, O_PAR, O_ST = 0x2C0 - _BASE, 0x2E8 - _BASE, 0x2F0 - _BASE
O_STAMP, O_VIS = 0x334 - _BASE, 0x353 - _BASE
_u32 = struct.Struct("<I").unpack_from
_u64 = struct.Struct("<Q").unpack_from
_xy = struct.Struct("<2f").unpack_from
ID_CACHE_MAX = 200_000

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_RPM = _k32.ReadProcessMemory
_RPM.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_RPM.restype = wt.BOOL
_buf = ctypes.create_string_buffer


def reader(pm):
    """read_bytes(addr, n) straight through ReadProcessMemory (about 2 us against pymem's 3.5 us per call).
    Raises pymem's MemoryReadError like pm.read_bytes."""
    h = pm.process_handle

    def rb(addr: int, n: int) -> bytes:
        b = _buf(n)
        if not _RPM(h, addr, b, n, None):
            raise pymem.exception.MemoryReadError(addr, n, ctypes.get_last_error())
        return b.raw
    return rb


class _Stats:
    """Tree-walk counters for tools/timing.py: walks started, nodes visited, ms spent inside walks."""
    __slots__ = ("walks", "nodes", "ms")

    def __init__(self) -> None:
        self.walks = self.nodes = 0
        self.ms = 0.0

    def snapshot(self) -> tuple:
        return self.walks, self.nodes, self.ms

    def since(self, snap: tuple) -> dict:
        return {"walks": self.walks - snap[0], "nodes": self.nodes - snap[1], "ms": self.ms - snap[2]}


STATS = _Stats()


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
        self._ids: dict[tuple[int, int], str] = {}      # (component, id string object) -> id
        self._ptrs: dict[tuple, tuple[int, int, int]] = {}  # cached() key -> (ptr, id object, parent)
        self._cache_root = 0
        self._rb_pm = self._rb = None
        self._hover: dict[tuple[int, int], frozenset] = {}   # (component, state array) -> hover state objects

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

    @property
    def rb(self):
        """Fast read_bytes for the current process handle."""
        pm = self.pm
        if self._rb_pm is not pm:
            self._rb_pm, self._rb = pm, reader(pm)
        return self._rb

    def raw(self, c: int) -> bytes:
        """C + 0x1C8 .. C + 0x358 in one read (offsets O_*)."""
        return self.rb(c + _BASE, _SPAN)

    def _id_raw(self, c: int, raw: bytes) -> str | None:
        idp = _u64(raw, O_ID)[0]
        k = (c, idp)
        cid = self._ids.get(k)
        if cid is None:
            try:
                cid = string_object(self.pm, idp)
            except Exception:
                cid = None
            if cid is None:
                return None
            if len(self._ids) > ID_CACHE_MAX:
                self._ids.clear()
            self._ids[k] = cid
        return cid

    def _id_fresh(self, c: int, raw: bytes) -> str | None:
        """The id read from memory now (refreshing the cache entry)."""
        idp = _u64(raw, O_ID)[0]
        try:
            cid = string_object(self.pm, idp)
        except Exception:
            cid = None
        if cid is not None:
            self._ids[(c, idp)] = cid
        else:
            self._ids.pop((c, idp), None)
        return cid

    def _comp_raw(self, c: int, raw: bytes, cid: str | None = None) -> Comp:
        x, y = _xy(raw, O_XY)
        st = _u64(raw, O_ST)[0]
        w, h = struct.unpack("<2f", self.rb(st + 0x11C, 8)) if st else (1.0, 1.0)
        if cid is None:
            cid = self._id_raw(c, raw)
        return Comp(c, cid or "", x, y, w, h, raw[O_VIS] != 0)

    def comp(self, c: int) -> Comp:
        return self._comp_raw(c, self.raw(c))

    def id(self, c: int) -> str | None:
        try:
            return self._id_raw(c, self.raw(c))
        except Exception:
            return None

    def parent(self, c: int) -> int:
        return self.q(c + 0x2E8)

    def _kids(self, raw: bytes) -> tuple[int, ...]:
        n = _u32(raw, O_NCH)[0]
        if not 0 < n < 5000:
            return ()
        try:
            return struct.unpack(f"<{n}Q", self.rb(_u64(raw, O_ARR)[0], 8 * n))
        except pymem.exception.MemoryReadError:      # a component being torn down: no children left
            return ()

    def children(self, c: int) -> list[int]:
        return list(self._kids(self.raw(c)))

    def state(self, c: int) -> str | None:
        """The component's current state name ("active", "inactive", "hover", "down", "selected", ...)."""
        try:
            st = self.q(c + 0x2F0)
            return string_object(self.pm, st + 0x18) if st else None
        except Exception:
            return None

    def state_ptr(self, c: int) -> int:
        """The current state object (changes on hover / press / select: one 8-byte read)."""
        return self.q(c + 0x2F0)

    def states(self, c: int) -> list[tuple[int, str]]:
        """Every state the component can be in: (state object, name)."""
        raw = self.raw(c)
        n = _u32(raw, O_NST)[0]
        if not 0 < n < 64:
            return []
        out = []
        for p in struct.unpack(f"<{n}Q", self.rb(_u64(raw, O_STA)[0], 8 * n)):
            try:
                out.append((p, string_object(self.pm, p + 0x18) or ""))
            except Exception:
                continue
        return out

    def hover_states(self, c: int) -> frozenset:
        """The component's state objects whose name says hover (empty when it has none). Cached per state array."""
        try:
            raw = self.raw(c)
        except Exception:
            return frozenset()
        k = (c, _u64(raw, O_STA)[0])
        hs = self._hover.get(k)
        if hs is None:
            try:
                hs = frozenset(p for p, name in self.states(c) if "hover" in name)
            except Exception:
                hs = frozenset()
            if len(self._hover) > 20_000:
                self._hover.clear()
            self._hover[k] = hs
        return hs

    def hover_probe(self, c: int, at: tuple[int, int] | None = None, depth: int = 4) -> tuple[int, frozenset] | None:
        """(component, its hover states) that tells when the game has registered the cursor over c: c itself when it
        has hover states, else the first visible descendant (up to `depth` levels) that has them and contains `at`
        (default: c's centre). None when there is none (then only time can tell)."""
        hs = self.hover_states(c)
        if hs:
            return c, hs
        if at is None:
            at = self.comp(c).center
        stack = [(k, 1) for k in reversed(self.children(c))]
        while stack:
            k, d = stack.pop()
            try:
                raw = self.raw(k)
            except Exception:
                continue
            if raw[O_VIS] == 0:
                continue
            kc = self._comp_raw(k, raw, "")
            if kc.x <= at[0] <= kc.x + kc.w and kc.y <= at[1] <= kc.y + kc.h:
                hs = self.hover_states(k)
                if hs:
                    return k, hs
            if d < depth:
                stack.extend((g, d + 1) for g in reversed(self._kids(raw)))
        return None

    def visible(self, c: int) -> bool:
        try:
            return self.pm.read_bytes(c + 0x353, 1)[0] != 0
        except Exception:
            return False

    def text(self, c: int) -> str | None:
        """The text a text component shows: wide string object at [[C + 0x2F0] + 0x138] (vtable, u32 length +8,
        wchar* +0x10; short strings inline from +8 with 0x80|length in the byte at +0x17)."""
        try:
            st = self.q(c + 0x2F0)
            o = self.q(st + 0x138) if st else 0
            if not o:
                return None
            raw = self.pm.read_bytes(o + 8, 16)
            flag = raw[15]
            if flag >> 4 == 8:
                n = flag & 0x0F
                return raw[:2 * n].decode("utf-16-le", "replace")
            n = _u32(raw, 0)[0]
            p = _u64(raw, 8)[0]
            if not 0 <= n < 4096 or not p:
                return None
            return self.pm.read_bytes(p, 2 * n).decode("utf-16-le", "replace") if n else ""
        except Exception:
            return None

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
            raw = self.raw(r)
            return bool(r) and _u64(raw, O_PAR)[0] == 0 and 0 < _u32(raw, O_NCH)[0] < 5000
        except Exception:
            return False

    def _check_caches(self, r: int | None) -> None:
        if r != self._cache_root:
            self._cache_root = r or 0
            self._ids.clear()
            self._ptrs.clear()
            self._hover.clear()

    def find_root(self) -> int | None:
        """The UI root, re-resolved on every call: static pointer first, then the root found before (only while
        the sensor's epoch is unchanged), then a rate-limited heap bootstrap. None when the game is not running."""
        if not self.s.attached:
            self._root = None
            self._check_caches(None)
            return None
        if self._epoch != self.s.epoch:          # re-attached or another campaign: nothing found before is valid
            self._epoch = self.s.epoch
            self._root = None
            self._next_bootstrap = 0.0
            self._root_off = _anchors().get("ui_root_ptr")
            self._check_caches(None)
        off = self._root_off
        if off is not None:
            try:
                r = self.q(self.s.base + off)
                if self._is_root(r):
                    self._root = r
                    self._check_caches(r)
                    return r
            except Exception:
                pass
        if self._root is not None and self._is_root(self._root):
            return self._root
        self._root = None
        self._check_caches(None)
        if time.monotonic() < self._next_bootstrap:
            return None
        self._next_bootstrap = time.monotonic() + BOOTSTRAP_MIN_INTERVAL
        r = self._bootstrap()
        self._check_caches(r)
        return r

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
            self._cache_root_ptr(c)
            return c
        return None

    def _cache_root_ptr(self, root: int) -> None:
        ptrs = memscan.scan_pointers_in_module(self.pm, self.s.base, self.s.size, root, root)
        if not ptrs:
            return
        a = _anchors()
        a["ui_root_ptr"] = self._root_off = ptrs[0][0] - self.s.base
        tmp = config.ANCHORS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(a, indent=2))
        tmp.replace(config.ANCHORS_FILE)

    # ---------------------------------------------------------------- walking
    def nodes(self, start: int | None = None, visible_only: bool = True, max_nodes: int = 200_000, skip=()):
        """Depth-first over the tree (children in order), yielding (ptr, id, raw) without building paths.
        `skip`: ids whose subtrees are not entered (the node itself is still yielded)."""
        t = time.perf_counter()
        start = start or self.find_root()
        if not start:
            return
        STATS.walks += 1
        rb = self.rb
        stack = [start]
        n = 0
        try:
            while stack and n < max_nodes:
                c = stack.pop()
                n += 1
                try:
                    raw = rb(c + _BASE, _SPAN)
                except pymem.exception.MemoryReadError:
                    continue
                if visible_only and raw[O_VIS] == 0:
                    continue
                cid = self._id_raw(c, raw) or "?"
                STATS.ms += (time.perf_counter() - t) * 1000
                yield c, cid, raw
                t = time.perf_counter()
                if cid in skip:
                    continue
                nch = _u32(raw, O_NCH)[0]
                if 0 < nch < 5000:
                    try:
                        kids = struct.unpack(f"<{nch}Q", rb(_u64(raw, O_ARR)[0], 8 * nch))
                    except pymem.exception.MemoryReadError:
                        continue
                    stack.extend(reversed(kids))
        finally:
            STATS.nodes += n
            STATS.ms += (time.perf_counter() - t) * 1000

    def walk(self, start: int | None = None, visible_only: bool = True, max_nodes: int = 200_000):
        """Depth-first over the tree, yielding (component ptr, path of ids). Nothing when there is no root.
        Prefer first() / nodes(): building the paths costs more than the reads."""
        t = time.perf_counter()
        start = start or self.find_root()
        if not start:
            return
        STATS.walks += 1
        rb = self.rb
        stack = [(start, ())]
        n = 0
        try:
            while stack and n < max_nodes:
                c, path = stack.pop()
                n += 1
                try:
                    raw = rb(c + _BASE, _SPAN)
                    if visible_only and raw[O_VIS] == 0:
                        continue
                    cid = self._id_raw(c, raw) or "?"
                    p = path + (cid,)
                    STATS.ms += (time.perf_counter() - t) * 1000
                    yield c, p
                    t = time.perf_counter()
                    for ch in reversed(self._kids(raw)):
                        stack.append((ch, p))
                except pymem.exception.MemoryReadError:
                    continue
        finally:
            STATS.nodes += n
            STATS.ms += (time.perf_counter() - t) * 1000

    # ---------------------------------------------------------------- lookups
    def root_children(self) -> list[tuple[int, str]]:
        """(ptr, id) of the visible children of the root, in order. One array read plus one read per child."""
        r = self.find_root()
        if not r:
            return []
        out = []
        rb = self.rb
        try:
            kids = self._kids(self.raw(r))
        except Exception:
            return []
        for c in kids:
            try:
                raw = rb(c + _BASE, _SPAN)
            except Exception:
                continue
            if raw[O_VIS]:
                out.append((c, self._id_raw(c, raw) or "?"))
        return out

    def root_child(self, cid: str) -> int | None:
        """The visible root child with this id (panels and popups live here), or None."""
        for c, i in self.root_children():
            if i == cid:
                return c
        return None

    def first(self, cid: str, under: str | int | None = None, start: int | None = None,
              skip=("3d_ui_parent",)) -> int | None:
        """The first visible component with id `cid` in depth-first order, or None.
          under  an id that must be among its ancestors (the search starts at that component when it is a root
                 child), or a component pointer to search below
          start  where the walk starts (default: the root)
          skip   ids whose subtrees are not searched: by default the map labels under 3d_ui_parent (hundreds of
                 nodes), unless cid is a map label ("label_...")
        A root child with that id is found without a walk. The match's id is re-read before it is returned."""
        if isinstance(under, int):
            start, under = under, None
        if cid.startswith("label_") or under == "3d_ui_parent":
            skip = ()
        if start is None:
            rc = self.root_children()
            if under is None:
                for c, i in rc:
                    if i == cid:
                        return c
            else:
                for c, i in rc:
                    if i == under:
                        start, under = c, None
                        break
        if under is None:
            for c, i, raw in self.nodes(start, skip=skip):
                if i == cid and c != start and self._id_fresh(c, raw) == cid:
                    return c
            return None
        # ids along the path: track whether an ancestor is `under`
        for c in self._first_under(cid, under, start, skip):
            return c
        return None

    def _first_under(self, cid: str, under: str, start: int | None, skip):
        start = start or self.find_root()
        if not start:
            return
        t = time.perf_counter()
        STATS.walks += 1
        rb = self.rb
        stack = [(start, False)]
        n = 0
        try:
            while stack:
                c, inside = stack.pop()
                n += 1
                try:
                    raw = rb(c + _BASE, _SPAN)
                except pymem.exception.MemoryReadError:
                    continue
                if raw[O_VIS] == 0:
                    continue
                i = self._id_raw(c, raw) or "?"
                if inside and i == cid and self._id_fresh(c, raw) == cid:
                    STATS.ms += (time.perf_counter() - t) * 1000
                    yield c
                    t = time.perf_counter()
                    continue
                if i in skip:
                    continue
                nch = _u32(raw, O_NCH)[0]
                if 0 < nch < 5000:
                    try:
                        kids = struct.unpack(f"<{nch}Q", rb(_u64(raw, O_ARR)[0], 8 * nch))
                    except pymem.exception.MemoryReadError:
                        continue
                    inner = inside or i == under
                    stack.extend((k, inner) for k in reversed(kids))
        finally:
            STATS.nodes += n
            STATS.ms += (time.perf_counter() - t) * 1000

    def all(self, cid: str, under: str | int | None = None, start: int | None = None) -> list[int]:
        """Every visible component with this id (same scoping as first())."""
        if isinstance(under, int):
            start, under = under, None
        if under is not None:
            return list(self._first_under(cid, under, start, ()))
        return [c for c, i, _r in self.nodes(start) if i == cid and c != start]

    def child(self, c: int, cid: str, visible_only: bool = False) -> int | None:
        """The direct child of c with this id."""
        rb = self.rb
        for k in self.children(c):
            try:
                raw = rb(k + _BASE, _SPAN)
            except Exception:
                continue
            if (not visible_only or raw[O_VIS]) and self._id_raw(k, raw) == cid:
                return k
        return None

    def index(self, start: int | None = None, skip=("3d_ui_parent",)) -> dict[str, list[int]]:
        """{id: [ptr, ...]} of every visible component below start, from one walk. Stale after any input."""
        out: dict[str, list[int]] = {}
        for c, i, _r in self.nodes(start, skip=skip):
            out.setdefault(i, []).append(c)
        return out

    def cached(self, cid: str, under: str | int | None = None, start: int | None = None) -> int | None:
        """first(cid, under, start), re-using the pointer found last time when it still has the same id string
        object, the same parent and is effectively visible (own and every ancestor's visible byte, attached all the
        way up to the current root). Only for ids that are unique on screen (a cached pointer can be a different,
        equally valid match than the first in walk order)."""
        key = (cid, under, start)
        e = self._ptrs.get(key)
        if e is not None:
            ptr, idp, par = e
            try:
                raw = self.raw(ptr)
                if (_u64(raw, O_ID)[0] == idp and _u64(raw, O_PAR)[0] == par and self.effective_visible(ptr, raw)
                        and self._id_fresh(ptr, raw) == cid):
                    return ptr
            except Exception:
                pass
            del self._ptrs[key]
        c = self.first(cid, under=under, start=start)
        if c is not None:
            raw = self.raw(c)
            self._ptrs[key] = (c, _u64(raw, O_ID)[0], _u64(raw, O_PAR)[0])
        return c

    def effective_visible(self, c: int, raw: bytes | None = None) -> bool:
        """Its own visible byte and every ancestor's, each still in its parent's child array, up to the current
        root. False for a hidden, detached or freed component."""
        try:
            r = self.find_root()
            seen = 0
            raw = raw or self.raw(c)
            while seen < 64:
                if raw[O_VIS] == 0:
                    return False
                p = _u64(raw, O_PAR)[0]
                if not p:
                    return c == r
                praw = self.raw(p)
                if c not in self._kids(praw):
                    return False
                c, raw = p, praw
                seen += 1
            return False
        except Exception:
            return False

    def clip_of(self, c: int) -> int | None:
        """The nearest ancestor list_clip (the window a scrolling list is seen through), or None."""
        try:
            p = self.parent(c)
            for _ in range(32):
                if not p:
                    return None
                if self.id(p) == "list_clip":
                    return p
                p = self.parent(p)
        except Exception:
            return None
        return None

    def in_clip(self, c: int, margin: float = 0.0) -> bool:
        """The component lies inside its list's clip window (True when it is not in a list). List items scrolled
        out of view still read visible, at off-screen coordinates: check this before clicking a list item."""
        clip = self.clip_of(c)
        if clip is None:
            return True
        k, cl = self.comp(c), self.comp(clip)
        return (cl.x + margin <= k.x and k.x + k.w <= cl.x + cl.w - margin
                and cl.y + margin <= k.y and k.y + k.h <= cl.y + cl.h - margin)

    def frame_stamp(self) -> int | None:
        """The root's per-frame ms stamp (changes once per UI frame)."""
        r = self.find_root()
        return _u32(self.pm.read_bytes(r + 0x334, 4), 0)[0] if r else None

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
