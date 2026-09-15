from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

VK_CONTROL = 0x11
VK_A = 0x41
VK_V = 0x56
VK_RETURN = 0x0D

ULONG_PTR = wintypes.WPARAM

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]
    _anonymous_ = ("_input",)
    _fields_ = [("type", wintypes.DWORD), ("_input", _INPUT)]


def _send_vk(vk: int, key_up: bool = False) -> None:
    flags = KEYEVENTF_KEYUP if key_up else 0
    inp = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, 0, flags, 0, 0))
    sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def ctrl_a() -> None:
    """Send Ctrl+A using fixed virtual-key codes; independent of active layout."""
    _send_vk(VK_CONTROL)
    _send_vk(VK_A)
    _send_vk(VK_A, True)
    _send_vk(VK_CONTROL, True)


def ctrl_v() -> None:
    """Send Ctrl+V using fixed virtual-key codes; independent of active layout."""
    _send_vk(VK_CONTROL)
    _send_vk(VK_V)
    _send_vk(VK_V, True)
    _send_vk(VK_CONTROL, True)


def enter() -> None:
    """Send Enter using a fixed virtual-key code."""
    _send_vk(VK_RETURN)
    _send_vk(VK_RETURN, True)
