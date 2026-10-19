"""The game's outgoing command stream: did a click become a game command? (player rule 2026-10-19: pacing,
detection and verification from memory, never from a timeout tuned per mode.)

Every campaign action (construct, cancel, research, recruit, a skill, abandon ...) is not applied by the click: the
UI posts a command, which the game applies when it is processed (in multiplayer only after the other players have
synced it, seconds later). Decoded on 9.0.4, 2026-10-19, from SETTLEMENT MarkForAbandon (FUN_141ff534c ->
FUN_141fc8570 -> FUN_141bca278 / FUN_141bcd5e4) and the construct sender FUN_14208d728, and checked live (a
construction started and cancelled, turn 12 of a single-player Clan Scruten save):

  G = [0x144480D38]                   the campaign game root (0 while no campaign is loaded)
  Q = [[G + 0x2F60] + 0x98]           the command writer (vtable 0x143A8F9F8, 0x5010 bytes)
  bytes Q+8 .. Q+8+cursor, cursor = u32 Q+0x5008: the commands written this frame
  one command: u16 length (header included, little-endian), u32 type id (big-endian; the id is a global per command
  type, e.g. construct building = [0x143F8A244] 0xBDF6E9EB, cancel construction = [0x143F8A254] 0x1A82B194), u8 flag
  (the registry entry's +0x10), then the command's own fields (construct: the slot id u32, a length-prefixed level
  key "wh2_main_skv_farm_1")

The stream is flushed within the frame (cursor back to 0 about 1 ms later), so Watch samples it from a thread for the
length of an action. What happens after the flush (the network / local apply) is not decoded: the effect itself is
read from the model by the caller (a slot under construction, the research, the points, the treasury).
"""
from __future__ import annotations
import struct
import threading
import time

GAME_ROOT = 0x144480D38
WRITER_OFF = (0x2F60, 0x98)
CURSOR_OFF = 0x5008
BUF_OFF = 8
BUF_MAX = 0x5000

MISS_GRACE_S = 2.5     # before a "missed" click is clicked again: this much longer for its effect (multiplayer: a
                       # command applied 0.4 s after it was written, 2026-10-19; a command the watch did not see while
                       # its effect is on the way must never be clicked a second time)
MISS_S = 0.6           # no command by then: the click did not reach the game (the command is written in the frame of
                       # the click, before any sync, in single player and multiplayer alike)
EFFECT_CAP_S = 15.0    # a command sent: wait this long at most for its effect (multiplayer sync measured at 1-3 s,
                       # 2026-10-18); the wait ends the moment memory shows it, so single player is not slowed


def writer(pm) -> int | None:
    """Q, the command writer, or None (no campaign loaded)."""
    q = lambda a: struct.unpack("<Q", pm.read_bytes(a, 8))[0]
    try:
        G = q(GAME_ROOT)
        if not G:
            return None
        A = q(G + WRITER_OFF[0])
        Q = q(A + WRITER_OFF[1]) if A else 0
        return Q or None
    except Exception:
        return None


def parse(buf: bytes) -> list[int]:
    """Type ids of the commands in a written stream."""
    out, off = [], 0
    while off + 7 <= len(buf):
        ln = struct.unpack_from("<H", buf, off)[0]
        if ln < 7 or off + ln > len(buf):
            break
        out.append(struct.unpack_from(">I", buf, off + 2)[0])
        off += ln
    return out


class Watch:
    """Records every command the game writes while it is active (a thread reading the stream continuously).
    with Watch(pm) as cw: click ...; cw.count, cw.types. cw.ok is False when the stream cannot be read (no
    campaign, or the layout moved): callers then must not take "no command" for a missed click."""

    def __init__(self, pm):
        self.pm = pm
        self.Q = writer(pm)
        self.ok = self.Q is not None
        self.types: list[int] = []
        self._stop = threading.Event()
        self._t = None
        self._head0 = self._head()

    def _head(self) -> bytes:
        """The stream's first bytes. A flush only resets the cursor: the bytes of the last command stay in the
        buffer, so a command written and flushed between two samples still shows as changed bytes."""
        try:
            return self.pm.read_bytes(self.Q + BUF_OFF, 64) if self.Q else b""
        except Exception:
            return b""

    @property
    def count(self) -> int:
        if not self.types and self.ok and self._head() != self._head0:
            self.types.append(-1)                  # written and flushed between two samples: type not seen
        return len(self.types)

    def _run(self) -> None:
        pm, Q, last = self.pm, self.Q, b""
        while not self._stop.is_set():
            try:
                cur = struct.unpack("<I", pm.read_bytes(Q + CURSOR_OFF, 4))[0]
                if 0 < cur <= BUF_MAX:
                    buf = pm.read_bytes(Q + BUF_OFF, cur)
                    if buf != last:
                        new = parse(buf)
                        old = parse(last) if last and buf.startswith(last) else []
                        self.types.extend(new[len(old):])
                        last = buf
                elif cur == 0:
                    last = b""
            except Exception:
                time.sleep(0.001)
            time.sleep(0)

    def __enter__(self) -> "Watch":
        if self.ok:
            self._t = threading.Thread(target=self._run, daemon=True, name="command-watch")
            self._t.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._t is not None:
            self._t.join(0.2)


def act(pm, do, done, cap: float = EFFECT_CAP_S, miss_s: float = MISS_S, poll: float = 0.005):
    """Run do() (one click) and wait for done() (the effect, read from memory). -> (status, value):
      ("done", value)    done() came true (its value)
      ("not clicked", None) do() returned False: it chose not to click (no hover, a card not shown)
      ("missed", None)   the game wrote no command within miss_s and nothing changed: the click did not reach the game,
                         clicking again is safe
      ("refused", None)  a command went out but its effect did not show within cap: the game did not apply it (never
                         click again: in multiplayer a second click can undo the first)
    When the stream cannot be read, a click without effect counts as "refused" after cap (never re-clicked)."""
    with Watch(pm) as cw:
        if do() is False:
            return "not clicked", None
        t0 = time.perf_counter()
        while True:
            try:
                v = done()
            except Exception:
                v = None
            if v:
                return "done", v
            el = time.perf_counter() - t0
            if cw.ok and cw.count == 0 and el > miss_s:
                return "missed", None
            if el > cap:
                return "refused", None
            time.sleep(poll)


def act_retry(pm, do, done, tries: int = 2, **kw):
    """act, clicked again only while the click "missed" (no command reached the game): never after a command, and
    only after MISS_GRACE_S more without the effect."""
    st, v = "missed", None
    for i in range(tries):
        st, v = act(pm, do, done, **kw)
        if st != "missed":
            break
        end = time.perf_counter() + MISS_GRACE_S
        while time.perf_counter() < end:           # a command the watch did not see: its effect still comes
            try:
                v = done()
            except Exception:
                v = None
            if v:
                return "done", v
            time.sleep(0.02)
    return st, v


WHY = {"missed": "the click did not reach the game (no command was written)",
       "refused": "the game took the order but memory never showed it applied",
       "not clicked": ""}
