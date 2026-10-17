"""Kill switch: a physical Shift+Esc ends this process at once (player request, 2026-10-16: "so i can back out if
something goes wrong during testing").

Installed by bot/focus.py at import, so every process that can send input to the game has it: the assistant app
(assist.runner), the test driver, benchmarks and ad-hoc test scripts. Each process watches the keyboard itself with
a low-level keyboard hook (WH_KEYBOARD_LL; every process gets every key event, so one press ends all of them) on
its own thread. On Shift+Esc it releases the mouse buttons and the keys the automation holds (WASD, Ctrl, Alt),
then calls os._exit: no cleanup code runs, nothing else is clicked.

Only a physical key press counts: injected input (our own SendInput/keybd_event, other tools) is ignored, so the
automation can never trigger it by itself. The Escape of the combination is swallowed (the game would open its
menu); Escape alone and Shift alone pass through untouched.

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
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
VK_ESCAPE, VK_SHIFT = 0x1B, 0x10
LLKHF_INJECTED = 0x10
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTUP, MOUSEEVENTF_RIGHTUP, MOUSEEVENTF_MIDDLEUP = 0x0004, 0x0010, 0x0040
RELEASE_VKS = (0x57, 0x41, 0x53, 0x44, 0x11, 0x12)        # W A S D Ctrl Alt (Shift is the player's own key)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
LRESULT = ctypes.c_ssize_t


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


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


def _fire() -> None:
    try:
        _release_inputs()
        sys.stderr.write(f"\nKILL SWITCH (Shift+Esc): process {os.getpid()} terminated\n")
        sys.stderr.flush()
    finally:
        os._exit(130)


def physical_key_age() -> float:
    """Seconds since the player last pressed or released a key (physical input only; inf if never seen)."""
    return time.monotonic() - _last_key if _last_key else float("inf")


def _on_key(n_code, w_param, l_param):
    global _last_key
    if n_code == 0:
        k = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        if not k.flags & LLKHF_INJECTED:
            _last_key = time.monotonic()        # the player is at the keyboard (tools/ui.py yields to them)
    if n_code == 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
        k = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        if (k.vkCode == TRIGGER_VK and _user32.GetAsyncKeyState(VK_SHIFT) & 0x8000
                and (TEST or not k.flags & LLKHF_INJECTED)):
            _fire()
            return 1
    return _user32.CallNextHookEx(None, n_code, w_param, l_param)


def _pump(ready: threading.Event) -> None:
    global _proc
    _proc = HOOKPROC(_on_key)
    hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, _proc, _kernel32.GetModuleHandleW(None), 0)
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
