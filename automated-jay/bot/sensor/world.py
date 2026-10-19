"""Read the campaign world from memory: the player's faction, its regions, every region's owner,
neighbours and building slots, and which factions the player is at war with.

Offsets were decoded from the game's Lua bindings (method name -> C function in the exe's binding
tables, decompiled with Ghidra) on 9.0.4, 2026-10-16. Script interfaces wrap the model object at +0x10.

faction F:  region count u32 F+0xF3C, array F+0xF40 (entry -> region*)
            relationship list [F+0xDB8]: count u32 +4, base +8, stride 0x78; other faction at +0x28;
                at war when int [[e+0x30]+0x20] == 0
            name: [[F+0xD88]+8] -> string object whose char* is at +8
region R:   DB record [R+0x80] (record +0x10 = char* key); owner [[R+0x120]+0x10];
            neighbours count u32 R+0x8C, array [R+0x90]; settlement [R+0x128];
            slots: L = [R+0x148]+0x10: count u32 L+4, array [L+8] of slot*
slot S:     type string at [S+0x188]+0x10 (string object); active byte S+0x1D8;
            slot-building record [S+0x190]: building [+0x20], construction [+0x10]
building B: level record [B+0x30]: key string object [+8]; level index u32 +0x1F0
"""
from __future__ import annotations
import struct
from dataclasses import dataclass, field

import pymem

from .memory import MemorySensor

STRING_VTABLE = 0x1433CE678


def _cstr(pm, addr: int, n: int = 128) -> str | None:
    try:
        b = pm.read_bytes(addr, n)
    except Exception:
        return None
    end = b.find(b"\0")
    if end <= 0:
        return None
    try:
        s = b[:end].decode("ascii")
    except UnicodeDecodeError:
        return None
    return s if s.isprintable() else None


def string_object(pm, obj: int) -> str | None:
    """Engine string object (decompiled accessor 0x1404D4BC0): if the top nibble of the qword at +8 is
    0x8 the text is stored inline at obj (short strings); otherwise +8 holds a char*.
    Falls back to the older guesses (+0x10, +0) for objects that carry a header."""
    try:
        head = pm.read_bytes(obj, 16)
        flag = struct.unpack_from("<Q", head, 8)[0]
        if (flag >> 60) == 0x8:
            raw = head[:15]
            end = raw.find(b"\0")
            txt = raw[:end if end >= 0 else 15]
            if txt and all(32 <= c < 127 for c in txt):
                return txt.decode()
    except Exception:
        pass
    for off in (8, 0x10, 0):
        try:
            p = pm.read_ulonglong(obj + off)
        except Exception:
            continue
        if 0x10000 < p < 0x7FF000000000:
            s = _cstr(pm, p)
            if s:
                return s
    return None


@dataclass
class Slot:
    type: str | None
    active: bool
    building: str | None        # building level key
    level: int | None
    constructing: bool


@dataclass
class Region:
    key: str
    owner: int | None
    neighbours: list[int]
    slots: list[Slot] = field(default_factory=list)


class World:
    def __init__(self, sensor: MemorySensor | None = None) -> None:
        self.s = sensor or MemorySensor()
        self._faction: int | None = None

    @property
    def pm(self):
        """Always the sensor's current process handle (it changes when the game is restarted)."""
        return self.s.pm

    # -------------------------------------------------------------- primitives
    def q(self, a: int) -> int:
        return self.pm.read_ulonglong(a)

    def u32(self, a: int) -> int:
        return struct.unpack("<I", self.pm.read_bytes(a, 4))[0]

    def faction_name(self, f: int) -> str | None:
        try:
            return string_object(self.pm, self.q(self.q(f + 0xD88) + 8) - 0) or _cstr(self.pm, self.q(self.q(self.q(f + 0xD88) + 8) + 8))
        except Exception:
            return None

    def faction_regions(self, f: int) -> list[int]:
        n = self.u32(f + 0xF3C)
        if not 0 <= n < 2000:
            return []
        arr = self.q(f + 0xF40)
        return [self.q(self.q(arr + 8 * i)) for i in range(n)]

    def wars(self, f: int) -> list[int]:
        rel = self.q(f + 0xDB8)
        if not rel:
            return []
        n = self.u32(rel + 4)
        base = self.q(rel + 8)
        out = []
        for i in range(min(n, 4000)):
            e = base + 0x78 * i
            try:
                if struct.unpack("<i", self.pm.read_bytes(self.q(e + 0x30) + 0x20, 4))[0] == 0:
                    out.append(self.q(e + 0x28))
            except pymem.exception.MemoryReadError:
                continue
        return out

    def met(self, f: int) -> set[int]:
        """Factions f has met (discovered): its relationship entry's byte +0x74 has bit 4 (decompiled
        FUN_14269c254, the check behind the Cco DiscoveredProvinceList, 9.0.4, 2026-10-18; 27 of 559 live, the
        player's neighbours). Unmet factions' lands are mostly under the shroud."""
        rel = self.q(f + 0xDB8)
        if not rel:
            return set()
        n, base = self.u32(rel + 4), self.q(rel + 8)
        out = set()
        for i in range(min(n, 4000)):
            e = base + 0x78 * i
            try:
                if self.pm.read_bytes(e + 0x74, 1)[0] & 4:
                    out.add(self.q(e + 0x28))
            except pymem.exception.MemoryReadError:
                continue
        return out

    # ---- the shroud: is a settlement explored? (decompiled 9.0.4, 2026-10-18: the check behind Cco IsShrouded and
    # the Masterplans region eligibility, FUN_1426CA9E0 -> FUN_142808AF8 -> FUN_141436C20)
    #   shroud Z = [F+0xEC0] (none: everything shown); Z+0xD0 byte 0: no shroud at all
    #   settlement S = [R+0x128]: map grid cell u16 x, u16 y at S+0x340
    #   grid descriptor D = [[[[[Z+0xC8]+0x6C98]]+0x28]]+0x68: u16 W, H; floats: x0 +4, y0 +8, odd-column y shift
    #     +0x18, row height +0x1C, column width +0x24 -> world (wx, wy)
    #   cell grid G = [[Z+0xC8]+0x6C98]: floats x0 +0x64, y0 +0x68, x1 +0x6C, y1 +0x70; u32 cells nx +0x74, ny +0x78
    #   bitmaps (quadtrees): explored at Z+0x20, hidden-again at Z+0x60: u32 width, height, span; root node at +0x10
    #     {u32 bits[2]; node* children}; children (4 x 0x10): +0 x<half y>=half, +0x10 x>=half y>=half,
    #     +0x20 x<half y<half, +0x30 x>=half y<half; a leaf maps its span onto 8 x 8 bits (bit x + 8y)
    #   shown = explored and not hidden-again
    def _qbit(self, B: int, x: int, y: int) -> bool:
        w, h, span = struct.unpack("<3I", self.pm.read_bytes(B, 12))
        if x >= w or y >= h:
            return False
        node = B + 0x10
        for _ in range(32):
            kids = self.q(node + 8)
            half = span >> 1
            if not kids:
                if span != 8 and span:
                    fx, fy = x / span * 8, y / span * 8
                    x = min(7, int(fx)) if fx > 0 else 0
                    y = min(7, int(fy)) if fy > 0 else 0
                bit = x + y * 8
                word = self.u32(node + (0 if y < 4 else 4))
                return bool(word & (1 << (bit & 31)))
            if x < half:
                node = kids + 0x20 if y < half else kids
            else:
                x -= half
                node = kids + 0x30 if y < half else kids + 0x10
            if y >= half:
                y -= half
            span = half
        return False

    def explored(self, f: int, r: int) -> bool:
        """The region's settlement is not under f's shroud (see above). True when it cannot be read."""
        try:
            Z = self.q(f + 0xEC0)
            if not Z or self.pm.read_bytes(Z + 0xD0, 1)[0] == 0:
                return True
            S = self.q(r + 0x128)
            if not S:
                return True
            gx, gy = struct.unpack("<2H", self.pm.read_bytes(S + 0x340, 4))
            M = self.q(Z + 0xC8)
            D = self.q(self.q(self.q(self.q(M + 0x6C98)) + 0x28)) + 0x68
            W, H = struct.unpack("<2H", self.pm.read_bytes(D, 4))
            gx, gy = min(gx, W - 1), min(gy, H - 1)
            fl = lambda o: struct.unpack("<f", self.pm.read_bytes(D + o, 4))[0]
            wy = gy * fl(0x1C) + (fl(0x18) if gx & 1 else 0.0) + fl(0x08)
            wx = gx * fl(0x24) + fl(0x04)
            G = self.q(M + 0x6C98)
            g = lambda o: struct.unpack("<f", self.pm.read_bytes(G + o, 4))[0]
            nx, ny = self.u32(G + 0x74), self.u32(G + 0x78)
            cx = int((wx - g(0x64)) * nx / (g(0x6C) - g(0x64)))
            cy = int((wy - g(0x68)) * ny / (g(0x70) - g(0x68)))
            return self._qbit(Z + 0x20, cx, cy) and not self._qbit(Z + 0x60, cx, cy)
        except Exception:
            return True

    def region_key(self, r: int) -> str | None:
        try:
            return _cstr(self.pm, self.q(self.q(r + 0x80) + 0x10))
        except Exception:
            return None

    def region_owner(self, r: int) -> int | None:
        o = self.q(r + 0x120)
        return self.q(o + 0x10) if o else None

    def neighbours(self, r: int) -> list[int]:
        n = self.u32(r + 0x8C)
        if not 0 < n < 64:
            return []
        arr = self.q(r + 0x90)
        return list(struct.unpack(f"<{n}Q", self.pm.read_bytes(arr, 8 * n)))

    def slots(self, r: int) -> list[Slot]:
        lst = self.q(r + 0x148)
        if not lst:
            return []
        L = lst + 0x10
        n = self.u32(L + 4)
        if not 0 < n < 32:
            return []
        arr = self.q(L + 8)
        out = []
        for i in range(n):
            s = self.q(arr + 8 * i)
            try:
                stype = string_object(self.pm, self.q(s + 0x188) + 0x10)
            except Exception:
                stype = None
            active = self.pm.read_bytes(s + 0x1D8, 1)[0] != 0
            sb = self.q(s + 0x190)
            b = self.q(sb + 0x20) if sb else 0
            con = bool(self.q(sb + 0x10)) if sb else False
            key = lvl = None
            if b:
                rec = self.q(b + 0x30)
                if rec:
                    key = string_object(self.pm, self.q(rec + 8)) or string_object(self.pm, rec + 8)
                    lvl = self.u32(rec + 0x1F0)
            out.append(Slot(stype, active, key, lvl, con))
        return out

    # -------------------------------------------------------------- whole-world view
    def region(self, r: int, with_slots: bool = False) -> Region:
        reg = Region(self.region_key(r) or hex(r), self.region_owner(r), self.neighbours(r))
        if with_slots:
            reg.slots = self.slots(r)
        return reg


# ------------------------------------------------------------------ player faction + frontline
import json as _json
import re as _re
from functools import lru_cache as _lru_cache

from .. import config as _config


def _anchors() -> dict:
    return _json.load(open(_config.ANCHORS_FILE))


HUMAN = 0x1BC4                    # faction:is_human(): byte < 2 (the Lua binding 0x1427d10e4 tests it, 9.0.4)
DEFAULT_FACTION = "wh2_main_skv_clan_skryre"
PLAYER = {"key": None}            # the player's faction key, as last found (modules that need it: current_faction())
_found: dict = {}                 # model -> (faction object, key): the search runs once per loaded campaign


def is_human(w: World, f: int) -> bool:
    try:
        return w.pm.read_bytes(f + HUMAN, 1)[0] < 2
    except Exception:
        return False


def current_faction() -> str:
    """The player's faction key (Clan Skryre until a campaign has been read)."""
    return PLAYER["key"] or DEFAULT_FACTION


GAME_ROOT = 0x144480D38          # the campaign game root (0 while no campaign is loaded); A = [G + 0x2F60]
LOCAL_FACTION = 0x1C8            # [A + 0x1C8]: the local player's faction; [A + 0x90]: the campaign model
LOCAL_MODEL = 0x90


def local_faction(w: World) -> int | None:
    """The faction the player at this PC controls, from memory: [[G + 0x2F60] + 0x1C8]. Decoded on 9.0.4, 2026-10-19,
    from the UI context function IsLocalPlayersTurn (FUN_141e84054: is_factions_turn([[[A+0x90]+0x6CA0]+0x310],
    [A+0x1C8])), the game's own "is it the local player's turn" test, so in multiplayer it is this PC's player by
    construction. Checked live: Clan Scruten in a single-player Thanquol campaign. None when unreadable or when A's
    model is not the campaign being read."""
    try:
        G = w.q(GAME_ROOT)
        A = w.q(G + 0x2F60) if G else 0
        if not A or w.q(A + LOCAL_MODEL) != w.s.model:
            return None
        F = w.q(A + LOCAL_FACTION)
        return F if F and w.faction_name(F) else None
    except Exception:
        return None


def find_player_faction(w: World) -> int | None:
    """The player's faction: the local faction from memory (local_faction), accepted when it is a faction the
    assistant plays (anchors.json player_factions: Ikit's Clan Skryre, Thanquol's Clan Scruten). Player rule
    2026-10-19: from memory, never from the HUD (it was the faction whose treasury the HUD showed). 2026-10-18,
    multiplayer: a pass once acted as Ikit, a friend's faction; the local faction cannot be another player's. When the
    pointer cannot be read, the old model paths are used only if exactly one human faction the assistant plays is in
    the campaign; otherwise None (the pass waits)."""
    a = _anchors()
    model = w.s.model
    want = a.get("player_factions") or [a.get("player_faction_key") or DEFAULT_FACTION]
    p = local_faction(w)
    if p is not None:
        name = w.faction_name(p)
        if name not in want:
            return None                            # this PC plays a faction the assistant does not
    else:
        found: list[tuple[int, str]] = []
        for path in a.get("faction_paths", []):
            try:
                q = model
                for off in path:
                    q = w.q(q + off)
                n = w.faction_name(q) if q else None
                if n in want and is_human(w, q) and all(q != f for f, _n in found):
                    found.append((q, n))
            except Exception:
                continue
        if len(found) != 1 or _other_assistant_humans(w, found[0][0], want):
            return None
        p, name = found[0]
    _found.clear()
    _found[model] = (p, name)
    if PLAYER["key"] != name:
        PLAYER["key"] = name
        try:
            from assist import gamedata
            gamedata.level_name.cache_clear()
        except Exception:
            pass
    return p


def _other_assistant_humans(w: World, F: int, want: list[str]) -> bool:
    """Another human faction of a clan the assistant plays is in the campaign (F's diplomacy list): then one
    candidate is not enough, the HUD must say which is local."""
    rel = w.q(F + 0xDB8)
    if not rel:
        return False
    n, base = w.u32(rel + 4), w.q(rel + 8)
    for i in range(min(n, 4000)):
        try:
            o = w.q(base + 0x78 * i + 0x28)
            if o and o != F and is_human(w, o) and w.faction_name(o) in want:
                return True
        except Exception:
            continue
    return False


def player_faction_key(w: World) -> str | None:
    f = find_player_faction(w)
    return PLAYER["key"] if f else None


@_lru_cache(maxsize=1)
def region_provinces() -> tuple[dict[str, str], dict[str, bool]]:
    from assist import gamedata as gd
    prov, cap = {}, {}
    for r in gd._load("region_to_province_junctions_tables"):
        prov[r["region"]] = r["province"]
        cap[r["region"]] = bool(r["is_capital"])
    return prov, cap


@dataclass
class Snapshot:
    faction: int
    faction_key: str
    at_war: list[str]
    own: dict[str, int]                      # region key -> region object
    province_of: dict[str, str]
    blocked_provinces: dict[str, str]        # province -> reason
    neighbours_of: dict[str, list[str]]


def snapshot(w: World | None = None) -> Snapshot | None:
    w = w or World()
    F = find_player_faction(w)
    if F is None:
        return None
    prov, _ = region_provinces()
    wars = w.wars(F)
    war_keys = [w.faction_name(x) or hex(x) for x in wars]
    own = {}
    for r in w.faction_regions(F):
        k = w.region_key(r)
        if k:
            own[k] = r
    # enemy-held regions, straight from the enemies' own region lists
    enemy_regions: dict[str, str] = {}
    for x, name in zip(wars, war_keys):
        for r in w.faction_regions(x):
            k = w.region_key(r)
            if k:
                enemy_regions[k] = name
    enemy_provinces = {prov.get(k, k): (k, f) for k, f in enemy_regions.items()}
    # region graph around our provinces: every region of a province we hold, and their neighbours
    objs: dict[str, int] = dict(own)
    frontier = list(own.values())
    seen = set(frontier)
    our_provs = {prov.get(k, k) for k in own}
    while frontier:
        r = frontier.pop()
        for n in w.neighbours(r):
            if n in seen:
                continue
            seen.add(n)
            k = w.region_key(n)
            if not k:
                continue
            objs[k] = n
            if prov.get(k) in our_provs:        # keep walking inside our provinces only
                frontier.append(n)
    neighbours_of = {k: [w.region_key(n) or "?" for n in w.neighbours(r)] for k, r in objs.items()}
    blocked: dict[str, str] = {}
    for p in our_provs:
        if p in enemy_provinces:
            k, f = enemy_provinces[p]
            blocked[p] = f"{f} holds {k} inside this province"
            continue
        members = [k for k in objs if prov.get(k) == p]
        for k in members:
            for nk in neighbours_of.get(k, []):
                np_ = prov.get(nk)
                if np_ and np_ != p and np_ in enemy_provinces:
                    ek, f = enemy_provinces[np_]
                    blocked[p] = f"borders {np_} where {f} (at war) holds {ek}"
                    break
            if p in blocked:
                break
    return Snapshot(F, w.faction_name(F) or "?", war_keys, own, prov, blocked, neighbours_of)


# ------------------------------------------------------------------ armies
# faction F: forces count u32 F+0xF64, array F+0xF68 (entry -> force)
# force MF: cqi u32 MF+8; general [[MF+0x110]]; garrison when [[MF+0x708]] or [[MF+0x718]] non-null;
#           units: L = MF+0x6C8, count u32 L+0xC, array [L+0x10] (entry -> unit)
# unit U:   key string object at [U+0x80]+0x3E0; men u32 U+0x278 / max u32 U+0x27C
# character C: details D = [C+0x3F0]; names: 4 entries of 0x28 at D+0x10 (kind byte +0x20:
#              0 forename, 1 surname; entry -> string object with a names_name_* loc key);
#              subtype record [D+0x1F8] (key string object at [rec+8]); region [[C+0x448]+0x10]

@dataclass
class Unit:
    key: str
    men: int
    max_men: int


@dataclass
class Army:
    cqi: int
    general_subtype: str | None
    general_name: str
    region: str | None
    units: list[Unit]
    general_ptr: int = 0
    region_obj: int = 0
    garrison: bool = False
    force_ptr: int = 0
    queued: list[str] = field(default_factory=list)     # unit keys in the recruitment queue
    general_id: int = 0          # the general's character id (u32 at character +0x110; character_row_<id> in the UI)


def _loc() -> dict:
    from assist import gamedata as gd
    return gd.loc()


def _nonnull_pp(w: World, a: int) -> bool:
    p = w.q(a)
    return bool(p) and bool(w.q(p))


def character_name(w: World, C: int) -> str:
    """Name entries are either a reference to a names_name_* localisation key, or (when the player
    renamed the character) an inline UTF-16 string: {vtable in the exe, ..., u32 len +0x10, wchar* +0x18}."""
    D = w.q(C + 0x3F0)
    parts = {}
    for e in range(4):
        ent = D + 0x10 + 0x28 * e
        try:
            kind = w.pm.read_bytes(ent + 0x20, 1)[0]
            first = w.q(ent)
        except Exception:
            continue
        if 0x140000000 <= first < 0x150000000:
            n = w.u32(ent + 0x10)
            if 0 < n < 64:
                parts[kind] = w.pm.read_bytes(w.q(ent + 0x18), 2 * n).decode("utf-16-le", "replace")
            continue
        key = string_object(w.pm, first)
        if key:
            text = _loc().get(key, "")
            for _ in range(3):              # some name entries only point at another: "{{tr:names_name_761698516}}"
                m = _re.fullmatch(r"\{\{tr:([^}]+)\}\}", text)
                if not m:
                    break
                text = _loc().get(m.group(1), "")
            parts[kind] = text
    return " ".join(p for p in (parts.get(0, ""), parts.get(1, "")) if p).strip() or "?"


def character_subtype(w: World, C: int) -> str | None:
    rec = w.q(w.q(C + 0x3F0) + 0x1F8)
    return string_object(w.pm, w.q(rec + 8)) if rec else None


def recruitment_queue(w: World, MF: int) -> list[str]:
    """Unit keys queued for recruitment in a force (decompiled recruitment_item_count, 9.0.4):
    container at MF+0x6E8: count u32 +4 (MF+0x6EC), item array +8 (MF+0x6F0);
    entry -> item X; [X+0x90] = unit details record (as returned by the recruitment_items binding),
    unit key = string object at details +0x3E0; [[X+0x38]+0x98] = recruitment source record."""
    n = w.u32(MF + 0x6EC)
    if not 0 < n < 40:
        return []
    arr = w.q(MF + 0x6F0)
    keys = []
    for i in range(n):
        try:
            X = w.q(w.q(arr + 8 * i))
            keys.append(string_object(w.pm, w.q(X + 0x90) + 0x3E0) or "?")
        except Exception:
            keys.append("?")
    return keys


SCHEMER = "wh3_dlc29_skv_schemer_"     # Thanquol's Underlings: each is a one-unit force kept in limbo (force type
                                      # CHAOTIC_PLAN_SCHEMERS) that only leaves it for a Masterplan's attack; the
                                      # player's (Masterplans are the player's, 2026-10-17), never a field army here


def armies(w: World, F: int, include_garrisons: bool = False) -> list[Army]:
    out = []
    n = w.u32(F + 0xF64)
    arr = w.q(F + 0xF68)
    for i in range(min(n, 200)):
        try:
            MF = w.q(w.q(arr + 8 * i))
            garrison = _nonnull_pp(w, MF + 0x708) or _nonnull_pp(w, MF + 0x718)
            if garrison and not include_garrisons:
                continue
            g = w.q(MF + 0x110)
            C = w.q(g) if g else 0
            L = MF + 0x6C8
            un = w.u32(L + 0xC)
            uarr = w.q(L + 0x10)
            units = []
            for k in range(min(un, 40)):
                U = w.q(w.q(uarr + 8 * k))
                key = string_object(w.pm, w.q(U + 0x80) + 0x3E0) or "?"
                units.append(Unit(key, w.u32(U + 0x278), w.u32(U + 0x27C)))
            region, robj = None, 0
            if C:
                r = w.q(C + 0x448)
                robj = w.q(r + 0x10) if r else 0
                region = w.region_key(robj) if robj else None
            sub = character_subtype(w, C) if C else None
            if sub and sub.startswith(SCHEMER):
                continue
            out.append(Army(w.u32(MF + 8), sub,
                            character_name(w, C) if C else "(no general)", region, units, C, robj, garrison,
                            MF, recruitment_queue(w, MF), w.u32(C + 0x110) if C else 0))
        except Exception:
            continue
    return out


# ------------------------------------------------------------------ characters (heroes roam on their own)
# faction F: characters count u32 F+0xF24, array F+0xF28 (entry -> character)
# character C: type key (agent: "general", "engineer", ...) string object at [C+0x330]+8;
#              embedded in force: [[C+0x438]+0x10]+0x18 (0 when the hero is on the map by itself)

@dataclass
class Character:
    ptr: int
    name: str
    subtype: str | None
    agent: str | None
    embedded_force: int        # 0 when roaming free
    region: str | None


def characters(w: World, F: int) -> list[Character]:
    out = []
    n = w.u32(F + 0xF24)
    arr = w.q(F + 0xF28)
    for i in range(min(n, 500)):
        try:
            C = w.q(w.q(arr + 8 * i))
            agent = string_object(w.pm, w.q(w.q(C + 0x330) + 8))
            e = w.q(C + 0x438)
            emb = 0
            if e and w.q(e + 0x10):
                emb = w.q(w.q(e + 0x10) + 0x18)
            r = w.q(C + 0x448)
            region = w.region_key(w.q(r + 0x10)) if r and w.q(r + 0x10) else None
            out.append(Character(C, character_name(w, C), character_subtype(w, C), agent, emb, region))
        except Exception:
            continue
    return out


# ------------------------------------------------------------------ multiplayer latency
_MP_CACHE: dict = {}


def multiplayer(w: World | None = None) -> bool:
    """Another human faction is in the loaded campaign (memory: the player's diplomacy list, is_human)."""
    w = w or World()
    m = w.s.model
    if m in _MP_CACHE:
        return _MP_CACHE[m]
    F = find_player_faction(w)
    hit = False
    rel = w.q(F + 0xDB8) if F else 0
    if rel:
        n, base = w.u32(rel + 4), w.q(rel + 8)
        for i in range(min(n, 4000)):
            try:
                o = w.q(base + 0x78 * i + 0x28)
                if o and o != F and is_human(w, o):
                    hit = True
                    break
            except Exception:
                continue
    _MP_CACHE.clear()
    _MP_CACHE[m] = hit
    return hit


# ------------------------------------------------------------------ hero caps
_AGENT_RECORDS: dict = {}        # model -> {agent type key: agent record}


def agent_record(w: World, F: int, agent: str) -> int | None:
    """The agent type's DB record ([C + 0x330] of any character of that type, its +8 the key string object), found
    among F's and its known factions' characters once per campaign."""
    recs = _AGENT_RECORDS.setdefault(w.s.model, {})
    if agent in recs:
        return recs[agent]
    fs = [F]
    try:
        rel = w.q(F + 0xDB8)
        n, base = w.u32(rel + 4), w.q(rel + 8)
        fs += [w.q(base + 0x78 * i + 0x28) for i in range(min(n, 4000))]
    except Exception:
        pass
    for f in fs:
        try:
            for c in characters(w, f):
                recs.setdefault(c.agent, w.q(c.ptr + 0x330))
        except Exception:
            continue
        if agent in recs:
            break
    return recs.get(agent)


def _effect_value(w: World, F: int, kind: int, R: int) -> int:
    """F's cached effect value for an agent type: the sorted table at F + 0x1A8 (count u32 +4, entries [+8], 0x20
    bytes: u64 key = ((1 << 16 | kind) << 40) | agent id u32 R + 0xD0, record +0x10 == R, f32 value +0x18), rounded
    as the game does (FUN_141515c24)."""
    E = F + 0x1A8
    n, arr = w.u32(E + 4), w.q(E + 8)
    key = (((1 << 16) | kind) << 40) | w.u32(R + 0xD0)
    lo, hi = 0, n
    while lo < hi:
        m = (lo + hi) // 2
        if w.q(arr + 0x20 * m) < key:
            lo = m + 1
        else:
            hi = m
    if lo < n and w.q(arr + 0x20 * lo) == key and w.q(arr + 0x20 * lo + 0x10) == R:
        f = struct.unpack("<f", w.pm.read_bytes(arr + 0x20 * lo + 0x18, 4))[0]
        return int(f + 0.5) if f > 0 else int(f - 0.5)
    return 0


def agent_cap(w: World, F: int, agent: str) -> int | None:
    """The faction's cap for a hero type, computed as the game's faction:agent_cap (binding FUN_142792210 ->
    FUN_14268cf88, decompiled 9.0.4 2026-10-19): min(max cap, base + effects + extra), where
      base     the model's cap table [[[F+0x3A8]+0x90]+0x6FB0] (sorted list of entries by i32 +0x10; the entry for
               u32 F + 0x1440), its map at entry + 0x70: node +0x10 == R -> i32 +0x18
      effects  _effect_value(kind 0); max cap = max(0, _effect_value(kind 6) + i32 R + 0x88)
      extra    F's list at F + 0x1BB0 (count u32 F + 0x1BAC) of {R, i32 +8}
    None when the agent type has no cap (u32 R + 0x30 < 3: lords) or cannot be read. Checked live 2026-10-19 on a
    turn-12 Thanquol save: 1 for every hero type (base 1, no bonus yet); bonuses not yet compared with the panel."""
    try:
        R = agent_record(w, F, agent)
        if not R or w.u32(R + 0x30) < 3:
            return None
        i32 = lambda a: struct.unpack("<i", w.pm.read_bytes(a, 4))[0]
        T = w.q(w.q(w.q(F + 0x3A8) + 0x90) + 0x6FB0)
        n, arr = w.u32(T + 4), w.q(T + 8)
        want = w.u32(F + 0x1440)
        ent = next((w.q(arr + 8 * i) for i in range(n) if i32(w.q(arr + 8 * i) + 0x10) >= want), w.q(arr + 8 * (n - 1)))
        M, base = ent + 0x70, 0
        if w.u32(M + 0x1C) != 1:
            head = M + 8
            node, k = w.q(head), 0
            while node and node != head and k < 4000:
                if w.q(node + 0x10) == R:
                    base = i32(node + 0x18)
                    break
                node, k = w.q(node), k + 1
        extra = 0
        for i in range(min(w.u32(F + 0x1BAC), 64)):
            a = w.q(F + 0x1BB0) + 16 * i
            if w.q(a) == R:
                extra = i32(a + 8)
        mx = max(0, _effect_value(w, F, 6, R) + i32(R + 0x88))
        return min(mx, base + _effect_value(w, F, 0, R) + extra)
    except Exception:
        return None


def human_factions(w: World) -> list[str]:
    """Keys of every human faction in the campaign (is_human), sorted: the local faction and those in its diplomacy
    list. The same after a reload of the campaign (assist/runner._cid)."""
    F = local_faction(w) or find_player_faction(w)
    if not F:
        return []
    out = {w.faction_name(F)} if is_human(w, F) else set()
    rel = w.q(F + 0xDB8)
    n, base = (w.u32(rel + 4), w.q(rel + 8)) if rel else (0, 0)
    for i in range(min(n, 4000)):
        try:
            o = w.q(base + 0x78 * i + 0x28)
            if o and is_human(w, o):
                out.add(w.faction_name(o))
        except Exception:
            continue
    return sorted(k for k in out if k)
