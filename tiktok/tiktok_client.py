from __future__ import annotations

import time
from typing import Iterable

import pyautogui
import pyperclip

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

    def _paste(self, text: str) -> None:
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.hotkey("ctrl", "v")

    def _click_match(self, match: OCRMatch) -> None:
        x, y = match.center
        self.logger.info(
            "Clicking @%s at OCR box (%s,%s,%s,%s), center=(%s,%s), score=%.2f",
            match.username, match.x, match.y, match.width, match.height, x, y, match.score,
        )
        self.app.bring_to_front()
        pyautogui.click(x, y, duration=0.10)
        wait = float(self.settings.get("after_nickname_click_wait_seconds", 1.0))
        time.sleep(wait)
        # Re-activate the same TikTok top-level window after the chat opens so
        # Ctrl+A / Ctrl+V are delivered to TikTok rather than another window.
        self.app.bring_to_front()
        self.logger.info("TikTok window re-activated after opening @%s; waiting %.2fs before paste.", match.username, wait)

    def _send_message(self, message: str, username: str) -> None:
        if not message.strip():
            raise MessageSendError("Message is empty.")

        # Preserve the Stage 13 send mechanism: clipboard -> Ctrl+A -> Ctrl+V -> Enter.
        # Explicitly bring the TikTok app to the foreground immediately before the
        # keyboard sequence so another window cannot receive the keystrokes.
        self.app.bring_to_front()
        self.logger.info("Sending to @%s: activating TikTok, then Ctrl+A/Ctrl+V/Enter.", username)
        self._paste(message)
        pyautogui.press("enter")
        time.sleep(float(self.settings.get("after_send_wait_seconds", 1.0)))
        self.logger.info("Message sent to @%s", username)

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
