from __future__ import annotations

import json
from pathlib import Path

from models.user import User


def load_users(path: Path) -> list[User]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return [
        User(
            username=str(item.get("username", "")).strip(),
            message=str(item.get("message", "")),
            enabled=bool(item.get("enabled", True)),
        )
        for item in data
        if str(item.get("username", "")).strip()
    ]
