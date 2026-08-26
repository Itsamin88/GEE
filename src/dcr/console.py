"""Typing `pause` at the running crawl.

The researcher should not have to reach for Ctrl+C to stop a crawl safely
(brief §18). Three ways in are provided, and all three end in the same place —
a request file the supervisor picks up at its next safe boundary:

* type ``pause``, ``resume``, ``cancel`` or ``status`` into the console the
  crawl is running in, which is what a PyCharm Run window offers;
* press the buttons in ``tools/control_panel.py``;
* run ``dcr pause`` in a second terminal.

The listener below is the first of those. It reads standard input on a daemon
thread, so a crawl that is deep inside an await still notices, and a console
with no keyboard attached — a scheduled run, a redirected stdin — simply gets
no listener and carries on.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Callable

from .control import request_cancel, request_pause, request_resume, read_status
from .logging_setup import get_logger

log = get_logger("console")

HELP = ("  Type  pause  to stop safely,  resume  to continue, "
        "cancel  to end the run, or  status  to see where it is.")


class ConsoleController:
    """Watches the console for pause/resume/cancel while a crawl runs."""

    def __init__(self, output_root: Path, *, stream: object | None = None,
                 on_message: Callable[[str], None] | None = None):
        self.output_root = Path(output_root)
        self._stream = stream if stream is not None else sys.stdin
        self._on_message = on_message or (lambda line: print(line))
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.commands_seen: list[str] = []

    # -- lifecycle ---------------------------------------------------------
    def usable(self) -> bool:
        """Is there a console to read from at all?"""
        stream = self._stream
        if stream is None or getattr(stream, "closed", False):
            return False
        try:
            return bool(stream.isatty())
        except (AttributeError, ValueError):
            return False

    def start(self) -> bool:
        if self._thread is not None or not self.usable():
            return False
        self._thread = threading.Thread(target=self._loop, name="dcr-console",
                                        daemon=True)
        self._thread.start()
        self._on_message(HELP)
        return True

    def stop(self) -> None:
        self._stop.set()

    # -- the loop ----------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                line = self._stream.readline()
            except (ValueError, OSError):
                return
            if not line:
                return
            self.handle(line.strip())

    def handle(self, command: str) -> str:
        """Act on one typed command. Returns what was said back."""
        word = (command or "").strip().lower()
        if not word:
            return ""
        self.commands_seen.append(word)
        if word in ("pause", "p"):
            request_pause(self.output_root, "paused from the console")
            message = "  PAUSE requested — the crawl will stop at its next safe boundary."
        elif word in ("resume", "r", "continue"):
            request_resume(self.output_root, "resumed from the console")
            message = "  RESUME requested."
        elif word in ("cancel", "stop", "abort"):
            request_cancel(self.output_root, "cancelled from the console")
            message = ("  CANCEL requested — the run will end. Everything already "
                       "retrieved is saved.")
        elif word in ("status", "s", "?"):
            message = _format_status(read_status(self.output_root))
        elif word in ("help", "h"):
            message = HELP
        else:
            message = f"  {command!r} is not a command.\n{HELP}"
        self._on_message(message)
        return message


def _format_status(status: dict | None) -> str:
    """The status block of brief §28."""
    if not status:
        return "  No run status recorded yet."
    lines = [
        f"  Status: {status.get('state', 'UNKNOWN')}",
    ]
    if status.get("stage_no") is not None:
        stage = f"  Stage: {status['stage_no']}/9"
        if status.get("stage_name"):
            stage += f"  ({status['stage_name']})"
        lines.append(stage)
    if status.get("source_id"):
        lines.append(f"  Source: {status['source_id']}")
    total = status.get("tasks_total") or 0
    done = status.get("tasks_done") or 0
    lines.append(f"  Progress: {done}/{total} tasks" if total
                 else f"  Progress: {done} tasks")
    lines.append(f"  Internet: {status.get('connectivity', 'UNKNOWN')}")
    if status.get("pause_reason"):
        lines.append(f"  Reason: {status['pause_reason']}")
    pauses = (status.get("pauses_manual") or 0) + (status.get("pauses_network") or 0)
    if pauses:
        lines.append(f"  Pauses so far: {status.get('pauses_manual', 0)} manual, "
                     f"{status.get('pauses_network', 0)} network")
    return "\n".join(lines)


format_status = _format_status
