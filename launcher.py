from __future__ import annotations

import ctypes
import json
import locale
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

from utils.keyboard import force_english_layout
from utils.logger import get_logger


PROJECT_DIR = Path(__file__).resolve().parent
MAIN_SCRIPT = PROJECT_DIR / "main.py"
PYTHON_EXE = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

WM_SYSCOMMAND = 0x0112
SC_MONITORPOWER = 0xF170
HWND_BROADCAST = 0xFFFF
MONITOR_POWER_ON = -1


logger = get_logger()
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    _anonymous_ = ("_input",)
    _fields_ = [("type", ctypes.c_ulong), ("_input", _INPUT)]


INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001


kernel32.SetThreadExecutionState.argtypes = [ctypes.c_uint]
kernel32.SetThreadExecutionState.restype = ctypes.c_uint

user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = ctypes.c_bool
user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = ctypes.c_uint
user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
user32.SendMessageW.restype = ctypes.c_long


def _load_settings() -> dict:
    path = PROJECT_DIR / "config" / "settings.json"
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def set_execution_state(*, system_required: bool, display_required: bool) -> None:
    """Keep Windows awake and/or keep the display powered on for this launcher thread."""
    flags = ES_CONTINUOUS
    if system_required:
        flags |= ES_SYSTEM_REQUIRED
    if display_required:
        flags |= ES_DISPLAY_REQUIRED

    previous = kernel32.SetThreadExecutionState(flags)
    if previous == 0:
        raise ctypes.WinError(ctypes.get_last_error())

    logger.info(
        "Power state request updated: system_required=%s, display_required=%s.",
        system_required,
        display_required,
    )


def clear_execution_state() -> None:
    """Return power-management control to Windows defaults."""
    previous = kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    if previous == 0:
        logger.warning("Could not clear launcher execution-state request: %s", ctypes.WinError(ctypes.get_last_error()))
    else:
        logger.info("Launcher power-management request cleared.")


def wake_display() -> None:
    """Ask Windows to power the monitor and generate a tiny synthetic mouse move.

    The Task Scheduler documentation explicitly notes that a scheduled wake can
    leave the screen off even though Windows has already resumed. The monitor-power
    request and mouse nudge are therefore used together as a best-effort wake-up.
    """
    try:
        user32.SendMessageW(
            ctypes.c_void_p(HWND_BROADCAST),
            WM_SYSCOMMAND,
            ctypes.c_void_p(SC_MONITORPOWER),
            ctypes.c_void_p(MONITOR_POWER_ON),
        )
        logger.info("Sent Windows monitor-power ON request after wake.")
    except Exception as exc:
        logger.warning("Could not send monitor-power ON request: %s", exc)

    point = POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        logger.warning("Could not read the current cursor position for the display wake nudge.")
        return

    mouse = INPUT(
        type=INPUT_MOUSE,
        mi=MOUSEINPUT(
            dx=1,
            dy=0,
            mouseData=0,
            dwFlags=MOUSEEVENTF_MOVE,
            time=0,
            dwExtraInfo=None,
        ),
    )

    sent = user32.SendInput(1, ctypes.byref(mouse), ctypes.sizeof(INPUT))
    if sent != 1:
        logger.warning("Could not generate the synthetic mouse wake nudge: %s", ctypes.WinError(ctypes.get_last_error()))
        return

    logger.info("Sent a 1-pixel synthetic mouse movement to wake the display.")


def _run_netsh(*args: str) -> tuple[bytes, int]:
    completed = subprocess.run(
        ["netsh", *args],
        capture_output=True,
        text=False,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    output = (completed.stdout or b"") + (b"\n" + completed.stderr if completed.stderr else b"")
    return output, completed.returncode


def _decode_netsh_output(raw: bytes) -> str:
    if not raw:
        return ""

    encodings: list[str] = []
    preferred = locale.getpreferredencoding(False)
    if preferred:
        encodings.append(preferred)
    encodings.extend(["oem", "cp866", "cp1251", "utf-8"])

    seen: set[str] = set()
    for encoding in encodings:
        if encoding in seen:
            continue
        seen.add(encoding)
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue

    return raw.decode("utf-8", errors="replace")


def _netsh_text(*args: str) -> tuple[str, int]:
    raw, returncode = _run_netsh(*args)
    return _decode_netsh_output(raw), returncode


def has_internet(timeout: float = 4.0) -> bool:
    urls = (
        "https://www.msftconnecttest.com/connecttest.txt",
        "https://www.google.com/generate_204",
    )
    for url in urls:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if 200 <= response.status < 400:
                    return True
        except Exception:
            continue
    return False


def current_wifi_ssid() -> Optional[str]:
    output, _ = _netsh_text("wlan", "show", "interfaces")
    match = re.search(r"(?im)^\s*SSID\s*:\s*(.*?)\s*$", output)
    if not match:
        return None

    ssid = match.group(1).strip()
    return ssid or None


def wifi_is_connected() -> bool:
    return current_wifi_ssid() is not None


def connected_to_ssid(expected_ssid: str) -> bool:
    actual = current_wifi_ssid()
    return actual is not None and actual.casefold() == expected_ssid.casefold()


def find_target_ssids(preferred: str, fallback: str) -> tuple[str, ...]:
    output, _ = _netsh_text("wlan", "show", "networks", "mode=bssid")
    normalized = output.casefold()
    found: list[str] = []
    for ssid in (preferred, fallback):
        if ssid.casefold() in normalized:
            found.append(ssid)
    return tuple(found)


def connect_to_saved_wifi(ssid: str) -> bool:
    logger.info("Attempting to connect to Wi-Fi profile '%s'.", ssid)

    if connected_to_ssid(ssid):
        logger.info("Windows is already connected to '%s'.", ssid)
        return True

    raw_output, returncode = _run_netsh("wlan", "connect", f"name={ssid}")
    output = _decode_netsh_output(raw_output)

    if returncode == 0:
        logger.info("Windows accepted the connection request for '%s' (netsh exit code 0).", ssid)
        return True

    logger.warning(
        "Windows rejected connection request for '%s' (exit code %s). Output: %s",
        ssid,
        returncode,
        " ".join(output.split())[:500],
    )
    return False


def ensure_network_ready(settings: dict) -> None:
    network = settings.get("network", {})
    preferred_5g = str(network.get("preferred_ssid", "TP-Link_292C_5G"))
    fallback_24g = str(network.get("fallback_ssid", "TP-Link_292C"))
    scan_interval = max(1.0, float(network.get("scan_interval_seconds", 5)))
    connect_wait = max(5.0, float(network.get("connection_wait_seconds", 120)))
    connection_poll = max(0.5, float(network.get("connection_poll_seconds", 2)))
    post_connection_wait = max(0.0, float(network.get("post_connection_wait_seconds", 5)))

    logger.info(
        "Network readiness check: preferred=%s, fallback=%s.",
        preferred_5g,
        fallback_24g,
    )

    initial_ssid = current_wifi_ssid()
    if initial_ssid:
        logger.info("Current Wi-Fi SSID: '%s'.", initial_ssid)
    else:
        logger.info("No currently connected Wi-Fi SSID detected.")

    if wifi_is_connected() and has_internet():
        logger.info("Wi-Fi is connected and internet access is available. Continuing.")
        return

    if wifi_is_connected() and not has_internet():
        logger.warning(
            "Wi-Fi '%s' is connected, but internet access is unavailable. Searching for target Wi-Fi networks.",
            current_wifi_ssid() or "unknown",
        )
    else:
        logger.warning("No active Wi-Fi connection with internet detected. Searching for target Wi-Fi networks.")

    while True:
        available = find_target_ssids(preferred_5g, fallback_24g)
        if not available:
            logger.info(
                "Neither target network is currently visible. Retrying Wi-Fi scan in %.1f seconds.",
                scan_interval,
            )
            time.sleep(scan_interval)
            continue

        logger.info("Target Wi-Fi networks visible in preference order: %s", ", ".join(available))

        for ssid in available:
            if not connect_to_saved_wifi(ssid):
                continue

            logger.info("Waiting up to %.1f seconds for Wi-Fi '%s' + internet.", connect_wait, ssid)
            deadline = time.monotonic() + connect_wait
            while time.monotonic() < deadline:
                actual_ssid = current_wifi_ssid()
                internet = has_internet()

                if actual_ssid:
                    logger.info(
                        "Network status while waiting for '%s': current_ssid='%s', internet=%s",
                        ssid,
                        actual_ssid,
                        internet,
                    )

                if connected_to_ssid(ssid) and internet:
                    logger.info(
                        "Internet connection established through '%s'. Waiting %.1f seconds before launching TikTok.",
                        ssid,
                        post_connection_wait,
                    )
                    time.sleep(post_connection_wait)
                    return

                time.sleep(connection_poll)

            logger.warning(
                "Wi-Fi '%s' did not become ready in time. Current SSID: '%s'.",
                ssid,
                current_wifi_ssid() or "none",
            )

        logger.warning(
            "Target Wi-Fi was found, but the selected connection was not ready. Rescanning in %.1f seconds.",
            scan_interval,
        )
        time.sleep(scan_interval)


def launch_main() -> int:
    settings = _load_settings()
    launcher = settings.get("launcher", {})
    python_exe = PYTHON_EXE if PYTHON_EXE.exists() else Path(sys.executable)

    startup_delay = max(0.0, float(launcher.get("startup_delay_seconds", 1.0)))
    post_wake_wait = max(0.0, float(launcher.get("post_wake_wait_seconds", 8.0)))
    wake_display_enabled = bool(launcher.get("wake_display_enabled", True))
    mouse_nudge_enabled = bool(launcher.get("mouse_nudge_enabled", True))
    keep_system_awake = bool(launcher.get("keep_system_awake", True))
    keep_display_awake = bool(launcher.get("keep_display_awake", True))

    power_state_active = False

    try:
        logger.info("========== launcher START ==========")

        if keep_system_awake:
            set_execution_state(system_required=True, display_required=False)
            power_state_active = True

        if startup_delay > 0:
            logger.info("Startup stabilization delay: %.1f seconds.", startup_delay)
            time.sleep(startup_delay)

        if wake_display_enabled:
            if not power_state_active:
                set_execution_state(system_required=True, display_required=False)
                power_state_active = True

            set_execution_state(system_required=True, display_required=True)
            if mouse_nudge_enabled:
                wake_display()

            logger.info("Waiting %.1f seconds for Windows to finish resuming and initialize the desktop.", post_wake_wait)
            time.sleep(post_wake_wait)

            # During a potentially long Wi-Fi wait, keep Windows awake but allow the
            # display to follow the normal power policy until TikTok is ready to launch.
            if keep_system_awake:
                set_execution_state(system_required=True, display_required=False)
            else:
                clear_execution_state()
                power_state_active = False

        print("Switching keyboard layout to English...")
        try:
            changed = force_english_layout()
            print(f"English keyboard layout requested: {changed}")
        except Exception as exc:
            print(f"Could not force English keyboard layout: {exc}")
            logger.exception("Could not force English keyboard layout")

        ensure_network_ready(settings)

        if keep_system_awake or keep_display_awake:
            set_execution_state(
                system_required=keep_system_awake,
                display_required=keep_display_awake,
            )
            power_state_active = True

        command = [str(python_exe), str(MAIN_SCRIPT)]
        print(f"Starting main.py with: {python_exe}")
        logger.info("Starting main.py after wake/display and network readiness checks.")
        completed = subprocess.run(command, cwd=str(PROJECT_DIR))
        return completed.returncode

    finally:
        if power_state_active:
            clear_execution_state()
        logger.info("========== launcher FINISHED ==========")


if __name__ == "__main__":
    raise SystemExit(launch_main())
