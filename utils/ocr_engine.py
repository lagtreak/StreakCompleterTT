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

    def capture_left_half(self) -> tuple[Image.Image, int, int]:
        screen_w, screen_h = pyautogui.size()
        crop_w = screen_w // 2
        screenshot = pyautogui.screenshot()
        return screenshot.crop((0, 0, crop_w, screen_h)), 0, 0

    def find_matches(self, usernames: Iterable[str]) -> list[OCRMatch]:
        self.validate()
        targets = list(usernames)
        normalized_targets = {self._normalize(name): name for name in targets}
        screenshot, offset_x, offset_y = self.capture_left_half()
        processed = self._preprocess(screenshot)

        output_dir = Path(__file__).resolve().parent.parent / "screenshots"
        output_dir.mkdir(parents=True, exist_ok=True)
        processed.save(output_dir / "ocr_left_half_processed.png")

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
            conf_raw = data["conf"][i]
            try:
                conf = float(conf_raw)
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
                if norm == target_norm:
                    score = 1.0
                else:
                    score = difflib.SequenceMatcher(None, norm, target_norm).ratio()
                if score > best_score:
                    best_score = score
                    best_user = target_original

            if best_user is None:
                continue

            threshold = float(self.settings.get("fuzzy_threshold", 0.84))
            # Be stricter for very short names / numbers to avoid false positives.
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
            "OCR left-half scan: %d target matches found: %s",
            len(matches),
            [f"@{m.username}@y={m.y}/score={m.score:.2f}" for m in matches],
        )
        return matches
