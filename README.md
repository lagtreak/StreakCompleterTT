# StreakCompleterTT

This version uses `launcher.py` as the entry point. The launcher is designed for use with Windows Task Scheduler and scheduled wake from hibernation.

## Start manually

Run:

```text
.\\.venv\\Scripts\\python.exe launcher.py
```

or run `Start.bat`.

The launcher:

1. Keeps Windows awake while it is preparing the workflow.
2. Requests the monitor to turn on after a scheduled wake and sends a tiny synthetic mouse movement as a fallback wake signal.
3. Waits for Windows to finish resuming.
4. Requests the English keyboard layout for the foreground window.
5. Waits until the configured Wi-Fi connection and internet are ready.
6. Keeps the display and system awake while `main.py` performs the TikTok workflow.
7. Clears its power-management request when `main.py` exits.

The wake/display timings are configurable under `launcher` in `config/settings.json`.

## Windows Task Scheduler

Create one daily task for `launcher.py` / `Start.bat`.

Recommended settings:

### General

- Choose the same Windows user account that normally runs the TikTok app.
- Select **Run only when user is logged on**. This is important because the automation uses the interactive desktop, mouse/keyboard input and OCR.
- Select **Run with highest privileges**.

### Triggers

Create a daily trigger at the required time, for example 03:00.

### Actions

Use either:

```text
Program/script:
C:\Windows\System32\cmd.exe

Add arguments:
/c "C:\Path\To\StreakCompleterTT\Start.bat"

Start in:
C:\Path\To\StreakCompleterTT
```

or directly:

```text
Program/script:
C:\Path\To\StreakCompleterTT\.venv\Scripts\python.exe

Add arguments:
"C:\Path\To\StreakCompleterTT\launcher.py"

Start in:
C:\Path\To\StreakCompleterTT
```

The second form is simpler and avoids an extra `cmd.exe` process.

### Conditions

Enable:

- **Wake the computer to run this task**.

Do not require network availability here, because `launcher.py` already waits for the configured Wi-Fi networks and checks internet access itself.

### Settings

Useful settings:

- **Allow task to be run on demand** — enable.
- **If the task is already running** — choose **Do not start a new instance**.
- Avoid a short execution time limit, because the launcher can legitimately wait for Wi-Fi or a slow wake/resume.

## Important power check

Before the first overnight test, run these commands in Command Prompt:

```text
powercfg /waketimers
powercfg /lastwake
```

`/waketimers` lists active wake timers. `/lastwake` reports what woke Windows last time.

## Scheduled wake behavior

Windows Task Scheduler can wake a computer from sleep or hibernation with **WakeToRun**. Microsoft also documents that after such a scheduled wake, Windows can resume while the screen remains off. This launcher therefore adds an explicit display wake step before starting the automation.


## Message input readiness

After opening each target chat, the script no longer clicks the message input field. It waits for OCR text to appear in the fixed screen area `(520, 1020, 300, 40)`. As soon as any text with sufficient OCR confidence is detected there, the script immediately runs the existing `Ctrl+A` / `Ctrl+V` / `Enter` sequence.

This replaces the old coordinate click at `(600, 1040)` and removes the race where the chat page could still be updating when the click happened, causing Ctrl+A to select the page instead of the input field.

The readiness OCR is configurable with:

```text
automation.message_input_ocr_x
automation.message_input_ocr_y
automation.message_input_ocr_width
automation.message_input_ocr_height
automation.message_input_ocr_timeout_seconds
automation.message_input_ocr_poll_seconds
automation.message_input_ocr_min_confidence
```

## Telegram execution reports

After each workflow run, the program can send a report to a Telegram bot. The report includes:

- date and start/end time;
- total execution duration;
- number of users who received the message;
- number and nicknames of users who did not receive it;
- unprocessed users when their result cannot be determined;
- exact local times when each workflow stage started;
- the stage and error text when the run fails.

Telegram is configured in `config/telegram.json`. The project uses only Python's standard library for the Telegram Bot API, so no extra package is required.

### First-time Telegram setup

1. Open the configured bot in Telegram.
2. Press **Start** or send `/start` from your private chat with the bot.
3. Run the workflow once. With `chat_id` set to `auto`, the program finds the private chat automatically and caches the chat id in `config/telegram_chat_id.txt`.

The bot token is stored in `config/telegram.json`, which is ignored by Git. Never publish that file to a public repository. For another PC, copy `config/telegram.json` together with the project, then send `/start` to the bot once on that PC if the cached chat id is not copied.

To disable notifications without removing the integration, set `enabled` to `false` in `config/telegram.json`.
