"""Each press asks for one more playbook army; presses add up (player choice 2026-10-24).

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assist import new_army as N


def test_requests_add_up(monkeypatch, tmp_path):
    f = tmp_path / "raise_army.request"
    monkeypatch.setattr(N, "_request_file", lambda: f)
    assert N.requested() == 0
    N.request_raise()
    N.request_raise()
    assert N.requested() == 2
    N._set_requested(N.requested() - 1)
    assert N.requested() == 1
    N._set_requested(0)
    assert N.requested() == 0 and not f.exists()
