#!/usr/bin/env python3
"""A PAUSE / RESUME / CANCEL window for a running crawl.

    python3 tools/control_panel.py

The crawler is a console program, so the buttons the brief asks for (§18) live
in a small separate window rather than inside it. That is deliberate: the panel
holds no research state, talks to the crawl only through the request files in
the output directory, and can be opened, closed or crashed without the crawl
noticing. It can also be started before the crawl, or after it — a PAUSE left
behind is picked up whenever a run next reaches a safe boundary.

Tkinter ships with Python on Windows and macOS. Where it is missing (a bare
Linux image, usually) the panel says so and points at the console commands and
the `dcr pause` CLI, which do the same job.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dcr.config import load_settings                                  # noqa: E402
from dcr.control import (request_cancel, request_pause, request_resume,  # noqa: E402
                         read_status)

REFRESH_MS = 1000

_COLOURS = {
    "RUNNING": "#1b7f3b",
    "RESUMING": "#1b7f3b",
    "PAUSING": "#b06a00",
    "PAUSED_MANUAL": "#b06a00",
    "PAUSED_NETWORK": "#a3341f",
    "CANCELLING": "#a3341f",
    "CANCELLED": "#666666",
    "COMPLETED": "#1b7f3b",
    "FAILED": "#a3341f",
}


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        print("Tkinter is not available in this Python installation.")
        print("The same controls are available without it:")
        print("   - type  pause / resume / cancel / status  into the running crawl")
        print("   - or, in another terminal:  python3 RUN.py pause")
        return 2

    settings = load_settings(ROOT)
    output_root = settings.output_root

    window = tk.Tk()
    window.title("Documentary Research Crawler — run control")
    window.minsize(520, 300)

    frame = ttk.Frame(window, padding=16)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="Documentary Research Crawler",
              font=("TkDefaultFont", 13, "bold")).pack(anchor="w")
    ttk.Label(frame, text=str(output_root), foreground="#666666").pack(anchor="w")

    state_var = tk.StringVar(value="…")
    state_label = ttk.Label(frame, textvariable=state_var,
                            font=("TkDefaultFont", 16, "bold"))
    state_label.pack(anchor="w", pady=(12, 4))

    detail_var = tk.StringVar(value="Waiting for a run to report its status…")
    ttk.Label(frame, textvariable=detail_var, justify="left",
              wraplength=470).pack(anchor="w")

    progress = ttk.Progressbar(frame, mode="determinate", length=470)
    progress.pack(anchor="w", pady=(12, 12))

    buttons = ttk.Frame(frame)
    buttons.pack(anchor="w", pady=(4, 0))

    message_var = tk.StringVar(value="")
    ttk.Label(frame, textvariable=message_var, foreground="#1b4f9c",
              wraplength=470, justify="left").pack(anchor="w", pady=(12, 0))

    def do_pause() -> None:
        request_pause(output_root, "paused from the control panel")
        message_var.set("PAUSE requested. The crawl stops at its next safe boundary "
                        "and writes a checkpoint; nothing in progress is lost.")

    def do_resume() -> None:
        request_resume(output_root, "resumed from the control panel")
        message_var.set("RESUME requested. The crawl continues from its last checkpoint.")

    def do_cancel() -> None:
        request_cancel(output_root, "cancelled from the control panel")
        message_var.set("CANCEL requested. The run ends and will not resume by itself. "
                        "Everything already retrieved is kept.")

    ttk.Button(buttons, text="PAUSE", command=do_pause, width=12).pack(side="left")
    ttk.Button(buttons, text="RESUME", command=do_resume, width=12).pack(side="left",
                                                                        padx=(8, 0))
    ttk.Button(buttons, text="CANCEL", command=do_cancel, width=12).pack(side="left",
                                                                        padx=(8, 0))

    def refresh() -> None:
        status = read_status(output_root)
        if not status:
            state_var.set("NO RUN")
            detail_var.set("No run has reported a status yet. Start a crawl, or leave "
                           "this window open — a PAUSE pressed now is picked up when "
                           "one starts.")
            progress["value"] = 0
        else:
            state = str(status.get("state", "UNKNOWN"))
            state_var.set(state)
            state_label.configure(foreground=_COLOURS.get(state, "#000000"))
            done = int(status.get("tasks_done") or 0)
            total = int(status.get("tasks_total") or 0)
            lines = []
            if status.get("stage_no") is not None:
                stage = f"Stage {status['stage_no']}/9"
                if status.get("stage_name"):
                    stage += f" — {status['stage_name']}"
                lines.append(stage)
            if status.get("source_id"):
                lines.append(f"Source: {status['source_id']}")
            lines.append(f"Progress: {done}/{total} tasks" if total
                         else f"Progress: {done} tasks")
            lines.append(f"Internet: {status.get('connectivity', 'UNKNOWN')}")
            if status.get("pause_reason"):
                lines.append(f"Reason: {status['pause_reason']}")
            if status.get("checkpoint_utc"):
                lines.append(f"Last checkpoint: {status['checkpoint_utc']}")
            detail_var.set("\n".join(lines))
            progress["maximum"] = max(total, 1)
            progress["value"] = min(done, max(total, 1))
        window.after(REFRESH_MS, refresh)

    refresh()
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
