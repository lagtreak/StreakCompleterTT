from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional
from urllib import parse, request


class TelegramNotifier:
    """Small Telegram Bot API client based only on Python's standard library."""

    def __init__(self, project_dir: Path, config: dict | None = None):
        self.project_dir = project_dir
        self.config = config or self._load_config()
        self.logger = logging.getLogger("tiktok_messenger")
        self.enabled = bool(self.config.get("enabled", False))
        self.token = str(self.config.get("bot_token", "")).strip()
        self.chat_id = str(self.config.get("chat_id", "auto")).strip()
        self.timeout = max(3.0, float(self.config.get("request_timeout_seconds", 10.0)))
        self.cache_path = self.project_dir / "config" / "telegram_chat_id.txt"
        self.message_limit = max(1000, int(self.config.get("message_limit", 3900)))

    def _load_config(self) -> dict:
        path = self.project_dir / "config" / "telegram.json"
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except Exception as exc:
            self.logger.warning("Could not load Telegram config: %s", exc)
            return {}

    def _api_call(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        if not self.token:
            raise RuntimeError("Telegram bot token is not configured.")

        url = f"https://api.telegram.org/bot{self.token}/{method}"
        body = parse.urlencode(params or {}).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "StreakCompleterTT/1.0",
            },
            method="POST",
        )

        with request.urlopen(req, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if not isinstance(payload, dict) or not payload.get("ok"):
            description = payload.get("description", "Unknown Telegram API error") if isinstance(payload, dict) else "Invalid Telegram API response"
            raise RuntimeError(str(description))
        return payload

    def _load_cached_chat_id(self) -> Optional[str]:
        try:
            if not self.cache_path.exists():
                return None
            value = self.cache_path.read_text(encoding="utf-8").strip()
            return value or None
        except Exception as exc:
            self.logger.warning("Could not read cached Telegram chat id: %s", exc)
            return None

    def _cache_chat_id(self, chat_id: str) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(str(chat_id), encoding="utf-8")
        except Exception as exc:
            self.logger.warning("Could not cache Telegram chat id: %s", exc)

    def _discover_chat_id(self) -> Optional[str]:
        cached = self._load_cached_chat_id()
        if cached:
            return cached

        payload = self._api_call(
            "getUpdates",
            {
                "limit": 50,
                "timeout": 0,
            },
        )
        updates = payload.get("result", [])
        if not isinstance(updates, list):
            return None

        candidates: list[tuple[int, str]] = []
        for update in updates:
            if not isinstance(update, dict):
                continue
            update_id = int(update.get("update_id", 0))
            for key in ("message", "edited_message"):
                message = update.get(key)
                if not isinstance(message, dict):
                    continue
                chat = message.get("chat")
                if not isinstance(chat, dict) or chat.get("type") != "private":
                    continue
                chat_id = chat.get("id")
                if chat_id is None:
                    continue
                candidates.append((update_id, str(chat_id)))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        chat_id = candidates[0][1]
        self._cache_chat_id(chat_id)
        return chat_id

    def resolve_chat_id(self) -> str:
        if self.chat_id and self.chat_id.casefold() not in {"auto", "none", "null"}:
            return self.chat_id

        discovered = self._discover_chat_id()
        if discovered:
            return discovered

        raise RuntimeError(
            "Telegram chat id was not found. Open the bot in Telegram and send /start once, then run the workflow again."
        )

    def send_text(self, text: str) -> None:
        chat_id = self.resolve_chat_id()
        chunks = [text[i:i + self.message_limit] for i in range(0, len(text), self.message_limit)] or [""]
        for chunk in chunks:
            self._api_call(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": "true",
                },
            )

    def send_report(self, report: Any) -> bool:
        if not self.enabled:
            self.logger.info("Telegram notifications are disabled.")
            return False

        if not self.token:
            self.logger.warning("Telegram notifications are enabled, but bot_token is empty.")
            return False

        try:
            self.send_text(report.to_telegram_text())
            self.logger.info("Telegram execution report sent successfully.")
            return True
        except Exception as exc:
            self.logger.exception("Could not send Telegram execution report: %s", exc)
            return False
