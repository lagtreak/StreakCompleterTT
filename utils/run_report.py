from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional


@dataclass(frozen=True)
class StageMark:
    name: str
    timestamp: datetime


class RunReport:
    """Collects one workflow run's stage times and messaging results."""

    def __init__(self) -> None:
        self.started_at = datetime.now()
        self.finished_at: Optional[datetime] = None
        self.stages: list[StageMark] = []
        self.successful_users: list[str] = []
        self.failed_users: list[str] = []
        self.total_users: Optional[int] = None
        self.status = "Выполнение"
        self.error_message: Optional[str] = None
        self.current_stage = "Старт"
        self.stage("Старт")

    def stage(self, name: str) -> None:
        self.current_stage = name
        self.stages.append(StageMark(name=name, timestamp=datetime.now()))

    def set_total_users(self, total: int) -> None:
        self.total_users = max(0, int(total))

    def set_results(self, successful: Iterable[str], failed: Iterable[str]) -> None:
        self.successful_users = self._unique_names(successful)
        self.failed_users = [
            name for name in self._unique_names(failed)
            if name.casefold() not in {success.casefold() for success in self.successful_users}
        ]

    def complete(self, status: str, error_message: Optional[str] = None) -> None:
        self.status = status
        self.error_message = error_message
        self.finished_at = datetime.now()

    def duration_seconds(self) -> float:
        end = self.finished_at or datetime.now()
        return max(0.0, (end - self.started_at).total_seconds())

    @staticmethod
    def _unique_names(names: Iterable[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for raw_name in names:
            name = str(raw_name).lstrip("@").strip()
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(name)
        return result

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total = int(round(seconds))
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours} ч {minutes:02d} мин {seconds:02d} сек"
        if minutes:
            return f"{minutes} мин {seconds:02d} сек"
        return f"{seconds} сек"

    def to_telegram_text(self) -> str:
        if self.status == "Успешно завершено":
            title = "✅ StreakCompleterTT завершён"
        elif self.status == "Прервано":
            title = "⚠️ StreakCompleterTT прерван"
        elif self.status == "Ошибка":
            title = "❌ StreakCompleterTT завершён с ошибкой"
        else:
            title = "🤖 StreakCompleterTT"

        lines = [
            title,
            "",
            f"📅 Дата: {self.started_at.strftime('%d.%m.%Y')}",
            f"🕒 Старт: {self.started_at.strftime('%H:%M:%S')}",
        ]

        if self.finished_at:
            lines.append(f"🕒 Завершение: {self.finished_at.strftime('%H:%M:%S')}")
        lines.append(f"⏱ Общее время: {self._format_duration(self.duration_seconds())}")

        lines.extend([
            "",
            "📨 Результат:",
            f"👥 Всего пользователей: {self.total_users if self.total_users is not None else '—'}",
            f"✅ Получили сообщение: {len(self.successful_users)}",
            f"❌ Не получили сообщение: {len(self.failed_users)}",
        ])

        if self.failed_users:
            lines.append("")
            lines.append("Не получили:")
            lines.extend(f"• {name}" for name in self.failed_users)

        if self.total_users is not None:
            known = len(self.successful_users) + len(self.failed_users)
            not_processed = max(0, self.total_users - known)
            if not_processed:
                lines.extend([
                    "",
                    f"❔ Не обработаны / результат неизвестен: {not_processed}",
                ])

        lines.extend(["", "⏱ Переходы по стадиям:"])
        for index, mark in enumerate(self.stages):
            lines.append(f"{mark.name} — {mark.timestamp.strftime('%H:%M:%S')}")

        if self.error_message:
            lines.extend([
                "",
                f"📍 Стадия ошибки: {self.current_stage}",
                f"⚠️ Ошибка: {self.error_message}",
            ])

        return "\n".join(lines)
