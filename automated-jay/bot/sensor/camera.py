"""Campaign camera from memory, and world -> screen projection.

Found 2026-10-16 (9.0.4) by panning the camera and watching memory. The renderer keeps a per-frame
camera block:
    block = [Warhammer3.exe + 0x48610A0] + 0x3710
    block - 0x60 : float4 forward plane (fx, fh, fy, d)   world axes are (x, height, y)
    block + 0x00 : float3 eye (x, h, y)
    block + 0x0C : float  m00 (projection x scale)
    block + 0xA0 : float  m11 (projection y scale)
Character map position (x, y) is at character + 0x60 (floats), grid position at +0x68 (u16 x, y).
"""
from __future__ import annotations
import struct
from dataclasses import dataclass

import numpy as np

from .. import config
from .memory import MemorySensor

# Camera block candidates: (static pointer in the exe, offset from its target to the eye), tried in order.
# 0x4095490 (+0xA00) found 2026-10-16 by a resident-memory scan for the block layout: it holds the camera while it
# is idle too. 0xBC5F08's block (and 0x4480D00 +0x1420) only read as a camera while the camera moves: after
# recruiting a lord or hero, or an Escape, they held garbage until the next pan ("camera block not found").
# 0x48610A0 did not survive a save reload, so it is only a last fallback.
BLOCKS = [(0x4095490, 0xA00), (0xBC5F08, 0x3010), (0x48610A0, 0x3710)]
M00, M11 = 0.8222039, 1.4616958          # projection scales at 1920x1080 (fixed FOV; zoom does not change them)
GROUND_H = 0.7          # typical terrain height near the coast; flags sit higher


@dataclass
class Camera:
    eye: np.ndarray        # (x, h, y)
    fwd: np.ndarray
    right: np.ndarray
    up: np.ndarray
    m00: float
    m11: float

    def project(self, x: float, y: float, h: float = GROUND_H) -> tuple[float, float] | None:
        d = np.array([x, h, y], dtype=np.float64) - self.eye
        zc = float(d @ self.fwd)
        if zc <= 0.01:
            return None
        xn = self.m00 * float(d @ self.right) / zc
        yn = self.m11 * float(d @ self.up) / zc
        W, H = config.RESOLUTION
        return (xn + 1) / 2 * W, (1 - yn) / 2 * H

    def ground_at_center(self, h: float = GROUND_H) -> tuple[float, float]:
        t = (h - self.eye[1]) / self.fwd[1]
        p = self.eye + t * self.fwd
        return float(p[0]), float(p[2])


def _block(s: MemorySensor) -> int:
    pm = s.pm
    for ptr, off in BLOCKS:
        try:
            blk = pm.read_ulonglong(s.base + ptr) + off
            eye = struct.unpack("<3f", pm.read_bytes(blk, 12))
            fwd = struct.unpack("<3f", pm.read_bytes(blk - 0x60, 12))
        except Exception:
            continue
        n = sum(v * v for v in fwd)
        if abs(n - 1) < 0.01 and -0.99 < fwd[1] < -0.2 and eye[1] > 0.5:
            return blk
    raise RuntimeError("camera block not found")


def read_camera(s: MemorySensor) -> Camera:
    pm = s.pm
    blk = _block(s)
    eye = np.array(struct.unpack("<3f", pm.read_bytes(blk, 12)), dtype=np.float64)
    fwd = np.array(struct.unpack("<3f", pm.read_bytes(blk - 0x60, 12)), dtype=np.float64)
    fwd /= np.linalg.norm(fwd)
    right = np.array([fwd[2], 0.0, -fwd[0]])
    right /= np.linalg.norm(right)
    up = np.array([0.0, 1.0, 0.0]) - fwd[1] * fwd
    up /= np.linalg.norm(up)
    return Camera(eye, fwd, right, up, M00, M11)


def character_pos(pm, C: int) -> tuple[float, float]:
    return struct.unpack("<2f", pm.read_bytes(C + 0x60, 8))
