# TikTok Messenger — Stage 13

This stage uses the installed TikTok Chrome app and the existing Chrome `Default` profile.

## New workflow

1. `Open TikTok App` starts the installed TikTok Chrome app and maximizes it.
2. `Open Messages` clicks the Messages entry at the updated fullscreen point: base `(101, 570)` for a 1920×1080 screen.
3. After Messages is opened, the script waits **15 seconds**.
4. It then clicks the exact base screen point **`(404, 75)`** and waits again.
5. The screen is scanned by OCR **only in the left half**.
6. Matching target nicknames are sorted by Y coordinate; the uppermost match is processed first.
7. The script clicks the nickname, types **`Огонь`**, and presses Enter.
8. That nickname is added to the completed set and will not be selected again.
9. For every **second** completed nickname (2nd, 4th, 6th, ...), the mouse moves to the just-completed nickname and the script scrolls down by **50** mouse-wheel steps before the next OCR scan.
10. For odd-numbered completions, the next OCR scan is performed without the scroll step.

## Target nicknames

The default `config/users.json` contains:

`zero`, `мяу`, `Алекс`, `ангелинка`, `Ruslan`, `SGseX`, `artem._171`, `поднебесный`, `Cub3r`, `999`, `vanase2`, `v1ksstt`

## OCR requirement

`pytesseract` is a Python wrapper. Windows also needs the **Tesseract OCR engine** installed separately, including Russian (`rus`) language data.

After installing Tesseract, either make sure it is on PATH or put its executable path in:

```json
"tesseract_cmd": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
```

The default OCR language is `rus+eng`.

## Install

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then start:

```powershell
.\.venv\Scripts\python.exe main.py
```

## Important test procedure

Do the first run with **one or two nicknames** in `config/users.json`, verify that OCR selects the correct account and that the click opens the intended chat, then expand to the full list.

The application saves screenshots in `screenshots/` and logs in `logs/application.log`.

`pyautogui` has its emergency failsafe enabled: moving the mouse to the top-left corner can abort a pyautogui action.

## Stage 13 note

The message sending implementation is intentionally preserved from Stage 8: after clicking the OCR match and waiting, the script copies the configured message to the clipboard, sends `Ctrl+A`, `Ctrl+V`, and then presses Enter. No extra click on the message field is performed.
