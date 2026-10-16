"""Per-pass, per-step and per-action timing, cheap enough to leave on.

    with timing.trace(turn=N, label="pass"):            # one JSON line per pass in runs/timing-YYYYMMDD.jsonl
        with timing.step("tech"):
            ...                                          # tools/ui.py records every input ("click", "key", ...),
                                                         # tools/wait.py every wait ("wait": what, ms, ok, polls),
                                                         # time.sleep every fixed sleep (per call site),
                                                         # bot/sensor/ui.py the UI-tree walks (walks, nodes, ms)

A step line holds: total ms; ms in input / waits / fixed sleeps / tree lookups; counts; the fixed sleeps by call
site ("tech.py:323": [count, ms]); and the actions in order ({"a": "click", "ms": .., "at": [x, y]},
{"a": "wait", "what": "technology_panel appears", "ms": .., "ok": true}, ...), capped at MAX_ACTIONS per step.

Cost: one thread-local lookup per recorded thing, nothing at all in a thread without an active trace.

    python -X utf8 -m tools.timing [runs/timing-YYYYMMDD.jsonl] [--last N]   # per-step summary of recent passes
"""
from __future__ import annotations
import contextlib
import json
import os
import sys
import threading
import time
from datetime import datetime

from bot import config

MAX_ACTIONS = 400
LAST: dict | None = None          # the last pass record written (tools/bench.py prints it)
_tls = threading.local()
real_sleep = time.sleep           # the unhooked sleep: tools/wait.py polls with it (a poll is not a fixed sleep)
perf = time.perf_counter


class _Step:
    __slots__ = ("name", "t0", "input_ms", "wait_ms", "sleep_ms", "clicks", "keys", "waits", "timeouts",
                 "sleeps", "actions", "walk0", "result")

    def __init__(self, name: str) -> None:
        from bot.sensor import ui as _ui
        self.name = name
        self.t0 = perf()
        self.input_ms = self.wait_ms = self.sleep_ms = 0.0
        self.clicks = self.keys = self.waits = self.timeouts = 0
        self.sleeps: dict[str, list] = {}
        self.actions: list[dict] = []
        self.walk0 = _ui.STATS.snapshot()
        self.result = None

    def add(self, rec: dict) -> None:
        if len(self.actions) < MAX_ACTIONS:
            self.actions.append(rec)

    def line(self) -> dict:
        from bot.sensor import ui as _ui
        w = _ui.STATS.since(self.walk0)
        return {"step": self.name, "ms": round((perf() - self.t0) * 1000, 1),
                "input_ms": round(self.input_ms, 1), "wait_ms": round(self.wait_ms, 1),
                "sleep_ms": round(self.sleep_ms, 1), "lookup_ms": round(w["ms"], 1),
                "walks": w["walks"], "nodes": w["nodes"], "clicks": self.clicks, "keys": self.keys,
                "waits": self.waits, "timeouts": self.timeouts,
                "sleeps": {k: [n, round(ms, 1)] for k, (n, ms) in self.sleeps.items()},
                "result": self.result, "actions": self.actions}


class _Trace:
    def __init__(self, label: str, turn, meta: dict) -> None:
        self.label, self.turn, self.meta = label, turn, meta
        self.t0 = perf()
        self.steps: list[dict] = []
        self.phases: dict[str, float] = {}


def _cur_step() -> _Step | None:
    return getattr(_tls, "step", None)


def active() -> bool:
    return getattr(_tls, "step", None) is not None


@contextlib.contextmanager
def trace(label: str = "pass", turn=None, path=None, **meta):
    """One pass. Steps inside it are written as one JSON line when it ends (also when it raises)."""
    tr = _Trace(label, turn, meta)
    outer = getattr(_tls, "trace", None)
    _tls.trace = tr
    try:
        yield tr
    finally:
        _tls.trace = outer
        global LAST
        rec = {"t": round(time.time(), 3), "label": label, "turn": tr.turn,
               "ms": round((perf() - tr.t0) * 1000, 1), "phases": tr.phases, "steps": tr.steps, **tr.meta}
        LAST = rec
        write(rec, path)


@contextlib.contextmanager
def step(name: str):
    """A step (or a pre-pass phase) inside the current trace. Steps do not nest: an inner step() is a no-op."""
    if getattr(_tls, "step", None) is not None:
        yield None
        return
    st = _Step(name)
    _tls.step = st
    try:
        yield st
    finally:
        _tls.step = None
        tr = getattr(_tls, "trace", None)
        if tr is not None:
            tr.steps.append(st.line())


def phase(name: str, seconds: float) -> None:
    """A pre-pass phase measured elsewhere (detect, settle, idle)."""
    tr = getattr(_tls, "trace", None)
    if tr is not None:
        tr.phases[name] = round(seconds * 1000, 1)


def set_result(result) -> None:
    st = _cur_step()
    if st is not None:
        st.result = None if result is None else str(result)[:300]


# ------------------------------------------------------------------ recording (called by tools/ui.py, tools/wait.py)

def input_event(kind: str, ms: float, **kw) -> None:
    st = _cur_step()
    if st is None:
        return
    st.input_ms += ms
    if kind in ("click", "rclick", "dclick", "drag"):
        st.clicks += 1
    elif kind in ("key", "hold"):
        st.keys += 1
    st.add({"a": kind, "ms": round(ms, 1), **kw})


def wait_event(what: str, ms: float, ok: bool, polls: int, **kw) -> None:
    st = _cur_step()
    if st is None:
        return
    st.wait_ms += ms
    st.waits += 1
    if not ok:
        st.timeouts += 1
    st.add({"a": "wait", "what": what, "ms": round(ms, 1), "ok": ok, "polls": polls, **kw})


@contextlib.contextmanager
def quiet():
    """Sleeps inside are part of something already recorded (an input primitive, a wait): not counted again."""
    q = getattr(_tls, "quiet", 0)
    _tls.quiet = q + 1
    try:
        yield
    finally:
        _tls.quiet = q


def _hooked_sleep(seconds: float) -> None:
    st = getattr(_tls, "step", None)
    if st is None or getattr(_tls, "quiet", 0):
        return real_sleep(seconds)
    f = sys._getframe(1)
    where = f"{os.path.basename(f.f_code.co_filename)}:{f.f_lineno}"
    t = perf()
    try:
        real_sleep(seconds)
    finally:
        ms = (perf() - t) * 1000
        st.sleep_ms += ms
        e = st.sleeps.get(where)
        if e is None:
            st.sleeps[where] = [1, ms]
        else:
            e[0] += 1
            e[1] += ms
        if seconds >= 0.05:
            st.add({"a": "sleep", "at": where, "ms": round(ms, 1)})


def install_sleep_hook() -> None:
    """Account every time.sleep made inside a step as a fixed sleep (by call site). Idempotent."""
    if time.sleep is not _hooked_sleep:
        time.sleep = _hooked_sleep


install_sleep_hook()


# ------------------------------------------------------------------ output

def log_path():
    return config.RUNS_DIR / f"timing-{datetime.now():%Y%m%d}.jsonl"


def write(rec: dict, path=None) -> None:
    try:
        config.RUNS_DIR.mkdir(exist_ok=True)
        with open(path or log_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as ex:
        print(f"WARNING: timing log not written ({ex})", flush=True)


def summary(recs: list[dict]) -> str:
    out = []
    for r in recs:
        out.append(f"{datetime.fromtimestamp(r['t']):%H:%M:%S} {r.get('label')} turn {r.get('turn')}: "
                   f"{r['ms'] / 1000:.2f} s" + (f"  phases {r['phases']}" if r.get("phases") else ""))
        for s in r["steps"]:
            out.append(f"  {s['step']:10s} {s['ms'] / 1000:7.2f} s  input {s['input_ms'] / 1000:5.2f}  "
                       f"wait {s['wait_ms'] / 1000:5.2f}  sleep {s['sleep_ms'] / 1000:5.2f}  "
                       f"lookup {s['lookup_ms'] / 1000:5.2f} ({s['walks']} walks)  clicks {s['clicks']}  "
                       f"timeouts {s['timeouts']}  | {s.get('result') or ''}"[:220])
            top = sorted(s["sleeps"].items(), key=lambda kv: -kv[1][1])[:6]
            if top:
                out.append("             sleeps: " + ", ".join(f"{k} {n}x {ms / 1000:.2f}s" for k, (n, ms) in top))
    return "\n".join(out)


def main() -> int:
    args = sys.argv[1:]
    n = int(args[args.index("--last") + 1]) if "--last" in args else 5
    files = [a for a in args if a.endswith(".jsonl")] or [str(log_path())]
    recs = []
    for fn in files:
        with open(fn, encoding="utf-8") as f:
            recs += [json.loads(line) for line in f if line.strip()]
    print(summary(recs[-n:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
