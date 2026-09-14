from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright


class BrowserManager:
    """Starts Opera GX with a separate persistent automation profile."""

    def __init__(
        self,
        executable_path: str | None = None,
        headless: bool = False,
        viewport_width: int = 1280,
        viewport_height: int = 800,
    ) -> None:
        self.project_root = Path(__file__).resolve().parent.parent
        self.profile_dir = self.project_root / "browser" / "profile"
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.configured_executable = executable_path
        self.headless = headless
        self.viewport = {"width": viewport_width, "height": viewport_height}
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    @staticmethod
    def _candidate_paths() -> Iterable[Path]:
        local_app_data = os.environ.get("LOCALAPPDATA")
        program_files = os.environ.get("PROGRAMFILES")
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)")

        candidates: list[Path] = []

        if local_app_data:
            candidates.extend(
                [
                    Path(local_app_data) / "Programs" / "Opera GX" / "opera.exe",
                    Path(local_app_data) / "Programs" / "Opera GX" / "launcher.exe",
                    Path(local_app_data) / "Programs" / "Opera GX" / "launcher.exe.exe",
                ]
            )

        for base in (program_files, program_files_x86):
            if base:
                candidates.extend(
                    [
                        Path(base) / "Opera GX" / "opera.exe",
                        Path(base) / "Opera GX" / "launcher.exe",
                    ]
                )

        # Common per-user installation used by some Opera GX versions.
        if local_app_data:
            opera_root = Path(local_app_data) / "Programs"
            candidates.extend(opera_root.glob("Opera GX*/opera.exe"))
            candidates.extend(opera_root.glob("Opera GX*/launcher.exe"))

        return candidates

    def find_opera_gx(self) -> Path | None:
        if self.configured_executable:
            configured = Path(os.path.expandvars(os.path.expanduser(self.configured_executable)))
            if configured.is_file():
                return configured
            raise FileNotFoundError(
                f"Opera GX executable was not found at: {configured}"
            )

        for candidate in self._candidate_paths():
            if candidate.is_file():
                return candidate

        return None

    def start(self) -> Page:
        if self.page is not None:
            return self.page

        executable = self.find_opera_gx()
        if executable is None:
            raise FileNotFoundError(
                "Opera GX was not found automatically. "
                "Set browser.executable_path in config/settings.json."
            )

        self.playwright = sync_playwright().start()
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            executable_path=str(executable),
            headless=self.headless,
            viewport=self.viewport,
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self.page

    def close(self) -> None:
        try:
            if self.context is not None:
                self.context.close()
        finally:
            self.context = None
            self.page = None

            if self.playwright is not None:
                self.playwright.stop()
            self.playwright = None
