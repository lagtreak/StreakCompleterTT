from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox

from app.controller import ApplicationController


class ApplicationGUI:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("TikTok Messenger - Stage 8")
        self.root.geometry("690x430")
        self.root.resizable(False, False)

        frame = tk.Frame(self.root, padx=22, pady=20)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="TikTok Messenger", font=("Segoe UI", 19, "bold")).pack(pady=(0, 8))
        tk.Label(
            frame,
            text="Stage 13: OCR search in the left half of the fullscreen TikTok window",
            fg="#555555",
        ).pack(pady=(0, 14))

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(
            frame,
            textvariable=self.status_var,
            wraplength=630,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(0, 14))

        controls = tk.Frame(frame)
        controls.pack()

        self.open_btn = tk.Button(controls, text="Open TikTok App", width=24, command=self._launch)
        self.open_btn.grid(row=0, column=0, padx=5, pady=5)

        self.messages_btn = tk.Button(controls, text="Open Messages", width=24, command=self._open_messages)
        self.messages_btn.grid(row=0, column=1, padx=5, pady=5)

        self.send_btn = tk.Button(controls, text="Run OCR messaging", width=24, command=self._send_all)
        self.send_btn.grid(row=1, column=0, padx=5, pady=5)

        self.close_btn = tk.Button(controls, text="Close TikTok App", width=24, command=self._close)
        self.close_btn.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(
            frame,
            text=(
                "Workflow:\n"
                "1) Open TikTok App  2) Open Messages  3) wait 15s + click (404,75)\n"
                "4) OCR scans only the left half  5) highest nickname by Y is selected\n"
                "6) send 'Огонь' + Enter  7) every second message scrolls down by one step."
            ),
            fg="#444444",
            justify="left",
        ).pack(pady=(20, 0), anchor="w")

        self.controller = ApplicationController(self.set_status)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def set_status(self, text: str) -> None:
        self.root.after(0, lambda: self.status_var.set(text))

    def _run_background(self, action) -> None:
        self._set_buttons(False)

        def worker():
            try:
                action()
            except Exception as exc:
                self.set_status(f"Error: {exc}")
                self.root.after(0, lambda: messagebox.showerror("TikTok Messenger", str(exc)))
            finally:
                self.root.after(0, lambda: self._set_buttons(True))

        threading.Thread(target=worker, daemon=True).start()

    def _set_buttons(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for button in (self.open_btn, self.messages_btn, self.send_btn, self.close_btn):
            button.configure(state=state)

    def _launch(self) -> None:
        self._run_background(self.controller.launch_tiktok)

    def _open_messages(self) -> None:
        self._run_background(self.controller.open_messages)

    def _send_all(self) -> None:
        confirmed = messagebox.askyesno(
            "OCR messaging",
            "Start OCR messaging for all enabled usernames in config/users.json?\n\nMessage: 'Огонь'",
        )
        if confirmed:
            self._run_background(self.controller.run_messaging)

    def _close(self) -> None:
        self._run_background(self.controller.close_tiktok)

    def _on_close(self) -> None:
        self.controller.close_tiktok()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run_app() -> None:
    ApplicationGUI().run()
