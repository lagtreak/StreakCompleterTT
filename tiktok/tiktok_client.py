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
        self.app.click_messages(self.ocr)
        self.app.prepare_messaging_view(self.ocr)
        initial_wait = float(self.settings.get("initial_nickname_search_wait_seconds", 10.0))
        if initial_wait > 0:
            self.logger.info(
                "Expanded chat view is ready. Waiting %.1f seconds before starting the first nickname search.",
                initial_wait,
            )
            time.sleep(initial_wait)

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

    def _wait_for_message_input(self, username: str) -> None:
        """Wait until OCR sees any text in the message-input area.

        The input area is used only as a visual readiness signal. We intentionally
        do not click it: after the chat is opened, the field is already focused in
        the working TikTok flow, and an unnecessary coordinate click can race with
        the page update and leave focus on the page instead of the input.
        """
        box_x = int(self.settings.get("message_input_ocr_x", 520))
        box_y = int(self.settings.get("message_input_ocr_y", 1020))
        box_w = int(self.settings.get("message_input_ocr_width", 300))
        box_h = int(self.settings.get("message_input_ocr_height", 40))
        timeout = float(self.settings.get("message_input_ocr_timeout_seconds", 30.0))
        poll = float(self.settings.get("message_input_ocr_poll_seconds", 0.5))
        min_confidence = float(self.settings.get("message_input_ocr_min_confidence", 10))

        self.logger.info(
            "Waiting for message input to become visually ready for @%s: OCR box=(%d,%d,%d,%d), timeout=%.1fs, poll=%.1fs.",
            username, box_x, box_y, box_w, box_h, timeout, poll,
        )

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.ensure_maximized()
            matches = self.ocr.find_any_text_in_box(
                box_x, box_y, box_w, box_h,
                min_confidence=min_confidence,
            )
            if matches:
                self.logger.info(
                    "Message input area detected for @%s: %s. Sending Ctrl+A/Ctrl+V immediately.",
                    username,
                    [f"{m.raw_text!r}@({m.x},{m.y})/conf={m.score:.0f}" for m in matches],
                )
                return

            self.logger.info(
                "Message input area for @%s is not ready yet; retrying OCR in %.1fs.",
                username, poll,
            )
            time.sleep(poll)

        self.app.save_screenshot(f"message_input_not_ready_{username}")
        raise TimeoutError(
            f"Message input area did not show any OCR text within {timeout:.1f}s for @{username}."
        )

    def _send_message(self, message: str, username: str) -> None:
        if not message.strip():
            raise MessageSendError("Message is empty.")

        self.app.bring_to_front()
        self._wait_for_message_input(username)
        self.app.bring_to_front()
        self.logger.info("Sending to @%s: Ctrl+A/Ctrl+V/Enter.", username)
        self._paste(message)
        pyautogui.press("enter")
        time.sleep(float(self.settings.get("after_send_wait_seconds", 1.0)))
        self.logger.info("Message sent to @%s", username)

    def wait_for_any_target_nickname(self, users: Iterable[User]) -> None:
        """Wait until at least one target nickname becomes visible before full OCR processing."""
        targets = [
            user.username.lstrip("@").strip()
            for user in users
            if user.enabled and user.username.strip()
        ]
        if not targets:
            raise UserSearchError("No enabled usernames to search.")

        timeout = float(self.settings.get("nicknames_ready_timeout_seconds", 300))
        poll = float(self.settings.get("nicknames_ready_poll_seconds", 1.0))
        found_wait = float(self.settings.get("nicknames_ready_found_wait_seconds", 3.0))
        self.logger.info(
            "Waiting for any target nickname to appear before starting full OCR: timeout=%.1fs, poll=%.1fs.",
            timeout, poll,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.ensure_maximized()
            matches = self.ocr.find_matches(targets)
            if matches:
                self.logger.info(
                    "Target nickname appeared (%s at y=%d); waiting %.1fs before Stage 3 OCR.",
                    matches[0].username, matches[0].y, found_wait,
                )
                time.sleep(found_wait)
                return
            time.sleep(poll)

        self.app.save_screenshot("nicknames_not_ready")
        raise TimeoutError(
            f"No target nickname appeared within {timeout:.1f}s after the Messages stage."
        )

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
