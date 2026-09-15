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


## Startup window behavior

After TikTok starts, the script keeps the TikTok window explicitly topmost and foreground for 10 seconds. During this period it periodically re-detects the current TikTok HWND because Chrome app windows can be recreated. After the 10-second hold, the permanent TOPMOST flag is removed and TikTok remains foreground.

The duration is configurable as `automation.startup_topmost_seconds` in `config/settings.json`.
