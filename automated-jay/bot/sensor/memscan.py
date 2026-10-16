"""Low-level process-memory helpers: region walk, byte scan, pointer scan.

Kept separate from the reader so tools/probe.py and the runtime share one
implementation. Nothing here knows about game structures.
"""
from __future__ import annotations
import ctypes
import ctypes.wintypes as wt
import struct
from dataclasses import dataclass
from typing import Iterator

import pymem
import pymem.process

MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
MEM_IMAGE = 0x1000000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
READABLE = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}  # R, RW, WC, XR, XRW, XWC


class MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD),
        ("PartitionId", wt.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
    ]


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.VirtualQueryEx.argtypes = [wt.HANDLE, wt.LPCVOID, ctypes.POINTER(MBI), ctypes.c_size_t]
_k32.VirtualQueryEx.restype = ctypes.c_size_t


@dataclass
class Region:
    base: int
    size: int
    protect: int
    type: int


def regions(handle: int, lo: int = 0, hi: int = 0x7FFF_FFFF_FFFF) -> Iterator[Region]:
    addr = lo
    mbi = MBI()
    while addr < hi:
        if not _k32.VirtualQueryEx(handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        base = mbi.BaseAddress or 0
        size = mbi.RegionSize
        if mbi.State == MEM_COMMIT and (mbi.Protect & 0xFF) in READABLE and not (mbi.Protect & PAGE_GUARD):
            yield Region(base, size, mbi.Protect, mbi.Type)
        addr = base + size


def attach(process_name: str) -> tuple[pymem.Pymem, int, int]:
    pm = pymem.Pymem(process_name)
    m = pymem.process.module_from_name(pm.process_handle, process_name)
    return pm, m.lpBaseOfDll, m.SizeOfImage


class _WSEX(ctypes.Structure):
    _fields_ = [("VirtualAddress", ctypes.c_void_p), ("Flags", ctypes.c_size_t)]


_psapi = ctypes.WinDLL("psapi")
PAGE = 4096


def resident_runs(handle: int, base: int, size: int) -> list[tuple[int, int]]:
    """(address, length) runs of pages of [base, base+size) that are already in the game's RAM.

    Reading a committed page that is not resident makes Windows give it real memory, so a scan that
    reads everything inflates the game's RAM use to its whole commit (measured 2026-10-17: 6.6 GB -> 20 GB).
    Live game data is always resident, so scans only read resident pages."""
    n = size // PAGE
    if n == 0:
        return []
    arr = (_WSEX * n)()
    for i in range(n):
        arr[i].VirtualAddress = base + i * PAGE
    if not _psapi.QueryWorkingSetEx(handle, arr, ctypes.sizeof(arr)):
        return []
    runs, start = [], None
    for i in range(n):
        res = arr[i].Flags & 1
        if res and start is None:
            start = i
        elif not res and start is not None:
            runs.append((base + start * PAGE, (i - start) * PAGE))
            start = None
    if start is not None:
        runs.append((base + start * PAGE, (n - start) * PAGE))
    return runs


def read_region(pm: pymem.Pymem, r: Region, chunk: int = 1 << 24) -> Iterator[tuple[int, bytes]]:
    """Yield (address, bytes) chunks for the RESIDENT pages of a region, skipping unreadable ones."""
    for rb in range(r.base, r.base + r.size, chunk):
        rs = min(chunk, r.base + r.size - rb)
        for addr, n in resident_runs(pm.process_handle, rb, rs):
            try:
                yield addr, pm.read_bytes(addr, n)
            except pymem.exception.MemoryReadError:
                pass


def scan_bytes(pm: pymem.Pymem, needle: bytes, private_only: bool = True, limit: int = 50) -> list[int]:
    """Find every occurrence of `needle` in readable memory. Private (heap) regions only by default."""
    hits: list[int] = []
    for r in regions(pm.process_handle):
        if private_only and r.type != MEM_PRIVATE:
            continue
        for addr, buf in read_region(pm, r):
            i = buf.find(needle)
            while i != -1:
                hits.append(addr + i)
                if len(hits) >= limit:
                    return hits
                i = buf.find(needle, i + 1)
    return hits


def scan_pointers_in_module(pm: pymem.Pymem, mod_base: int, mod_size: int,
                            lo: int, hi: int) -> list[tuple[int, int]]:
    """Find 8-byte aligned values V in the module's data with lo <= V <= hi.
    Returns (static_address, value). Static addresses give patch-stable pointer paths."""
    out: list[tuple[int, int]] = []
    for r in regions(pm.process_handle, mod_base, mod_base + mod_size):
        if r.base + r.size <= mod_base or r.base >= mod_base + mod_size:
            continue
        for addr, buf in read_region(pm, r):
            n = len(buf) // 8
            for i, v in enumerate(struct.unpack_from(f"<{n}Q", buf)):
                if lo <= v <= hi:
                    out.append((addr + i * 8, v))
    return out
