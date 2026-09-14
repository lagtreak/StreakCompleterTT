# TikTokMessenger — Manual keyboard Stage

This version is based on the working Stage 13 flow, but message entry is done with real keyboard key presses instead of the clipboard.

Workflow for each user:
1. OCR finds the highest matching nickname in the left half.
2. Click the nickname.
3. Wait 2 seconds.
4. Click the message input at `(620, 1047)` on a 1920x1080 fullscreen layout.
5. Activate the Russian keyboard layout.
6. Type `Огонь` using key presses: `Shift+J`, `U`, `J`, `Y`, `M`.
7. Press Enter.
8. Continue to the next user.

The existing Stage 13 scrolling logic remains:
- every second completed user scrolls by `-50` wheel notches over the completed nickname;
- OCR then searches again for the next target.

Run:

```powershell
.\.venv\Scripts\python.exe main.py
```

The configured message is currently `Огонь`. Manual keyboard mode is intentionally restricted to that message because the key mapping is explicit.
