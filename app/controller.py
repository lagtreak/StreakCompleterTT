from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from browser.chrome_app import ChromeTikTokApp
from models.user import User
from services.user_service import load_users
from tiktok.tiktok_client import TikTokClient
from utils.logger import logger


class ApplicationController:
    def __init__(self, status_callback: Optional[Callable[[str], None]] = None):
        self.status_callback = status_callback
        self.app: Optional[ChromeTikTokApp] = None
        self.client: Optional[TikTokClient] = None
        self.project_dir = Path(__file__).resolve().parent.parent

    def _status(self, message: str) -> None:
        logger.info(message)
        if self.status_callback:
            self.status_callback(message)

    def _load_settings(self) -> dict:
        path = self.project_dir / "config" / "settings.json"
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def launch_tiktok(self) -> None:
        settings = self._load_settings()
        browser = settings.get("browser", {})
        proxy_path = browser.get("chrome_proxy") or ChromeTikTokApp.find_proxy()
        if not proxy_path:
            raise FileNotFoundError(
                "Could not find chrome_proxy.exe. Set browser.chrome_proxy in config/settings.json"
            )

        self.app = ChromeTikTokApp(
            proxy_path=proxy_path,
            profile_directory=browser.get("profile_directory", "Default"),
            app_id=browser.get("app_id", ""),
            automation=settings.get("automation", {}),
        )
        self._status("Starting TikTok Chrome app...")
        self.app.start()
        self.client = TikTokClient(self.app, settings.get("automation", {}))
        self._status("TikTok app launched and maximized.")

    def open_messages(self) -> None:
        self._ensure_client()
        self._status("Opening Messages...")
        self.client.open_messages()
        self._status("Messages opened. Preparing fullscreen view...")

    def run_messaging(self) -> None:
        self._ensure_client()
        settings = self._load_settings()
        users = [
            user for user in load_users(self.project_dir / "config" / "users.json")
            if user.enabled
        ]
        if not users:
            raise RuntimeError("No enabled users found in config/users.json")

        message = settings.get("messaging", {}).get("message", "Огонь")
        self._status("Starting OCR messaging sequence...")
        summary = self.client.send_sequence(users, message)
        self._status(summary)

    def _ensure_client(self) -> None:
        if self.client is None or self.app is None:
            raise RuntimeError("TikTok is not open. Click Open TikTok App first.")

    def close_tiktok(self) -> None:
        if self.app:
            self.app.close()
        self.app = None
        self.client = None
        self._status("TikTok app closed.")
