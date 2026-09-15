from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from utils.keyboard import force_english_layout


PROJECT_DIR = Path(__file__).resolve().parent
MAIN_SCRIPT = PROJECT_DIR / "main.py"
PYTHON_EXE = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
START_DELAY_SECONDS = 1.0


def launch_main() -> int:
    python_exe = PYTHON_EXE if PYTHON_EXE.exists() else Path(sys.executable)

    print("Switching keyboard layout to English...")
    try:
        changed = force_english_layout()
        print(f"English keyboard layout requested: {changed}")
    except Exception as exc:
        print(f"Could not force English keyboard layout: {exc}")

    print(f"Waiting {START_DELAY_SECONDS:.1f} second before starting main.py...")
    time.sleep(START_DELAY_SECONDS)

    command = [str(python_exe), str(MAIN_SCRIPT)]
    print(f"Starting main.py with: {python_exe}")
    completed = subprocess.run(command, cwd=str(PROJECT_DIR))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(launch_main())
