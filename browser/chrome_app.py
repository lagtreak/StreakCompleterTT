from __future__ import annotations

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

    # Based on the user's fullscreen screenshot. Previous Y was ~490; user requested +80px.
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
        desktop = Desktop(backend="uia")
        windows = desktop.windows(visible_only=True)
        matching = []
        for window in windows:
            try:
                title = window.window_text() or ""
                if self.TITLE_RE.match(title):
                    matching.append(window)
            except Exception:
                continue
        if not matching:
            return None
        return matching[0]

    def _get_window(self) -> Any:
        if self.window is not None:
            try:
                if self.window.exists(timeout=0.5):
                    return self.window
            except Exception:
                pass
        return self.wait_for_window()

    def bring_to_front(self) -> None:
        window = self._get_window()
        try:
            window.set_focus()
        except Exception:
            pass
        try:
            window.maximize()
            time.sleep(0.8)
        except Exception as exc:
            self.logger.warning("Could not maximize TikTok window through UIA: %s", exc)
        try:
            window.set_focus()
        except Exception:
            pass

    def ensure_maximized(self) -> None:
        window = self._get_window()
        try:
            window.maximize()
        except Exception:
            pass
        time.sleep(0.8)
        try:
            window.set_focus()
        except Exception:
            pass
        self.logger.info("TikTok window is maximized before automation.")

    def _scaled_screen_point(self, base_x: int, base_y: int) -> tuple[int, int]:
        screen_w, screen_h = pyautogui.size()
        x = round(base_x * screen_w / self.BASE_WIDTH)
        y = round(base_y * screen_h / self.BASE_HEIGHT)
        return x, y

    def click_screen_point(self, x: int, y: int, label: str = "screen point") -> None:
        self.ensure_maximized()
        point = self._scaled_screen_point(x, y)
        self.logger.info(
            "Clicking %s at base=(%s,%s), screen=(%s,%s), screen_size=%sx%s",
            label, x, y, point[0], point[1], *pyautogui.size()
        )
        pyautogui.click(point[0], point[1], duration=0.08)

    def click_messages(self) -> None:
        self.bring_to_front()
        self.ensure_maximized()
        x = int(self.automation.get("messages_click_x", self.MESSAGES_X))
        y = int(self.automation.get("messages_click_y", self.MESSAGES_Y))
        self.click_screen_point(x, y, "Messages")
        time.sleep(float(self.automation.get("messages_after_click_wait_seconds", 2)))
        self.save_screenshot("messages_after_click")

    def prepare_messaging_view(self) -> None:
        wait_seconds = float(self.automation.get("after_messages_wait_seconds", 5))
        self.logger.info("Waiting %.1fs after opening Messages before second navigation click.", wait_seconds)
        time.sleep(wait_seconds)

        click_x = int(self.automation.get("second_click_x", 404))
        click_y = int(self.automation.get("second_click_y", 75))
        self.click_screen_point(click_x, click_y, "post-Messages view selector")
        time.sleep(float(self.automation.get("second_click_wait_seconds", 2)))
        self.ensure_maximized()
        self.save_screenshot("messaging_view_ready")

    def scroll_at(self, x: int, y: int, clicks: int = -1) -> None:
        self.ensure_maximized()
        point = self._scaled_screen_point(x, y)
        self.logger.info("Moving to completed nickname at (%s,%s) and scrolling %s notch.", point[0], point[1], clicks)
        pyautogui.moveTo(point[0], point[1], duration=0.12)
        pyautogui.scroll(clicks)
        time.sleep(float(self.automation.get("scroll_wait_seconds", 1.2)))
        self.save_screenshot("after_scroll")

    def close(self) -> None:
        window = None
        try:
            window = self._get_window()
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
