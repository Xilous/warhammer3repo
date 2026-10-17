"""Read building slots from the province panel by matching slot images against the game's own
building icons (assist/templates/buildings, extracted by tools/extract_icons.py).

A slot cell is 74x74 px at UI scale 1, the same size as the icon files.
"""
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ICONS = Path(__file__).resolve().parent / "templates" / "buildings"
CELL = 74


IGNORE = np.ones((CELL, CELL), bool)
IGNORE[CELL - 22:, :22] = False        # level numeral, bottom-left
IGNORE[:24, CELL - 26:] = False        # hammer / status badge, top-right


ICON_SCALE = 0.80      # the slot card draws the icon at ~80% of the 74 px cell (measured)
SCALES = (0.74, 0.80, 0.86)


@lru_cache(maxsize=16)
def icon_bank(scale: float = ICON_SCALE, cell: int = CELL) -> dict[str, np.ndarray]:
    """icon name -> RGBA float array cell x cell (alpha 0..1), icon shrunk to `scale` of the cell, centred."""
    bank = {}
    side = int(round(cell * scale))
    off = (cell - side) // 2
    for p in ICONS.glob("*.png"):
        if p.suffix != ".png":
            continue
        small = Image.open(p).convert("RGBA").resize((side, side), Image.LANCZOS)
        canvas = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
        canvas.paste(small, (off, off))
        a = np.asarray(canvas).astype(np.float32)
        a[..., 3] /= 255.0
        bank[p.stem] = a
    return bank


@lru_cache(maxsize=1)
def icon_chains() -> dict[str, list[str]]:
    return json.load(open(ICONS / "_icon_to_chains.json"))


def _grey(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def _ncc(a: np.ndarray, b: np.ndarray, m: np.ndarray) -> float:
    x = a[m]
    y = b[m]
    x = x - x.mean()
    y = y - y.mean()
    d = np.sqrt((x * x).sum() * (y * y).sum())
    return float((x * y).sum() / d) if d else 0.0


def match_cell(img: Image.Image, cx: int, cy: int, top: int = 3, search: int = 4, cell: int = CELL,
               names: list[str] | None = None) -> list[tuple[float, str]]:
    """Best icon matches for the card centred at (cx, cy): each icon is drawn over the card's own
    parchment colour and compared in grey (normalised correlation), allowing a few px of offset.
    `cell` is the card size in px (74 for province slots); `names` limits the candidate icons."""
    pad = search
    x0, y0 = cx - cell // 2 - pad, cy - cell // 2 - pad
    big = np.asarray(img.crop((x0, y0, x0 + cell + 2 * pad, y0 + cell + 2 * pad)).convert("RGB")).astype(np.float32)
    centre = big[pad:pad + cell, pad:pad + cell]
    f = max(1, cell // 10)
    band = np.concatenate([centre[f:f + 6, f:-f].reshape(-1, 3), centre[-f - 6:-f, 3 * f:-f].reshape(-1, 3)])
    bg = np.median(band, axis=0)
    cells = {(dx, dy): _grey(big[dy:dy + cell, dx:dx + cell])
             for dy in range(0, 2 * pad + 1, 2) for dx in range(0, 2 * pad + 1, 2)}
    m = np.ones((cell, cell), bool)
    k = int(cell * 0.3)
    m[cell - k:, :k] = False                                      # level numeral, bottom-left
    m[:int(cell * 0.32), cell - int(cell * 0.35):] = False        # badge, top-right
    m[:5, :] = m[-5:, :] = m[:, :5] = m[:, -5:] = False          # card frame
    scores: dict[str, float] = {}
    for scale in SCALES:
        for name, rgba in icon_bank(scale, cell).items():
            if names is not None and name not in names:
                continue
            comp = rgba[..., :3] * rgba[..., 3:4] + bg * (1 - rgba[..., 3:4])
            t = _grey(comp)
            best = max(_ncc(c, t, m) for c in cells.values())
            scores[name] = max(scores.get(name, -1.0), best)
    scores = sorted(((v, k) for k, v in scores.items()), reverse=True)
    return scores[:top]
