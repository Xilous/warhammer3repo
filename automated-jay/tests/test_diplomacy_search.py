"""The payment search (assist/diplomacy.most_they_pay) against a simulated payment window: lowest first (player
request 2026-10-21): a refusal at 1 gold costs no probe, then +200 arrow steps, then the last 200 narrowed from the
linear estimate (a line fitted through every arrow step's value). The answer must be exact and the typed
probes few: about 6.5 on average for an accepted deal (typed amounts are slow: the game drops fast typing; the
panel's 0.1 rounding leaves the line's zero about +-8 gold uncertain).

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist import diplomacy as d


class Window:
    """Value = base - k * amount (as Wissenland's join war: 3.8377 - 0.0065297 * gold), shown to 0.1; the game caps
    the amount at `top`."""

    def __init__(self, base, k=0.0065297, top=2000):
        self.base, self.k, self.top, self.amount = base, k, top, 1
        self.typed = self.steps = 0

    def value(self):
        return self.base - self.k * self.amount


@pytest.fixture
def win(monkeypatch):
    holder = {}

    def setup(base, **kw):
        w = Window(base, **kw)
        holder["w"] = w
        monkeypatch.setattr(d, "_option", lambda ui, kind: object())
        monkeypatch.setattr(d, "click", lambda ui, c: None)
        monkeypatch.setattr(d.wait, "wait_until", lambda *a, **k: True)
        monkeypatch.setattr(d.wait, "next_frame", lambda *a, **k: None)
        monkeypatch.setattr(d.wait, "state_is", lambda *a, **k: True)
        fake = type("U", (), {"first": lambda self, *a, **k: None, "state": lambda self, c: "active"})()
        holder["ui"] = fake
        monkeypatch.setattr(d, "_amount", lambda ui: w.amount)

        def set_amount(ui, x):
            w.typed += 1
            w.amount = min(max(1, x), w.top)
            return w.amount

        def step(ui):
            w.steps += 1
            if w.amount >= w.top:
                return None
            w.amount = min(w.amount + 200, w.top)
            return w.amount
        monkeypatch.setattr(d, "set_amount", set_amount)
        monkeypatch.setattr(d, "_step_up", step)
        monkeypatch.setattr(d, "payment_positive", lambda ui: w.value() > 0)
        monkeypatch.setattr(d, "payment_value", lambda ui: round(w.value(), 1))
        return w
    return lambda base, **kw: (setup(base, **kw), holder["ui"])


def best(w):
    return max(a for a in range(1, w.top + 1) if w.base - w.k * a > 0)


@pytest.mark.parametrize("base", [3.8377, 7.2, 0.5, 1.31, 9.9, 13.05])
def test_exact_and_few_typed_probes(win, base):
    w, ui = win(base)
    got = d.most_they_pay(ui, 5000)
    assert got == best(w)
    assert w.typed <= 11, (w.typed, w.steps)


def test_few_typed_probes_on_average(win):
    typed = []
    for i in range(1, 200):
        w, ui = win(i * 0.065)
        assert d.most_they_pay(ui, 5000) == best(w)
        typed.append(w.typed)
    assert sum(typed) / len(typed) < 7             # 6.5 measured: the 0.1 rounding leaves about +-8 gold


def test_refusal_at_one_gold_costs_nothing(win):
    w, ui = win(-0.2)
    assert d.most_they_pay(ui, 5000) is None
    assert w.typed == 0 and w.steps == 0


def test_all_of_the_maximum(win):
    w, ui = win(50.0)
    assert d.most_they_pay(ui, 5000) == 2000


def test_their_treasury_caps_it(win):
    w, ui = win(50.0)
    assert d.most_they_pay(ui, 600) in (601, 600)
