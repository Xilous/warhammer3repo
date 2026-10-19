"""End-turn notifications off (player request 2026-10-19, multiplayer turn 1: a "building can be upgraded"
notification sat over the End Turn button and took the assistant's End Turn click).

The game's notification list sits above End Turn (hud_campaign/.../notification_frame, button_notification). Its
settings open from button_notification_settings (bottom right, next to the list): notification_settings_container,
whose list (notification_settings_list, one CcoEndTurnNotificationRecord per notification type the player can
suppress) has a "Disable all" button. The setting is the player's UI preference, so it lives only in the UI: the
panel is opened, "Disable all" pressed when any notification is still on, and the panel closed again. Checked on every pass:
the settings are opened only while a notification shows.
"""
from __future__ import annotations

from tools import wait
from tools.ui import click, move_to

SETTINGS_BUTTON = "button_notification_settings"
CONTAINER = "notification_settings_container"
LIST = "notification_settings_list"
DISABLE_TEXT = "disable all"


def _texts(ui, ptr: int) -> str:
    return " ".join(t for b, _n, _r in ui.nodes(ptr) if (t := ui.text(b))).lower()


def _disable_button(ui, cont: int) -> int | None:
    """The button under the container whose own texts read "Disable all"."""
    for c, cid, _r in ui.nodes(cont):
        if cid and (cid.startswith("button") or "toggle" in cid) and DISABLE_TEXT in _texts(ui, c):
            return c
    return None


def _toggles(ui, cont: int) -> tuple[int, int]:
    """(notification types listed, how many of them are on: checkbox_toggle state "selected", read live
    2026-10-19). (0, 0) while the list is still being built."""
    lst = ui.first(LIST, under=cont)
    total = on = 0
    for c, cid, _r in (ui.nodes(lst) if lst else []):
        if cid == "checkbox_toggle":
            total += 1
            on += (ui.state(c) or "").startswith("selected")
    return total, on


NONE_TEXT = "end turn"          # what dy_notification reads with no notification left (seen live 2026-10-19)


def showing(ui) -> str:
    """The notification the HUD shows above End Turn ("Lord not moved"), or "" when none is."""
    d = ui.cached("dy_notification", under="hud_campaign")
    t = (ui.text(d) or "").strip() if d and ui.effective_visible(d) else ""
    return "" if t.lower() == NONE_TEXT else t


UNSUPPRESSIBLE: set = set()      # notifications still shown with every toggle off (not in the settings list)


def ensure_off(ui, model=None) -> str:
    """Notifications off whenever one shows (player report 2026-10-19: a new campaign had them on again and the
    assistant, having done it once in the previous campaign, did not look). -> a result line, "" when none shows.
    The settings are opened only when a notification is showing, so a pass with none costs no input."""
    shown = showing(ui)
    if not shown or shown in UNSUPPRESSIBLE:
        return ""
    btn = ui.cached(SETTINGS_BUTTON, under="hud_campaign")
    if btn is None:
        return "notifications: the settings button is not shown"
    click(ui, btn)
    cont = wait.wait_until(lambda: (lambda c: c if c and ui.effective_visible(c) else None)(ui.first(CONTAINER)),
                           2.0, "notification settings", must=False)
    if cont is None:
        return "notifications: the settings did not open"
    # the list fills in after the panel shows: wait for its toggles, then for the count to hold (2026-10-19: read
    # empty, taken for "already off")
    wait.wait_until(lambda: _toggles(ui, cont)[0] > 0, 2.0, "notification toggles listed", must=False)
    wait.stable(lambda: _toggles(ui, cont), n=3, timeout=1.5, ui=ui, must=False, what="notification toggles")
    total, on = _toggles(ui, cont)
    if total == 0:
        out = "notifications: the settings list did not fill in"
    elif on:
        dis = _disable_button(ui, cont)
        if dis is None:
            out = f"notifications: {on} on, no Disable all button found"
        else:
            click(ui, dis)
            wait.wait_until(lambda: _toggles(ui, cont)[1] == 0, 3.0, "notifications off", must=False)
            left = _toggles(ui, cont)[1]
            out = "notifications: turned off" if left == 0 else f"notifications: {left} still on after Disable all"
    else:
        out = ""
    click(ui, btn)                                  # the same button closes the settings
    wait.wait_until(lambda: not (ui.first(CONTAINER) and ui.effective_visible(ui.first(CONTAINER))), 2.0,
                    "notification settings closed", must=False)
    move_to(960, 1070)
    if total and not _toggles_off_left(on, out) and wait.wait_until(lambda: not showing(ui), 1.5,
                                                                    "notification gone", must=False) is None:
        UNSUPPRESSIBLE.add(shown)                  # every toggle off and it still shows: not a setting
        out = (out + "; " if out else "notifications: ") + f'"{shown}" is not one the settings can turn off'
    return out


def _toggles_off_left(on: int, out: str) -> bool:
    return "still on" in out or "no Disable" in out
