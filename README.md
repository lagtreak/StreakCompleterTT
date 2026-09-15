# StreakCompleterTT

This version adds a separate launcher step for keyboard-layout handling.

## Start

Run:

```text
.\.venv\Scripts\python.exe launcher.py
```

or run `Start.bat`.

The launcher first requests the English keyboard layout, waits 1 second, and then starts `main.py` in the project's `.venv`.

`main.py` itself no longer changes the keyboard layout; it starts directly with the TikTok workflow.
