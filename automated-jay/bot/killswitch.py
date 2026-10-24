"""Kill switch, and the player's hands: a physical Shift+Esc ends this process at once (player request, 2026-10-16: "so i can back out if
something goes wrong during testing"). In the assistant app (BRAKE = True, set by assist.runner main) it is an
emergency brake instead (player request 2026-10-23): the hold ends, held keys and buttons are released and the running
pass stops, but the assistant keeps running; test scripts still end.

Installed by bot/focus.py at import, so every process that can send input to the game has it: the assistant app
(assist.runner), the test driver, benchmarks and ad-hoc test scripts. Each process watches the keyboard itself with
a low-level keyboard hook (WH_KEYBOARD_LL; every process gets every key event, so one press ends all of them) on
its own thread. On Shift+Esc it releases the mouse buttons and the keys the automation holds (WASD, Ctrl, Alt),
then calls os._exit: no cleanup code runs, nothing else is clicked.

Only a physical key press counts: injected input (our own SendInput/keybd_event, other tools) is ignored, so the
automation can never trigger it by itself. The Escape of the combination is swallowed (the game would open its
menu); Escape alone and Shift alone pass through untouched.

The same thread also watches the mouse (WH_MOUSE_LL): it records when the player last clicked (physical button or
wheel events; moving the mouse does not count), and while the assistant holds the game (bot/focus.game_focus,
hold_mouse) it swallows the player's physical mouse events, so a pass cannot be disturbed (player request
2026-10-17). Our own clicks are injected and pass through; SetCursorPos is not a mouse event at all. A hold expires
by itself after HOLD_MAX_S, and ends with the process, so the mouse can never stay locked.

    KILLSWITCH_TEST=1     test mode, for checking the switch itself: the trigger is Shift+F24 (no program uses F24,
                          so an injected test press cannot reach anything else) and injected input counts
"""
from __future__ import annotations
import ctypes
import os
import sys
import threading
import time
from ctypes import wintypes

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
LLMHF_INJECTED, LLMHF_LOWER_IL_INJECTED = 0x1, 0x2
CLICK_MSGS = {0x0201, 0x0202, 0x0203, 0x0204, 0x0205, 0x0206, 0x0207, 0x0208, 0x0209, 0x020A, 0x020B, 0x020C, 0x020D,
              0x020E}               # button down/up/double-click (left, right, middle, X) and both wheels
UP_MSGS = {0x0202, 0x0205, 0x0208, 0x020C}   # button releases always pass: a press that began before a hold (the
                                            # click on Build & End Turn) must not leave a button stuck down
HOLD_MAX_S = 300.0                # a hold of the mouse ends by itself after this long, whatever happens
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
VK_ESCAPE, VK_SHIFT = 0x1B, 0x10
LLKHF_INJECTED = 0x10
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTUP, MOUSEEVENTF_RIGHTUP, MOUSEEVENTF_MIDDLEUP = 0x0004, 0x0010, 0x0040
SHIFT_VKS = (0x10, 0xA0, 0xA1)    # Shift, left Shift, right Shift
RELEASE_VKS = (0x57, 0x41, 0x53, 0x44, 0x11, 0x12)        # W A S D Ctrl Alt (Shift is the player's own key)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
LRESULT = ctypes.c_ssize_t


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
_user32.CallNextHookEx.restype = LRESULT
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short
_user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE

_installed = False
_last_key = 0.0                   # time.monotonic() of the player's last physical key event
_shift_down = False               # the player's Shift, from the hook itself (held input never updates key state)
_last_click = 0.0                 # ... and of their last physical mouse button / wheel event
_hold_until = 0.0                 # while time.monotonic() < this, the player's physical mouse events are swallowed
_mproc = None
_lock = threading.Lock()
_proc = None                      # the ctypes callback: must stay referenced for the life of the hook
TEST = os.environ.get("KILLSWITCH_TEST") == "1"
TRIGGER_VK = 0x87 if TEST else VK_ESCAPE              # VK_F24 in test mode


def _release_inputs() -> None:
    """Let go of everything the automation might be holding, so the player gets mouse and keyboard back clean."""
    for flag in (MOUSEEVENTF_LEFTUP, MOUSEEVENTF_RIGHTUP, MOUSEEVENTF_MIDDLEUP):
        _user32.mouse_event(flag, 0, 0, 0, 0)
    for vk in RELEASE_VKS:
        if _user32.GetAsyncKeyState(vk) & 0x8000:
            _user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


BRAKE = False                     # the assistant app sets this: Shift+Esc is an emergency brake there, not an exit
_brakes = 0                       # how many times the brake was pulled in this process (bot/focus.check_brake)


def brakes() -> int:
    return _brakes


def _fire() -> None:
    global _brakes, _hold_until
    if BRAKE:
        # the emergency brake (player request 2026-10-23: "shift esc shouldnt terminate the assistant, it should just
        # cancel the hold and cancel the automations"): mouse and keyboard back at once, and the running pass stops
        # at its next input or wait (bot/focus.check_brake raises EmergencyBrake); the process keeps running
        _release_inputs()
        _hold_until = 0.0
        _brakes += 1
        sys.stderr.write("\nEMERGENCY BRAKE (Shift+Esc): mouse and keyboard released, automations stopped\n")
        sys.stderr.flush()
        return
    try:
        _release_inputs()
        sys.stderr.write(f"\nKILL SWITCH (Shift+Esc): process {os.getpid()} terminated\n")
        sys.stderr.flush()
    finally:
        os._exit(130)


def physical_click_age() -> float:
    """Seconds since the player last clicked or turned the wheel (physical only; moving the mouse does not count)."""
    return time.monotonic() - _last_click if _last_click else float("inf")


def hold_mouse(on: bool, seconds: float = HOLD_MAX_S) -> None:
    """Take mouse and keyboard away from the player (their physical moves, clicks and key presses are swallowed;
    releases pass, and Shift+Esc always works) or give them back. Player request 2026-10-17: a pass must not be
    interruptible, the turn-start one included."""
    global _hold_until
    _hold_until = time.monotonic() + min(seconds, HOLD_MAX_S) if on else 0.0


def mouse_held() -> bool:
    return time.monotonic() < _hold_until


def _on_mouse(n_code, w_param, l_param):
    global _last_click
    if n_code == 0:
        m = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        if not m.flags & (LLMHF_INJECTED | LLMHF_LOWER_IL_INJECTED):
            if w_param in CLICK_MSGS:
                _last_click = time.monotonic()
            if time.monotonic() < _hold_until and w_param not in UP_MSGS:
                return 1                   # the assistant has the game: the player's mouse waits
    return _user32.CallNextHookEx(None, n_code, w_param, l_param)


def physical_key_age() -> float:
    """Seconds since the player last pressed or released a key (physical input only; inf if never seen)."""
    return time.monotonic() - _last_key if _last_key else float("inf")


def _on_key(n_code, w_param, l_param):
    global _last_key, _shift_down
    if n_code == 0:
        k = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        physical = not k.flags & LLKHF_INJECTED
        down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
        if physical:
            _last_key = time.monotonic()        # the player is at the keyboard (tools/ui.py yields to them)
            if k.vkCode in SHIFT_VKS:           # tracked here: while held, Shift never reaches the system
                _shift_down = down
        if down and k.vkCode == TRIGGER_VK and (TEST or physical) and (
                _shift_down or _user32.GetAsyncKeyState(VK_SHIFT) & 0x8000):
            _fire()
            return 1
        if physical and down and time.monotonic() < _hold_until:
            return 1                            # the assistant has the game: the player's keys wait (releases pass)
    return _user32.CallNextHookEx(None, n_code, w_param, l_param)


def _pump(ready: threading.Event) -> None:
    global _proc, _mproc
    _proc = HOOKPROC(_on_key)
    hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, _proc, _kernel32.GetModuleHandleW(None), 0)
    _mproc = HOOKPROC(_on_mouse)
    if not _user32.SetWindowsHookExW(WH_MOUSE_LL, _mproc, _kernel32.GetModuleHandleW(None), 0):
        sys.stderr.write(f"WARNING: mouse watch not installed (error {ctypes.get_last_error()})" + chr(10))
    ready.set()
    if not hook:
        sys.stderr.write(f"WARNING: kill switch (Shift+Esc) not installed (error {ctypes.get_last_error()})\n")
        return
    msg = wintypes.MSG()
    while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:      # the hook is called from this loop
        _user32.TranslateMessage(ctypes.byref(msg))
        _user32.DispatchMessageW(ctypes.byref(msg))


def install() -> None:
    """Arm the kill switch for this process (idempotent; returns once the hook is in place)."""
    global _installed
    with _lock:
        if _installed:
            return
        _installed = True
    ready = threading.Event()
    threading.Thread(target=_pump, args=(ready,), name="killswitch", daemon=True).start()
    ready.wait(2.0)


def main() -> int:
    """python -X utf8 -m bot.killswitch [seconds]: try the mouse hold by hand (your mouse is held for that long;
    Shift+Esc ends it at once)."""
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    install()
    print(f"your mouse is held for {seconds:.0f} s: try moving and clicking (Shift+Esc ends it at once)", flush=True)
    hold_mouse(True, seconds)
    while mouse_held():
        time.sleep(0.05)
    print(f"released; last click seen {physical_click_age():.1f} s ago", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
