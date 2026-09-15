from __future__ import annotations

import json
import time
from pathlib import Path

from app.controller import ApplicationController
from utils.logger import logger
from utils.keyboard import force_english_layout


def load_settings() -> dict:
    path = Path(__file__).resolve().parent / "config" / "settings.json"
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def wait_with_progress(seconds: float, stage: str) -> None:
    seconds = max(0.0, float(seconds))
    logger.info("Stage: %s. Waiting %.1f seconds...", stage, seconds)
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(1.0, remaining))
    logger.info("Wait finished: %s", stage)


def run_workflow() -> int:
    settings = load_settings()
    workflow = settings.get("workflow", {})
    controller = ApplicationController()

    messages_to_ocr = float(workflow.get("messages_to_ocr_wait_seconds", 20))
    ocr_to_close = float(workflow.get("ocr_to_close_wait_seconds", 10))

    try:
        logger.info("========== TikTok Messenger automated workflow START ==========")

        logger.info("Stage 0/4: Force English keyboard layout")
        try:
            changed = force_english_layout()
            logger.info("English keyboard layout requested before TikTok launch: %s", changed)
        except Exception as exc:
            logger.warning("Could not force English keyboard layout before launch: %s", exc)

        logger.info("Stage 1/4: Launch TikTok App")
        controller.launch_tiktok()

        logger.info("Stage 2/4: Wait for and Open Messages")
        controller.open_messages()

        wait_with_progress(messages_to_ocr, "between Stage 2 and Stage 3")

        logger.info("Stage 3/4: Run OCR messaging")
        controller.run_messaging()

        wait_with_progress(ocr_to_close, "between Stage 3 and Stage 4")

        logger.info("Stage 4/4: Close TikTok App")
        controller.close_tiktok()

        logger.info("========== TikTok Messenger automated workflow FINISHED ==========")
        return 0

    except KeyboardInterrupt:
        logger.warning("Workflow interrupted by user (Ctrl+C). Closing TikTok App...")
        controller.close_tiktok()
        return 130
    except Exception:
        logger.exception("Workflow failed. Closing TikTok App...")
        controller.close_tiktok()
        return 1


if __name__ == "__main__":
    raise SystemExit(run_workflow())
