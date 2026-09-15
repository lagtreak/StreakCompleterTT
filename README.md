# StreakCompleterTT - Messages OCR workflow update

This version is based on the user-provided `StreakCompleterTT_messages_ocr` project.

## Workflow

1. Request US English keyboard layout before launching TikTok.
2. Launch the TikTok Chrome app and force it maximized.
3. Continuously OCR the left third of the screen until `Сообщения` is detected.
4. After detection, wait 2 seconds, then click the detected label.
5. Wait 15 seconds, then click `(404,75)` as before.
6. Wait the configured 20 seconds.
7. Run the existing OCR nickname/message workflow unchanged.
8. Wait 10 seconds and close TikTok.

## Keyboard layout

The English layout is requested with the Windows input-language API before launch. The
existing clipboard send mechanism is otherwise unchanged.

## Configuration

Relevant settings are in `config/settings.json`: `messages_label_found_wait_seconds`
controls the 2-second wait after OCR finds `Сообщения`, and
`messages_ocr_timeout_seconds` controls how long the initial OCR search may continue.

Run:

```powershell
.\.venv\Scripts\python.exe main.py
```
