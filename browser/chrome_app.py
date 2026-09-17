from __future__ import annotations

import ctypes
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

import pyautogui
from pywinauto import Desktop

from utils.logger import get_logger


class ChromeTikTokApp:
    """Launch and control the installed TikTok Chrome app window."""

    TITLE_RE = re.compile(r".*TikTok.*", re.IGNORECASE)
    BASE_WIDTH = 1920
    BASE_HEIGHT = 1080

    # Full-screen coordinates calibrated from the user's 1920x1080 screenshot.
    MESSAGES_X = 101
    MESSAGES_Y = 570

    def __init__(
        self,
        proxy_path: str,
        profile_directory: str,
        app_id: str,
        automation: Optional[dict] = None,
    ):
        self.proxy_path = Path(proxy_path)
        self.profile_directory = profile_directory
        self.app_id = app_id
        self.automation = automation or {}
        self.process: Optional[subprocess.Popen] = None
        self.window: Optional[Any] = None
        self.logger = get_logger()

        self.screenshot_dir = Path(__file__).resolve().parent.parent / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def find_proxy() -> Optional[str]:
        candidates = [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome_proxy.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome_proxy.exe"),
            Path.home() / r"AppData\Local\Google\Chrome\Application\chrome_proxy.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    def start(self) -> None:
        if not self.proxy_path.exists():
            raise FileNotFoundError(f"chrome_proxy.exe not found: {self.proxy_path}")
        if not self.app_id:
            raise ValueError("TikTok Chrome app-id is empty.")

        command = [
            str(self.proxy_path),
            f"--profile-directory={self.profile_directory}",
            f"--app-id={self.app_id}",
        ]
        self.logger.info("Launching TikTok Chrome app")
        self.process = subprocess.Popen(command, close_fds=True)
        self.wait_for_window(timeout=30)
        self.ensure_maximized()
        startup_hold = float(self.automation.get("startup_topmost_seconds", 10.0))
        if startup_hold > 0:
            self.hold_topmost_and_foreground(startup_hold)

    def wait_for_window(self, timeout: float = 30) -> Any:
        deadline = time.time() + timeout
        while time.time() < deadline:
            window = self._find_window()
            if window:
                self.window = window
                return window
            time.sleep(0.5)
        raise TimeoutError("TikTok app window was not found after launch.")

    def _find_window(self) -> Optional[Any]:
        """Find the current visible TikTok top-level window.

        The Chrome app can recreate its top-level HWND during navigation. Therefore
        callers should refresh this reference before critical UI actions instead of
        treating the initial HWND as permanent.
        """
        desktop = Desktop(backend="uia")
        windows = desktop.windows(visible_only=True)

        foreground = None
        try:
            foreground_handle = ctypes.windll.user32.GetForegroundWindow()
        except Exception:
            foreground_handle = 0

        matching: list[Any] = []
        for window in windows:
            try:
                title = window.window_text() or ""
                if not self.TITLE_RE.match(title):
                    continue
                matching.append(window)
                if getattr(window, "handle", 0) == foreground_handle:
                    foreground = window
            except Exception:
                continue

        if foreground is not None:
            return foreground
        return matching[0] if matching else None

    def refresh_window(self, timeout: float = 5) -> Any:
        """Refresh the current HWND and return a live TikTok window object."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            window = self._find_window()
            if window is not None:
                old_handle = getattr(self.window, "handle", None) if self.window is not None else None
                new_handle = getattr(window, "handle", None)
                if old_handle != new_handle:
                    self.logger.info("TikTok window handle refreshed: %s -> %s", old_handle, new_handle)
                self.window = window
                return window
            time.sleep(0.25)
        raise TimeoutError("Current TikTok app window was not found.")

    def _get_window(self) -> Any:
        # Always refresh before a critical action because the Chrome app may change HWND.
        return self.refresh_window(timeout=5)

    def bring_to_front(self) -> None:
        window = self.refresh_window()
        self._force_maximize_and_activate(window)

    def hold_topmost_and_foreground(self, seconds: float) -> None:
        """Keep the TikTok window topmost and foreground for a short startup period."""
        seconds = max(0.0, float(seconds))
        deadline = time.monotonic() + seconds
        user32 = ctypes.windll.user32
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_SHOWWINDOW = 0x0040

        self.logger.info(
            "Holding TikTok topmost + foreground for %.1f seconds after launch.", seconds
        )

        while time.monotonic() < deadline:
            try:
                window = self.refresh_window(timeout=1.0)
                handle = getattr(window, "handle", 0)
                if handle:
                    # TOPMOST keeps TikTok above Explorer and other ordinary windows.
                    user32.SetWindowPos(
                        wintypes.HWND(handle),
                        wintypes.HWND(HWND_TOPMOST),
                        0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
                    )
                    user32.ShowWindow(handle, 3)  # SW_MAXIMIZE
                    user32.BringWindowToTop(handle)
                    user32.SetForegroundWindow(handle)
                    self.window = window
            except Exception as exc:
                self.logger.warning("Could not keep TikTok topmost/foreground: %s", exc)
            time.sleep(0.5)

        # Remove the persistent TOPMOST flag after the startup hold. The window stays
        # foreground, but normal z-order is restored so the rest of the desktop behaves normally.
        try:
            window = self.refresh_window(timeout=1.0)
            handle = getattr(window, "handle", 0)
            if handle:
                user32.SetWindowPos(
                    wintypes.HWND(handle),
                    wintypes.HWND(HWND_NOTOPMOST),
                    0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
                )
                user32.BringWindowToTop(handle)
                user32.SetForegroundWindow(handle)
                self.logger.info("Startup topmost hold finished; TikTok remains foregrounded (handle=%s).", handle)
        except Exception as exc:
            self.logger.warning("Could not clear TikTok topmost state: %s", exc)

    def _force_maximize_and_activate(self, window: Any) -> None:
        """Maximize without restoring to a windowed state, then foreground it."""
        handle = getattr(window, "handle", None)
        if not handle:
            try:
                window.maximize()
                window.set_focus()
            except Exception as exc:
                self.logger.warning("Could not focus/maximize TikTok window: %s", exc)
            return

        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        SW_MAXIMIZE = 3

        try:
            # If minimized, restore first. Never call SW_RESTORE on an ordinary
            # maximized window because it would intentionally unmaximize it.
            if user32.IsIconic(handle):
                user32.ShowWindow(handle, SW_RESTORE)
                time.sleep(0.2)

            user32.ShowWindow(handle, SW_MAXIMIZE)
            user32.BringWindowToTop(handle)
            user32.SetForegroundWindow(handle)
            time.sleep(0.25)

            # A second maximize call is idempotent and protects against a window
            # recreation during activation.
            user32.ShowWindow(handle, SW_MAXIMIZE)
            self.logger.info("TikTok window maximized and foregrounded via WinAPI (handle=%s).", handle)
        except Exception as exc:
            self.logger.warning("WinAPI maximize/foreground failed: %s", exc)
            try:
                window.maximize()
                window.set_focus()
            except Exception:
                pass

    def ensure_maximized(self) -> None:
        window = self.refresh_window()
        self._force_maximize_and_activate(window)
        self.logger.info("TikTok window is forced to maximized state before automation (handle=%s).", getattr(window, "handle", None))

    def _scaled_screen_point(self, base_x: int, base_y: int) -> tuple[int, int]:
        screen_w, screen_h = pyautogui.size()
        x = round(base_x * screen_w / self.BASE_WIDTH)
        y = round(base_y * screen_h / self.BASE_HEIGHT)
        return x, y

    def click_screen_point(self, x: int, y: int, label: str = "screen point") -> None:
        self.ensure_maximized()
        self.refresh_window()
        point = self._scaled_screen_point(x, y)
        screen_w, screen_h = pyautogui.size()
        self.logger.info(
            "Clicking %s at base=(%s,%s), screen=(%s,%s), screen_size=%sx%s, hwnd=%s",
            label, x, y, point[0], point[1], screen_w, screen_h, getattr(self.window, "handle", None)
        )
        pyautogui.click(point[0], point[1], duration=0.08)

    def click_messages(self, ocr=None) -> None:
        self.logger.info("Opening Messages: continuously locating the 'Сообщения' label in the left third of the screen.")
        self.ensure_maximized()
        self.refresh_window()

        if ocr is None:
            raise ValueError("OCR engine is required to locate the 'Сообщения' label.")

        target = str(self.automation.get("messages_label", "Сообщения"))
        timeout = float(self.automation.get("messages_ocr_timeout_seconds", 300))
        poll = float(self.automation.get("messages_ocr_poll_seconds", 1.0))
        after_found_wait = float(self.automation.get("messages_label_found_wait_seconds", 2.0))
        deadline = time.time() + timeout
        found = None

        while time.time() < deadline:
            self.ensure_maximized()
            matches = ocr.find_text_matches(
                [target],
                region_ratio=float(self.automation.get("messages_left_region_ratio", 1/3)),
            )
            if matches:
                found = matches[0]
                self.logger.info(
                    "Found '%s' at OCR box (%s,%s,%s,%s), center=(%s,%s), score=%.2f. Waiting %.1fs before click.",
                    target, found.x, found.y, found.width, found.height,
                    found.center[0], found.center[1], found.score, after_found_wait,
                )
                time.sleep(after_found_wait)
                break
            self.logger.info("'%s' not found yet; retrying OCR in %.1fs.", target, poll)
            time.sleep(poll)

        if found is None:
            self.save_screenshot("messages_label_not_found")
            raise TimeoutError(f"Could not locate '{target}' in the left third of the screen within {timeout:.1f}s.")

        x, y = found.center
        self.bring_to_front()
        # Refresh OCR coordinates after the wait/activation so we click where the
        # label was actually detected on the current fullscreen layout.
        self.logger.info(
            "Clicking '%s' at OCR center=(%s,%s).", target, x, y,
        )
        pyautogui.click(x, y, duration=0.10)
        time.sleep(float(self.automation.get("messages_after_click_wait_seconds", 2)))
        self.refresh_window()
        self.save_screenshot("messages_after_ocr_click")

    def prepare_messaging_view(self, ocr=None) -> None:
        # Instead of relying on a fixed timer before the second navigation click,
        # wait until the small header area visibly contains the "Сообщения" label.
        if ocr is None:
            raise ValueError("OCR engine is required to confirm the Messages header.")

        box_x = int(self.automation.get("messages_header_x", 89))
        box_y = int(self.automation.get("messages_header_y", 37))
        box_w = int(self.automation.get("messages_header_width", 400))
        box_h = int(self.automation.get("messages_header_height", 70))
        target = str(self.automation.get("messages_header_text", "Сообщения"))
        timeout = float(self.automation.get("messages_header_ocr_timeout_seconds", 300))
        poll = float(self.automation.get("messages_header_ocr_poll_seconds", 1.0))
        found_wait = float(self.automation.get("messages_header_found_wait_seconds", 1.0))

        self.logger.info(
            "Waiting for '%s' in header OCR box x=%d y=%d w=%d h=%d before second navigation click.",
            target, box_x, box_y, box_w, box_h,
        )
        deadline = time.monotonic() + timeout
        found = None
        while time.monotonic() < deadline:
            self.ensure_maximized()
            matches = ocr.find_text_matches_in_box(
                [target], box_x, box_y, box_w, box_h,
                min_confidence=float(self.automation.get("messages_header_ocr_min_confidence", 10)),
                fuzzy_threshold=float(self.automation.get("messages_header_ocr_fuzzy_threshold", 0.70)),
            )
            if matches:
                found = matches[0]
                self.logger.info(
                    "Found '%s' in header box at (%d,%d); waiting %.1fs before click (404,75).",
                    target, found.x, found.y, found_wait,
                )
                time.sleep(found_wait)
                break
            time.sleep(poll)

        if found is None:
            self.save_screenshot("messages_header_not_found")
            raise TimeoutError(
                f"Could not locate '{target}' in the header OCR box within {timeout:.1f}s."
            )

        self.ensure_maximized()
        self.click_screen_point(
            int(self.automation.get("second_click_x", 404)),
            int(self.automation.get("second_click_y", 75)),
            "post-Messages view selector",
        )
        time.sleep(float(self.automation.get("second_click_wait_seconds", 2)))
        self.ensure_maximized()
        self.refresh_window()
        self.save_screenshot("messaging_view_ready")

    def scroll_at(self, x: int, y: int, clicks: int = -50) -> None:
        self.ensure_maximized()
        point = self._scaled_screen_point(x, y)
        self.logger.info("Moving to completed nickname at (%s,%s) and scrolling %s notch.", point[0], point[1], clicks)
        pyautogui.moveTo(point[0], point[1], duration=0.12)
        pyautogui.scroll(clicks)
        time.sleep(float(self.automation.get("scroll_wait_seconds", 1.2)))
        self.refresh_window()
        self.save_screenshot("after_scroll")

    def close(self) -> None:
        window = None
        try:
            window = self.refresh_window(timeout=2)
        except Exception:
            pass

        if window:
            try:
                window.close()
                return
            except Exception:
                pass
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass

    def save_screenshot(self, name: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
        path = self.screenshot_dir / f"{safe}.png"
        try:
            pyautogui.screenshot().save(path)
            return path
        except Exception as exc:
            self.logger.warning("Could not save full-screen screenshot: %s", exc)
            return path
