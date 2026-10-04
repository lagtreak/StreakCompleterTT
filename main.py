from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from app.controller import ApplicationController
from utils.logger import logger
from utils.run_report import RunReport
from utils.telegram import TelegramNotifier


PROJECT_DIR = Path(__file__).resolve().parent


def load_settings() -> dict:
    path = PROJECT_DIR / "config" / "settings.json"
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


def close_tiktok_safely(controller: ApplicationController) -> None:
    try:
        controller.close_tiktok()
    except Exception:
        logger.exception("Could not close TikTok App during workflow cleanup.")


def run_workflow() -> int:
    settings = load_settings()
    workflow = settings.get("workflow", {})
    controller = ApplicationController()
    report = RunReport()
    telegram = TelegramNotifier(PROJECT_DIR)

    ocr_to_close = float(workflow.get("ocr_to_close_wait_seconds", 10))
    hibernate_after_close = float(
        workflow.get(
            "hibernate_after_tiktok_close_seconds",
            workflow.get("shutdown_after_tiktok_close_seconds", 1),
        )
    )

    try:
        logger.info("========== TikTok Messenger automated workflow START ==========")

        report.stage("Стадия 1 — Запуск TikTok")
        logger.info("Stage 1/4: Launch TikTok App")
        controller.launch_tiktok()

        report.stage("Стадия 2 — Открытие сообщений")
        logger.info("Stage 2/4: Wait for and Open Messages")
        controller.open_messages()

        report.stage("Стадия 3 — Рассылка сообщений")
        logger.info("Stage 3/4: Wait for target nicknames, then Run OCR messaging")
        controller.run_messaging(report)

        report.stage("Стадия 3 — Подготовка к закрытию")
        wait_with_progress(ocr_to_close, "between Stage 3 and Stage 4")

        report.stage("Стадия 4 — Закрытие TikTok")
        logger.info("Stage 4/4: Close TikTok App")
        controller.close_tiktok()

        report.stage("Подготовка гибернации")
        logger.info(
            "Waiting %.1f seconds after closing TikTok before hibernating Windows...",
            hibernate_after_close,
        )
        wait_with_progress(
            hibernate_after_close,
            "between TikTok close and Windows hibernation",
        )

        report.complete("Успешно завершено")
        telegram.send_report(report)

        logger.info("Putting Windows into hibernation now.")
        subprocess.Popen(["shutdown", "/h"], close_fds=True)

        logger.info("========== TikTok Messenger automated workflow FINISHED ==========")
        return 0

    except KeyboardInterrupt:
        report.complete("Прервано", "Выполнение остановлено пользователем (Ctrl+C).")
        logger.warning("Workflow interrupted by user (Ctrl+C). Closing TikTok App...")
        close_tiktok_safely(controller)
        telegram.send_report(report)
        return 130

    except Exception as exc:
        report.complete("Ошибка", str(exc))
        logger.exception("Workflow failed. Closing TikTok App...")
        close_tiktok_safely(controller)
        telegram.send_report(report)
        return 1


if __name__ == "__main__":
    raise SystemExit(run_workflow())
