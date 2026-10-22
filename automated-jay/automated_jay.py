"""Entry point of the distributable exe (tools/build_exe.py); the same as `python -m assist.runner` from the repo.

    automated-jay.exe              the assistant: window + overlay, acts at every turn start
    automated-jay.exe --once       one pass right now (the same checks as Run now)
    automated-jay.exe --selftest   check the bundled game data and the connection to the game (memory reads only, no
                                   input), write runs/selftest.txt next to the exe, and exit
"""
from __future__ import annotations
import json
import sys

from bot import config


def _console() -> None:
    """The windowed exe has no console: print() would fail. Send output to runs/console.log next to the exe."""
    if sys.stdout is None or sys.stderr is None:
        config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
        log = open(config.RUNS_DIR / "console.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


def selftest() -> int:
    lines: list[str] = []

    def check(name, fn):
        try:
            lines.append(f"OK    {name}: {str(fn())[:300]}")
        except Exception as ex:                       # noqa: BLE001  (a report, not a crash)
            lines.append(f"FAIL  {name}: {type(ex).__name__}: {ex}")

    from assist import gamedata as gd
    check("paths", lambda: f"user files {config.ROOT}, bundled data {config.DB_DIR.parent}")
    check("release", lambda: (config.BUNDLE / "data" / "release.txt").read_text(encoding="utf-8").strip()
          if config.FROZEN else "from the repo")
    check("strategy files", lambda: sorted(p.name for p in config.STRATEGY_DIR.glob("*.json")))
    check("localisation", lambda: f"{len(gd.loc())} names")
    for table in sorted(p.stem for p in config.DB_DIR.glob("*.json")):
        check(f"table {table}", lambda t=table: f"{len(json.load(open(config.DB_DIR / f'{t}.json', encoding='utf-8')))} rows")
    check("tech beeline", lambda: f"{len(json.load(open(config.BEELINE_FILE, encoding='utf-8')))} entries")
    from assist import runner
    check("schedule", runner.schedule)
    from bot.sensor.memory import MemorySensor
    s = MemorySensor()
    st = s.read()
    check("game", lambda: (f"attached, turn {st.turn}, treasury {st.treasury}" if st.ok
                           else "game not running or no campaign loaded (start it and run --selftest again)"))
    if st.ok:
        from bot.sensor import turn
        from assist import build, recruit, skills
        check("whose turn", lambda: turn.players_turn(s))
        check("building plan", lambda: build.planned_actions())
        check("recruitment sources", lambda: recruit.sources())
        check("skill orders", lambda: sorted(skills.orders()["characters"]))

        def plans():
            from bot.sensor import masterplans as mem
            m = mem.read()
            if m is None:
                return "not found in memory"
            return (f"types {sorted(m.unlocked_types)}, Warpstone {m.warpstone}, plans "
                    f"{[(p.type, p.region, p.risk, p.alarm) for p in m.plans]}, Underlings "
                    f"{[(u.name, 'free' if u.free else 'unlocked' if u.unlocked else 'locked') for u in m.underlings]}, "
                    f"{len(m.inventory)} Secrets, {len(m.region_cooldowns)} settlements on cooldown")
        from bot.sensor.world import World, find_player_faction
        _w = World(s)
        def secrets_shop():
            from bot.sensor import masterplans as mem
            r = mem.shop(_w)
            if r is None:
                return "not found in memory"
            lines, counts = r
            listed = [k for k, l in lines.items() if l.listed]
            blocked = sorted(k.replace("wh3_dlc29_", "") for k, l in lines.items() if l.blocked)
            return (f"{len(lines)} lines in {len(counts)} tabs, {len(listed)} offered, purchases per tab {counts}, "
                    f"needing content not owned: {blocked}")
        if (_w.faction_name(find_player_faction(_w) or 0) or "") == "wh3_dlc29_skv_clan_scruten":
            check("masterplans (memory)", plans)
            check("Secrets shop (memory)", secrets_shop)

    text = "\n".join(lines)
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (config.RUNS_DIR / "selftest.txt").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if any(x.startswith("FAIL") for x in lines) else 0


def main() -> int:
    _console()
    if "--selftest" in sys.argv:
        return selftest()
    from assist.runner import main as run
    return run()


if __name__ == "__main__":
    sys.exit(main())
