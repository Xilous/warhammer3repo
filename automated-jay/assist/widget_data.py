"""What the widget says, in plain words (player request 2026-10-24: "i find myself mostly ignoring almost every word";
the redesign the player approved: https://claude.ai/artifact/2siWTbdSqXSmnzky6z2CXr). Pure data for assist/rail.py
(the collapsed bar) and assist/railpanel.py (the full-screen view), built from memory and the pass's own result lines;
nothing here clicks, and nothing here decides what the player can afford (player rule 2026-10-24: the widget gives
the facts, the player decides).

  steps(lines)              THIS TURN: one plain line per step, with its state (done / waiting / failed)
  needs(state, detail, ids) NEEDS YOU: what waits on the player, each with what happens until it is done
  army_cards(rows, fin)     ARMIES: each army's composition against the playbook, its upkeep, its refill switch
  progress(w, F, rows, st)  ARMY BUILDER, in progress: what each refill or asked-for army is doing and what is next
  bar_line(...)             the collapsed bar's one line
"""
from __future__ import annotations
import re
from collections import Counter

from . import gamedata as gd

STEP_NAMES = {"events": "Events", "rites": "Rites", "workshop": "Workshop", "tech": "Tech", "skills": "Skills",
              "masterplans": "Plans", "buildings": "Buildings", "army": "Army", "end turn pressed": "End turn"}
FAIL = ("ERROR", "MISSED", "INTERRUPTED", "interrupted", "could not", "did not", "refused by the game", "failed",
        "NOT confirmed", "NOT ENDED", "not done")
WAIT = ("waiting for", "waits", "queued", "held")


def _nice(text: str) -> str:
    from .app import nice
    return nice(text)


def region_name(key: str | None) -> str:
    return gd.loc().get("regions_onscreen_" + (key or ""), key or "")


def province_name(key: str | None) -> str:
    return gd.loc().get("provinces_onscreen_" + (key or ""), key or "")


def unit_label(key: str) -> str:
    from .army import unit_name
    return unit_name(key)


# ------------------------------------------------------------------ THIS TURN
def _first_sentence(text: str, limit: int = 220) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "..."


def steps(lines: list[str]) -> list[dict]:
    """The pass's result lines ("step: result | verified | MISSED ...") as [{"name", "state", "text"}]: the result in
    plain words (the verification bookkeeping dropped), state "failed" when any part failed, "wait" when it waits on
    the player or the game, else "done"."""
    out = []
    for line in lines or []:
        if line.startswith("turn ") or ": " not in line:
            continue
        step, rest = line.split(": ", 1)
        name = STEP_NAMES.get(step.strip().lower(), step.strip().capitalize())
        parts = [p.strip() for p in rest.split(" | ")]
        main = parts[0]
        bad = [p for p in parts[1:] if any(k in p for k in FAIL) and not p.startswith("verified")]
        state = "failed" if bad or any(k in main for k in FAIL) else "wait" if any(k in main for k in WAIT) else "done"
        text = _nice(main)
        text = text[:1].upper() + text[1:]
        if bad:
            why = bad[0].replace("not done, with a reason: ", "")
            text += " — " + _nice(why)
        out.append({"name": name, "state": state, "text": _first_sentence(text, 260)})
    return out


# ------------------------------------------------------------------ NEEDS YOU
def needs(state: str, headline: str, detail: str, ignorable: list[str] | None = None,
          failed: list[dict] | None = None) -> list[dict]:
    """[{"title", "text", "ignore"}]: decisions the game holds for the player, then what failed this turn."""
    out = []
    d = detail or ""
    m = re.search(r"waiting for you: (.+?)(?:\n|$)", d)
    if state == "paused" and m:
        what = m.group(1)
        what = re.sub(r"\s*\([a-z_]+(?:, [a-z_]+)*\)", "", what).strip()
        held = "The other factions wait until you answer it." if "other factions" in d else \
            "The turn's steps wait until you deal with it."
        out.append({"title": what[:1].upper() + what[1:] + " is open", "text": held + " The assistant goes on once "
                    "it is closed.", "ignore": None})
    elif state == "paused" and "DECISION" not in headline.upper():
        out.append({"title": "The assistant is paused", "text": "Nothing runs until you press RESUME.", "ignore": None})
    for cid in ignorable or []:
        out.append({"title": f"A popup blocks the turn ({cid})", "text": "If it is harmless, ignore it and the turn's "
                    "steps go on.", "ignore": cid})
    for s in failed or []:
        out.append({"title": f"{s['name']} failed", "text": s["text"], "ignore": None})
    return out


# ------------------------------------------------------------------ ARMIES
def army_cards(rows, fin=None) -> list[dict]:
    """rows: [(army, delta, (can tick, why not))] (assist/app.py). Each army: its playbook units as have / want, the
    off-playbook units, the Warlock Engineer, where it is, its upkeep now and once refilled, and its refill switch."""
    from .army import load_automation, tick_for, enabled_armies
    t = load_automation()["army_builder"]["template"]
    cost = {c.cqi: c for c in (getattr(fin, "armies", None) or [])}
    ticked = enabled_armies()
    out = []
    for a, d, (can, why_not) in rows:
        troops = Counter(u.key for u in a.units if "_cha_" not in u.key)
        queued = Counter(k for k in getattr(a, "queued", []) if k and k != "?")
        units = []
        for key, want in t["units"].items():
            have = troops.get(key, 0)
            q = queued.get(key, 0)
            text = f"{have} / {want}" + (f"  (+{q} queued)" if q else "")
            units.append({"unit": unit_label(key), "count": text,
                          "state": "ok" if have + q >= want else "short"})
        for hero, want in t["heroes"].items():
            have = want - d.heroes_missing.get(hero, 0)
            label = "Warlock Engineer" if hero.endswith("warlock_engineer") else gd.loc().get(
                f"agent_subtypes_onscreen_name_override_{hero}", hero)
            units.append({"unit": label, "count": f"{have} / {want}", "state": "ok" if have >= want else "short"})
        for key, n in Counter(d.disband).items():
            units.append({"unit": f"{unit_label(key)} (not in the playbook)", "count": str(n), "state": "extra"})
        on, _why = tick_for(a, ticked)
        missing = sum(d.missing.values())
        if d.matches:
            status, tone = "Matches the playbook.", "good"
        elif not d.lord_ok:
            status, tone = "Its lord cannot lead a playbook army.", "muted"
        else:
            bits = []
            if missing:
                bits.append("Missing " + ", ".join(f"{n} {unit_label(k)}" for k, n in d.missing.items()) + ".")
            if d.disband:
                bits.append(f"The {len(d.disband)} off-playbook units go once their replacements can be recruited.")
            if d.heroes_missing:
                bits.append("Needs a Warlock Engineer.")
            status, tone = " ".join(bits) or "Off the playbook.", "ink"
        c = cost.get(a.cqi)
        upkeep = (f"{c.now:,}" + (f" now, {c.refilled:,} once refilled" if c.refilled != c.now else "")) if c else "—"
        size = f"{len(a.units)}" + (f" + {len(a.queued)} queued" if getattr(a, "queued", None) else "") + " / 20"
        out.append({"cqi": a.cqi, "name": a.general_name, "size": size, "where": _where(a), "units": units,
                    "status": status, "tone": tone, "upkeep": upkeep, "ticked": on, "matches": d.matches,
                    "can": bool(can), "why_not": (why_not or "").replace("cannot refill: ", ""), "army": a})
    return out


def _where(a) -> str:
    from bot.sensor.world import region_provinces
    prov = region_provinces()[0].get(a.region or "")
    r = region_name(a.region)
    return f"{r} ({province_name(prov)})" if prov else (r or "at sea or in the field")


# ------------------------------------------------------------------ ARMY BUILDER: in progress
def progress(w, F, rows, status: dict | None = None) -> list[dict]:
    """[{"name", "kind", "now", "next", "chips": [(text, ok)]}]: each ticked army that still needs units, and the
    armies asked for (status: army_finance.army_status). From memory: where the army stands, the province it recruits
    in this pass (army_builder.plan_provinces: one army per province), the closest free one it marches to."""
    from .army import enabled_armies, tick_for
    from .army_builder import closest_target, eligible, plan_provinces
    from .army import load_automation
    from bot.sensor.world import region_provinces
    prov_of = region_provinces()[0]
    ticked = enabled_armies()
    acting = [a for a, d, _c in rows if tick_for(a, ticked)[0]]
    plan = plan_provinces(w, F, acting) if acting else {}
    elig = eligible(w, F, set(load_automation()["army_builder"]["template"]["units"]))
    out = []
    for a, d, _c in rows:
        if a not in acting or (d.matches and not d.heroes_missing):
            continue
        here = prov_of.get(a.region or "")
        mine = next((p for p, n in plan.items() if n == a.general_name), None)
        need = ", ".join(f"{n} {unit_label(k)}" for k, n in d.missing.items())
        chips = []
        if mine and mine == here:
            q = len(getattr(a, "queued", []) or [])
            now = (f"Recruiting at {region_name(a.region)} ({province_name(here)}): {q} unit{'s' if q != 1 else ''} "
                   "in the queue." if q else f"At {region_name(a.region)} ({province_name(here)}): recruits {need} "
                   "at the next army step.")
            chips.append((f"Province: {province_name(here)}", True))
        elif mine:
            others = frozenset(p for p, n in plan.items() if n != a.general_name)
            tgt = closest_target(w, F, a, elig, skip=others)
            if tgt:
                region, province, hops = tgt
                now = f"Marching to {region_name(region)} ({province_name(province)}), {hops} regions away."
            else:
                now = f"Heading for {province_name(mine)}."
            chips.append((f"Province: {province_name(mine)}", True))
        else:
            now = ("Waiting: every province that recruits the whole playbook is recruiting for another army."
                   if elig else "Waiting: no province recruits the whole playbook yet.")
            chips.append(("Province: none free", False))
        nxt = []
        if need:
            nxt.append(f"Then: recruit {need}")
        if d.disband:
            nxt.append(f"disband {len(d.disband)} off-playbook units")
        if d.heroes_missing:
            nxt.append("get a Warlock Engineer")
            chips.append(("Engineer: needed", False))
        else:
            chips.append(("Engineer: has one", True))
        out.append({"name": a.general_name, "kind": "Refill", "now": now,
                    "next": (", ".join(nxt) + ".") if nxt else "", "chips": chips})
    if status:
        req, can = status.get("requested", 0), status.get("can_raise", 0)
        for i in range(min(req, can)):
            out.append({"name": f"New army {i + 1}", "kind": "New army",
                        "now": "Raised at your next Build & End Turn: a Verminlord Warpseer in a free recruiting "
                               "province, then the playbook recruited there.",
                        "next": "Its Warlock Engineer is recruited the same turn.", "chips": [("Ready to raise", True)]})
        if req > can:
            lim = status.get("limits", {})
            short = [k for k, v in lim.items() if v <= 0]
            out.append({"name": f"{req - can} more asked for", "kind": "Waiting",
                        "now": "Raised once a free recruiting province, a Warlock Engineer and a Warpseer are there.",
                        "next": ("Short of: " + ", ".join(short) + ".") if short else "",
                        "chips": [(f"{k}: {v}", v > 0) for k, v in lim.items()]})
    return out


# ------------------------------------------------------------------ the collapsed bar's line
def bar_line(state: str, detail: str, needs_list: list[dict], progress_list: list[dict], build_line: str = "") -> str:
    """One line for the collapsed bar: what needs the player first, then what failed, then what is in progress."""
    if state == "automating":
        return "Hands off the mouse until it is done. Shift+Esc stops it."
    if needs_list:
        n = needs_list[0]
        return f"{n['title']}: {n['text']}"
    bits = []
    for p in progress_list[:2]:
        bits.append(f"{p['name']}: {p['now']}")
    if build_line:
        bits.append(build_line)
    if bits:
        return " ".join(bits)
    first = next((ln for ln in (detail or "").splitlines() if ln.strip()), "")
    return _nice(first)


def next_build(lines: list[str]) -> str:
    """"Next build: <item> (<when>)" from the buildings line's "saving for ...", or ""."""
    for line in lines or []:
        if line.lower().startswith("buildings:") and "saving for " in line:
            m = re.search(r"saving for ([^,(|]+)\(in (\d+) turn", line)
            if m:
                return f"Next build: {m.group(1).strip()} in {m.group(2)} turn(s)."
    return ""
