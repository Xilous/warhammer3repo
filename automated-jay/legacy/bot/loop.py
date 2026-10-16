"""Read -> decide -> act -> wait. One iteration per campaign turn."""
from __future__ import annotations
import json
import sys
import time
from datetime import datetime

from . import config
from .brain.rulebook import decide
from .hands.osinput import Hands
from .sensor.memory import MemorySensor
from .sensor.screen import ScreenSensor


def wait_for_turn_change(sensor: MemorySensor, start: int, timeout: float) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = sensor.read()
        if s.ok and s.turn != start:
            return True
        time.sleep(1.0)
    return False


def run(turns: int, dry_run: bool, turn_timeout: float = 600) -> None:
    config.RUNS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log = open(config.RUNS_DIR / f"{stamp}.jsonl", "a")
    mem = MemorySensor()
    scr = ScreenSensor()
    hands = Hands(dry_run=dry_run)
    print(f"model base: {hex(mem.model) if mem.model else None}")

    for i in range(turns):
        s = mem.read()
        s.extras["screen"] = scr.fingerprint()
        a = decide(s)
        rec = {"t": time.time(), "state": json.loads(s.to_json()), "action": a.kind, "reason": a.reason}
        log.write(json.dumps(rec) + "\n")
        log.flush()
        print(f"[{i}] turn={s.turn} treasury={s.treasury} income={s.income} -> {a.kind} ({a.reason})")

        if a.kind == "ask":
            if dry_run or not sys.stdin.isatty():
                print("no rule applies and no operator attached; stopping")
                return
            input("No rule applies. Decide in-game, then press Enter here to continue... ")
            continue
        if a.kind == "end_turn":
            hands.focus()
            hands.end_turn()
            if dry_run:
                continue
            if not wait_for_turn_change(mem, s.turn, turn_timeout):
                print("turn did not advance; stopping so you can look")
                return
