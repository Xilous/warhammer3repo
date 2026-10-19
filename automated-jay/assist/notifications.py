"""End-turn notifications off (player request 2026-10-19, multiplayer turn 1: a "building can be upgraded"
notification sat over the End Turn button and took the assistant's End Turn click).

The game's notification list sits above End Turn (hud_campaign/.../notification_frame, button_notification). Its
settings open from button_notification_settings (bottom right, next to the list): notification_settings_container,
whose list (notification_settings_list, one CcoEndTurnNotificationRecord per notification type the player can
suppress) has a "Disable all" button. The setting is the player's UI preference, so it lives only in the UI: the
panel is opened, "Disable all" pressed when any notification is still on, and the panel closed again. Done once per
campaign (checked again after a restart of the assistant).
"""
from __future__ import annotations

from tools import wait
from tools.ui import click, move_to

SETTINGS_BUTTON = "button_notification_settings"
CONTAINER = "notification_settings_container"
LIST = "notification_settings_list"
DISABLE_TEXT = "disable all"
_DONE: set = set()                 # campaign models whose notifications were turned off


def _texts(ui, ptr: int) -> str:
    return " ".join(t for b, _n, _r in ui.nodes(ptr) if (t := ui.text(b))).lower()


def _disable_button(ui, cont: int) -> int | None:
    """The button under the container whose own texts read "Disable all"."""
    for c, cid, _r in ui.nodes(cont):
        if cid and (cid.startswith("button") or "toggle" in cid) and DISABLE_TEXT in _texts(ui, c):
            return c
    return None


def _toggles_on(ui, cont: int) -> int:
    """How many notification types in the list are still on (their toggle in a selected / ticked state)."""
    lst = ui.first(LIST, under=cont)
    n = 0
    for c, cid, _r in (ui.nodes(lst) if lst else []):
        if cid and ("toggle" in cid or "checkbox" in cid):
            st = ui.state(c) or ""
            if st.startswith("selected") or st in ("on", "ticked", "active_selected"):
                n += 1
    return n


def ensure_off(ui, model) -> str:
    """Notifications turned off for this campaign. -> a result line ("" when nothing needed doing)."""
    if model in _DONE:
        return ""
    btn = ui.cached(SETTINGS_BUTTON, under="hud_campaign")
    if btn is None:
        return "notifications: the settings button is not shown"
    click(ui, btn)
    cont = wait.wait_until(lambda: (lambda c: c if c and ui.effective_visible(c) else None)(ui.first(CONTAINER)),
                           2.0, "notification settings", must=False)
    if cont is None:
        return "notifications: the settings did not open"
    wait.stable(lambda: tuple(cid for _c, cid, _r in ui.nodes(cont)), n=3, timeout=1.5, ui=ui, must=False,
                what="notification settings listed")
    on = _toggles_on(ui, cont)
    out = "notifications: already off"
    if on:
        dis = _disable_button(ui, cont)
        if dis is None:
            out = f"notifications: {on} on, no Disable all button found"
        else:
            click(ui, dis)
            wait.wait_until(lambda: _toggles_on(ui, cont) == 0, 3.0, "notifications off", must=False)
            left = _toggles_on(ui, cont)
            out = "notifications: turned off" if left == 0 else f"notifications: {left} still on after Disable all"
    click(ui, btn)                                  # the same button closes the settings
    wait.wait_until(lambda: not (ui.first(CONTAINER) and ui.effective_visible(ui.first(CONTAINER))), 2.0,
                    "notification settings closed", must=False)
    move_to(960, 1070)
    if "still on" not in out and "no Disable" not in out:
        _DONE.add(model)
    return out
