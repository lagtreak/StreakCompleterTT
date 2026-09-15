# TikTokMessenger Stage 17

This version is based on the working Stage 13/14 automation, with a focused fix for Chrome App window state and changing window handles.

## Stage 17 changes

- TikTok is forcibly maximized immediately after launch.
- The code no longer calls `SW_RESTORE` on an already-maximized window. That was able to temporarily restore the app to a windowed state.
- If the app is minimized, it is restored first and then maximized.
- The current TikTok window is refreshed before important actions because the Chrome app may recreate its top-level HWND.
- Foreground activation is performed through WinAPI before screen-coordinate actions.
- The existing workflow timings, OCR flow, nickname coordinates, `scroll_steps=-50`, and Stage 13 clipboard send sequence are otherwise preserved.

## Run

```powershell
.\.venv\Scripts\python.exe main.py
```

## Expected workflow

1. Launch TikTok app and force maximize.
2. Wait 60 seconds.
3. Click Messages at `(101,570)`.
4. Wait 15 seconds.
5. Force maximize/refresh the current TikTok window, then click `(404,75)`.
6. Wait 20 seconds.
7. OCR messaging workflow.
8. Wait 10 seconds.
9. Close TikTok.

Logs are written to `logs/application.log` and screenshots to `screenshots/`.
