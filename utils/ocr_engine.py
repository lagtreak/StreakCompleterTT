from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pyautogui
import pytesseract
from PIL import Image, ImageFilter, ImageOps
from pytesseract import Output

from utils.exceptions import OCRNotAvailableError
from utils.logger import get_logger


@dataclass
class OCRMatch:
    username: str
    score: float
    x: int
    y: int
    width: int
    height: int
    raw_text: str

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


class ScreenOCR:
    def __init__(self, settings: dict | None = None):
        self.settings = settings or {}
        self.logger = get_logger()
        self._configure_tesseract()

    def _configure_tesseract(self) -> None:
        configured = str(self.settings.get("tesseract_cmd", "")).strip()
        if configured:
            path = Path(configured)
            if path.exists():
                pytesseract.pytesseract.tesseract_cmd = str(path)
                return

        candidates = [
            Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
            Path.home() / r"AppData\Local\Tesseract-OCR\tesseract.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                pytesseract.pytesseract.tesseract_cmd = str(candidate)
                return

    def validate(self) -> None:
        try:
            version = pytesseract.get_tesseract_version()
        except Exception as exc:
            raise OCRNotAvailableError(
                "Tesseract OCR is not installed or cannot be found. Install Tesseract OCR, "
                "then set automation.tesseract_cmd in config/settings.json if necessary."
            ) from exc

        lang = str(self.settings.get("ocr_lang", "rus+eng"))
        try:
            languages = pytesseract.get_languages(config="")
        except Exception as exc:
            raise OCRNotAvailableError(f"Could not read Tesseract language data: {exc}") from exc

        needed = [part for part in lang.split("+") if part]
        missing = [part for part in needed if part not in languages]
        if missing:
            raise OCRNotAvailableError(
                f"Tesseract is installed (version {version}), but language data is missing: {', '.join(missing)}. "
                "Install the Russian language data for Tesseract or adjust automation.ocr_lang."
            )

        self.logger.info("Tesseract ready: version=%s, languages=%s", version, lang)

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.strip().lstrip("@")
        return "".join(ch.lower() for ch in text if ch.isalnum())

    def _preprocess(self, image: Image.Image) -> Image.Image:
        scale = int(self.settings.get("ocr_scale", 3))
        gray = ImageOps.grayscale(image)
        gray = ImageOps.autocontrast(gray)
        gray = gray.filter(ImageFilter.SHARPEN)
        return gray.resize((gray.width * scale, gray.height * scale))

    def find_text_matches(self, texts: Iterable[str], region_ratio: float = 1/3) -> list[OCRMatch]:
        """Find arbitrary target texts in the left part of the screen."""
        self.validate()
        targets = list(texts)
        normalized_targets = {self._normalize(name): name for name in targets}

        screen_w, screen_h = pyautogui.size()
        crop_w = max(1, int(screen_w * region_ratio))
        screenshot = pyautogui.screenshot()
        crop = screenshot.crop((0, 0, crop_w, screen_h))
        processed = self._preprocess(crop)

        output_dir = Path(__file__).resolve().parent.parent / "screenshots"
        output_dir.mkdir(parents=True, exist_ok=True)
        processed.save(output_dir / "ocr_left_third_messages.png")

        lang = str(self.settings.get("ocr_lang", "rus+eng"))
        psm = int(self.settings.get("messages_ocr_psm", self.settings.get("ocr_psm", 11)))
        config = f"--oem 3 --psm {psm}"
        data = pytesseract.image_to_data(processed, lang=lang, config=config, output_type=Output.DICT)
        scale = int(self.settings.get("ocr_scale", 3))
        threshold = float(self.settings.get("messages_ocr_fuzzy_threshold", 0.72))
        matches: list[OCRMatch] = []
        seen: set[tuple[str, int, int]] = set()

        for i, raw in enumerate(data["text"]):
            text = (raw or "").strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1
            if conf < float(self.settings.get("messages_ocr_min_confidence", 15)):
                continue

            norm = self._normalize(text)
            if not norm:
                continue

            best_user = None
            best_score = 0.0
            for target_norm, target_original in normalized_targets.items():
                score = 1.0 if norm == target_norm else difflib.SequenceMatcher(None, norm, target_norm).ratio()
                if score > best_score:
                    best_score = score
                    best_user = target_original

            if best_user is None or best_score < threshold:
                continue

            left = int(data["left"][i]) // scale
            top = int(data["top"][i]) // scale
            width = max(1, int(data["width"][i]) // scale)
            height = max(1, int(data["height"][i]) // scale)
            key = (self._normalize(best_user), left, top)
            if key in seen:
                continue
            seen.add(key)
            matches.append(OCRMatch(best_user, best_score, left, top, width, height, text))

        matches.sort(key=lambda m: (m.y, m.x))
        self.logger.info(
            "Messages OCR left-third scan: %d matches found: %s",
            len(matches),
            [f"{m.username}@y={m.y}/score={m.score:.2f}/raw={m.raw_text!r}" for m in matches],
        )
        return matches

    def find_any_text_in_box(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        min_confidence: float = 10,
    ) -> list[OCRMatch]:
        """Return OCR tokens for any visible text inside a fixed screen rectangle."""
        self.validate()

        screen_w, screen_h = pyautogui.size()
        left = max(0, min(int(x), screen_w - 1))
        top = max(0, min(int(y), screen_h - 1))
        right = max(left + 1, min(left + int(width), screen_w))
        bottom = max(top + 1, min(top + int(height), screen_h))

        screenshot = pyautogui.screenshot()
        crop = screenshot.crop((left, top, right, bottom))
        processed = self._preprocess(crop)

        lang = str(self.settings.get("ocr_lang", "rus+eng"))
        psm = int(self.settings.get("message_input_ocr_psm", self.settings.get("ocr_psm", 11)))
        config = f"--oem 3 --psm {psm}"
        data = pytesseract.image_to_data(processed, lang=lang, config=config, output_type=Output.DICT)

        scale = int(self.settings.get("ocr_scale", 3))
        matches: list[OCRMatch] = []
        seen: set[tuple[int, int, str]] = set()

        for i, raw in enumerate(data["text"]):
            text = (raw or "").strip()
            if not text:
                continue

            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1
            if conf < float(min_confidence):
                continue

            local_left = int(data["left"][i]) // scale
            local_top = int(data["top"][i]) // scale
            local_width = max(1, int(data["width"][i]) // scale)
            local_height = max(1, int(data["height"][i]) // scale)
            screen_left = left + local_left
            screen_top = top + local_top
            key = (screen_left, screen_top, text.casefold())
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                OCRMatch(
                    username=text,
                    score=conf,
                    x=screen_left,
                    y=screen_top,
                    width=local_width,
                    height=local_height,
                    raw_text=text,
                )
            )

        matches.sort(key=lambda m: (m.y, m.x))
        self.logger.info(
            "OCR any-text scan (%d,%d,%d,%d): %d text tokens found: %s",
            left, top, right-left, bottom-top, len(matches),
            [f"{m.raw_text!r}@({m.x},{m.y})/conf={m.score:.0f}" for m in matches],
        )
        return matches

    def find_text_matches_in_box(
        self,
        texts: Iterable[str],
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        min_confidence: float | None = None,
        fuzzy_threshold: float | None = None,
    ) -> list[OCRMatch]:
        """Find target texts in a fixed screen rectangle and return screen coordinates."""
        self.validate()
        targets = list(texts)
        normalized_targets = {self._normalize(name): name for name in targets}

        screen_w, screen_h = pyautogui.size()
        left = max(0, min(int(x), screen_w - 1))
        top = max(0, min(int(y), screen_h - 1))
        right = max(left + 1, min(left + int(width), screen_w))
        bottom = max(top + 1, min(top + int(height), screen_h))

        screenshot = pyautogui.screenshot()
        crop = screenshot.crop((left, top, right, bottom))
        processed = self._preprocess(crop)

        lang = str(self.settings.get("ocr_lang", "rus+eng"))
        psm = int(self.settings.get("messages_ocr_psm", self.settings.get("ocr_psm", 11)))
        config = f"--oem 3 --psm {psm}"
        data = pytesseract.image_to_data(processed, lang=lang, config=config, output_type=Output.DICT)
        scale = int(self.settings.get("ocr_scale", 3))
        confidence_limit = float(
            self.settings.get("messages_ocr_min_confidence", 15)
            if min_confidence is None else min_confidence
        )
        threshold = float(
            self.settings.get("messages_ocr_fuzzy_threshold", 0.72)
            if fuzzy_threshold is None else fuzzy_threshold
        )

        matches: list[OCRMatch] = []
        seen: set[tuple[str, int, int]] = set()
        for i, raw in enumerate(data["text"]):
            text = (raw or "").strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1
            if conf < confidence_limit:
                continue

            norm = self._normalize(text)
            if not norm:
                continue

            best_user = None
            best_score = 0.0
            for target_norm, target_original in normalized_targets.items():
                score = 1.0 if norm == target_norm else difflib.SequenceMatcher(None, norm, target_norm).ratio()
                if score > best_score:
                    best_score = score
                    best_user = target_original

            if best_user is None or best_score < threshold:
                continue

            local_left = int(data["left"][i]) // scale
            local_top = int(data["top"][i]) // scale
            local_width = max(1, int(data["width"][i]) // scale)
            local_height = max(1, int(data["height"][i]) // scale)
            screen_left = left + local_left
            screen_top = top + local_top
            key = (self._normalize(best_user), screen_left, screen_top)
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                OCRMatch(
                    best_user, best_score, screen_left, screen_top,
                    local_width, local_height, text
                )
            )

        matches.sort(key=lambda m: (m.y, m.x))
        self.logger.info(
            "OCR fixed-box scan (%d,%d,%d,%d): %d matches found: %s",
            left, top, right-left, bottom-top, len(matches),
            [f"{m.username}@({m.x},{m.y})/score={m.score:.2f}/raw={m.raw_text!r}" for m in matches],
        )
        return matches

    def capture_nickname_area(self) -> tuple[Image.Image, int, int]:
        """Capture the configured nickname-search area and return its screen offset."""
        screen_w, screen_h = pyautogui.size()
        left = max(0, min(int(self.settings.get("nickname_region_x", 90)), screen_w - 1))
        top = max(0, min(int(self.settings.get("nickname_region_y", 100)), screen_h - 1))
        width = max(1, int(self.settings.get("nickname_region_width", 400)))
        height = max(1, int(self.settings.get("nickname_region_height", 980)))
        right = min(left + width, screen_w)
        bottom = min(top + height, screen_h)
        screenshot = pyautogui.screenshot()
        return screenshot.crop((left, top, right, bottom)), left, top

    def find_matches(self, usernames: Iterable[str]) -> list[OCRMatch]:
        """Find target nicknames inside the configured fixed screen rectangle.

        Matches are sorted primarily by screen Y, so the highest visible nickname
        is always selected first, preserving the existing priority rule.
        """
        self.validate()
        targets = list(usernames)
        normalized_targets = {self._normalize(name): name for name in targets}
        screenshot, offset_x, offset_y = self.capture_nickname_area()
        processed = self._preprocess(screenshot)

        output_dir = Path(__file__).resolve().parent.parent / "screenshots"
        output_dir.mkdir(parents=True, exist_ok=True)
        processed.save(output_dir / "ocr_nickname_area_processed.png")

        lang = str(self.settings.get("ocr_lang", "rus+eng"))
        psm = int(self.settings.get("ocr_psm", 11))
        config = f"--oem 3 --psm {psm}"
        data = pytesseract.image_to_data(processed, lang=lang, config=config, output_type=Output.DICT)

        scale = int(self.settings.get("ocr_scale", 3))
        matches: list[OCRMatch] = []
        seen: set[tuple[str, int, int]] = set()

        for i, raw in enumerate(data["text"]):
            text = (raw or "").strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1
            if conf < float(self.settings.get("min_ocr_confidence", 25)):
                continue

            norm = self._normalize(text)
            if not norm:
                continue

            best_user = None
            best_score = 0.0
            for target_norm, target_original in normalized_targets.items():
                score = 1.0 if norm == target_norm else difflib.SequenceMatcher(None, norm, target_norm).ratio()
                if score > best_score:
                    best_score = score
                    best_user = target_original

            if best_user is None:
                continue

            threshold = float(self.settings.get("fuzzy_threshold", 0.84))
            if len(self._normalize(best_user)) <= 3:
                threshold = max(threshold, 0.92)
            if best_score < threshold:
                continue

            left = int(data["left"][i]) // scale + offset_x
            top = int(data["top"][i]) // scale + offset_y
            width = max(1, int(data["width"][i]) // scale)
            height = max(1, int(data["height"][i]) // scale)
            key = (self._normalize(best_user), left, top)
            if key in seen:
                continue
            seen.add(key)
            matches.append(OCRMatch(best_user, best_score, left, top, width, height, text))

        matches.sort(key=lambda m: (m.y, m.x))
        self.logger.info(
            "OCR nickname-area scan (%d,%d,%d,%d): %d target matches found: %s",
            offset_x, offset_y, screenshot.width, screenshot.height, len(matches),
            [f"@{m.username}@y={m.y}/score={m.score:.2f}/raw={m.raw_text!r}" for m in matches],
        )
        return matches

