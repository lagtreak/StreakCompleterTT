from __future__ import annotations

import time
import ctypes
from typing import Iterable

import pyautogui

from browser.chrome_app import ChromeTikTokApp
from models.user import User
from utils.exceptions import MessageSendError, UserSearchError
from utils.logger import get_logger
from utils.ocr_engine import OCRMatch, ScreenOCR


class TikTokClient:
    """Screen-based UI automation for the authenticated TikTok Chrome app."""

    def __init__(self, app: ChromeTikTokApp, automation_settings: dict | None = None):
        self.app = app
        self.settings = automation_settings or {}
        self.logger = get_logger()
        self.ocr = ScreenOCR(self.settings)
        pyautogui.PAUSE = float(self.settings.get("pyautogui_pause", 0.15))
        pyautogui.FAILSAFE = True

    def open_messages(self) -> None:
        self.logger.info("Opening Messages")
        self.app.click_messages()
        self.app.prepare_messaging_view()

    def _type_message_manually(self, text: str) -> None:
        """Type the message using real keyboard key presses, without the clipboard."""
        if text != "Огонь":
            raise MessageSendError("Manual keyboard mode currently supports only the configured message 'Огонь'.")

        # Russian keyboard layout mapping:
        # О = Shift+J, г = U, о = J, н = Y, ь = M
        user32 = ctypes.windll.user32
        original_layout = user32.GetKeyboardLayout(0)
        russian_layout = user32.LoadKeyboardLayoutW("00000419", 1)
        if not russian_layout:
            raise MessageSendError("Could not activate the Russian keyboard layout.")

        try:
            user32.ActivateKeyboardLayout(russian_layout, 0)
            time.sleep(0.1)

            keys = [("shift", "j"), (None, "u"), (None, "j"), (None, "y"), (None, "m")]
            key_interval = float(self.settings.get("manual_key_interval_seconds", 0.08))
            for modifier, key in keys:
                if modifier:
                    pyautogui.keyDown(modifier)
                pyautogui.press(key)
                if modifier:
                    pyautogui.keyUp(modifier)
                if key_interval > 0:
                    time.sleep(key_interval)
        finally:
            if original_layout:
                user32.ActivateKeyboardLayout(original_layout, 0)

    def _send_message(self, message: str, username: str) -> None:
        if not message.strip():
            raise MessageSendError("Message is empty.")

        input_x = int(self.settings.get("message_input_x", 620))
        input_y = int(self.settings.get("message_input_y", 1047))
        self.logger.info("Clicking message input at (%s,%s)", input_x, input_y)
        self.app.click_screen_point(input_x, input_y, "message input")

        wait_seconds = float(self.settings.get("before_manual_typing_wait_seconds", 2.0))
        self.logger.info("Waiting %.2fs before manual keyboard input", wait_seconds)
        time.sleep(wait_seconds)

        self.logger.info("Typing message manually: %s", message)
        self._type_message_manually(message)
        pyautogui.press("enter")
        time.sleep(float(self.settings.get("after_send_wait_seconds", 1.0)))
        self.logger.info("Message submitted for @%s", username)

    def _click_match(self, match: OCRMatch) -> None:
        x, y = match.center
        self.logger.info(
            "Clicking @%s at OCR box (%s,%s,%s,%s), center=(%s,%s), score=%.2f",
            match.username, match.x, match.y, match.width, match.height, x, y, match.score,
        )
        pyautogui.click(x, y, duration=0.10)
        time.sleep(float(self.settings.get("after_nickname_click_wait_seconds", 1.0)))

    def send_sequence(self, users: Iterable[User], message: str) -> str:
        self.app.ensure_maximized()
        self.ocr.validate()

        targets = [user.username.lstrip("@").strip() for user in users if user.enabled and user.username.strip()]
        if not targets:
            raise UserSearchError("No enabled usernames to search.")

        completed: set[str] = set()
        completed_count = 0
        failures: list[str] = []

        self.logger.info("Target nicknames: %s", targets)
        self.app.save_screenshot("sequence_start")

        while len(completed) < len(targets):
            remaining = [name for name in targets if name.lower() not in {c.lower() for c in completed}]
            if not remaining:
                break

            matches = self.ocr.find_matches(remaining)
            if not matches:
                failures.extend(remaining)
                self.app.save_screenshot("ocr_no_targets_found")
                self.logger.warning("No remaining target nickname found on the left half of the screen.")
                break

            chosen = matches[0]
            try:
                self._click_match(chosen)
                self._send_message(message, chosen.username)
                completed.add(chosen.username)
                completed_count += 1
                self.logger.info(
                    "Completed %d/%d: @%s",
                    completed_count, len(targets), chosen.username,
                )

                # Every second completed nickname follows the scroll-down scenario.
                if completed_count % 2 == 0:
                    self.app.scroll_at(
                        chosen.center[0], chosen.center[1],
                        clicks=int(self.settings.get("scroll_steps", -50)),
                    )
                else:
                    time.sleep(float(self.settings.get("between_standard_scans_wait_seconds", 0.8)))

            except Exception as exc:
                failures.append(chosen.username)
                self.logger.exception("Failed for @%s: %s", chosen.username, exc)
                completed.add(chosen.username)

        summary = f"Finished: {completed_count}/{len(targets)} messages sent."
        if failures:
            summary += f" Failed/skipped: {', '.join('@' + name for name in failures)}."
        self.app.save_screenshot("sequence_finished")
        return summary
