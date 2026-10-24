"""The emergency brake (player request 2026-10-23): in the assistant app Shift+Esc stops the running pass and releases
the hold, and the process keeps running.

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import focus, killswitch


def test_brake_stops_a_pass_and_keeps_the_process(monkeypatch):
    monkeypatch.setattr(killswitch, "BRAKE", True)
    monkeypatch.setattr(killswitch, "_release_inputs", lambda: None)
    killswitch.hold_mouse(True, 5)
    focus._tls.brakes0 = killswitch.brakes()
    try:
        focus.check_brake()                       # not pulled yet: nothing happens
        killswitch._fire()                        # returns (no os._exit)
        assert not killswitch.mouse_held()        # the hold is released
        with pytest.raises(focus.EmergencyBrake):
            focus.check_brake()
        assert issubclass(focus.EmergencyBrake, focus.InputAborted)
    finally:
        focus._tls.brakes0 = None
    focus.check_brake()                           # outside a pass: a brake pulled earlier stops nothing new
