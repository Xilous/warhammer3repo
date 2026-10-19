"""Small file helpers."""
from __future__ import annotations
import time
from pathlib import Path


def replace(tmp: Path, dst: Path, tries: int = 10, pause: float = 0.05) -> None:
    """Move tmp over dst, as Path.replace, but retried: on Windows the swap fails ("Access is denied") while another
    thread or process has dst open, e.g. the widget reading it (2026-10-18: runs/engineer_claims.json failed the
    army step's verification). After the retries the content is written to dst directly."""
    for _ in range(tries):
        try:
            tmp.replace(dst)
            return
        except PermissionError:
            time.sleep(pause)
    data = tmp.read_bytes()
    dst.write_bytes(data)
    try:
        tmp.unlink()
    except OSError:
        pass
