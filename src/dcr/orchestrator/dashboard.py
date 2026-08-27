"""What the researcher sees while two hundred communities are running.

The brief is blunt about the audience (§51): *the system should be usable by a
researcher, not a developer*. A scrolling wall of log lines from sixteen
concurrent crawls is not a status display — it is sixteen crawls' logs
interleaved, and nobody can read it.

So the terminal keeps the detail and this owns the top of the screen: a fixed
block, redrawn in place, that answers the four questions a person actually has.

    How far through is it?      37 / 212 completed, 11 running, 164 queued
    Is anything wrong?          1 failed, 4 paused, network CONNECTED
    How much longer?            03:24:18 elapsed, 1:45–3:10 remaining
    What is it doing now?       one line per running community

## Redrawing in place, without a curses dependency

Cursor-up escape codes, and a plain-text fallback when the output is not a
terminal — a log file, a CI job, PyCharm's run window with virtual terminal
turned off. Detection is by `isatty()` plus the environment, and when in doubt
it prints rather than tries to move the cursor, because a status display that
scrolls is untidy and one that emits raw escape codes into a log is unreadable.

Nothing here reads the database. The scheduler passes its own snapshot, which
it already has; making the display query would put a reader on the queue every
second for no benefit.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .store import (CANCELLED, COMPLETED, FAILED, PAUSED_MANUAL, PAUSED_NETWORK,
                    PAUSING, QUEUED, RESUMING, RUNNING)

#: Ten stages, 0-9, so a stage number is directly a fraction of the protocol.
STAGES = 10

#: What each state looks like in the table. Deliberately words, not colours:
#: the researcher may be reading this in a log file a week later.
STATE_LABELS: dict[str, str] = {
    QUEUED: "queued",
    RUNNING: "running",
    PAUSING: "pausing",
    PAUSED_MANUAL: "paused",
    PAUSED_NETWORK: "offline",
    RESUMING: "resuming",
    COMPLETED: "complete",
    FAILED: "FAILED",
    CANCELLED: "cancelled",
}


def format_duration(seconds: float | None) -> str:
    """HH:MM:SS, because a run can last a day and 'in 3.7 hours' is not useful."""
    if seconds is None:
        return "--:--:--"
    total = int(max(0.0, float(seconds)))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def format_range(low: float | None, high: float | None) -> str:
    if not low and not high:
        return "unknown"
    if low and high and abs(high - low) < 60:
        return format_duration(high)
    return f"{format_duration(low)}–{format_duration(high)}"


def _terminal_width(default: int = 100) -> int:
    try:
        return max(70, min(200, shutil.get_terminal_size((default, 24)).columns))
    except Exception:
        return default


def supports_redraw(stream: Any = None) -> bool:
    """Can we move the cursor, or should we just print?

    When in doubt, print. A status block that scrolls is untidy; one that emits
    raw escape codes into a log file is unreadable, and the second is worse.
    """
    stream = stream or sys.stdout
    if os.environ.get("DCR_PLAIN_OUTPUT"):
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    try:
        return bool(stream.isatty())
    except Exception:
        return False


@dataclass
class Dashboard:
    """The status block. Give it a scheduler snapshot; it renders and redraws."""

    stream: Any = None
    redraw: bool | None = None
    max_rows: int = 14
    #: Never redraw faster than this: a display that flickers is worse than one
    #: that lags a second behind.
    min_interval_s: float = 0.5

    def __post_init__(self) -> None:
        self.stream = self.stream or sys.stdout
        if self.redraw is None:
            self.redraw = supports_redraw(self.stream)
        self._last_lines = 0
        self._last_drawn = 0.0
        self._last_signature = ""

    # -- rendering ---------------------------------------------------------
    def render(self, snapshot: Mapping[str, Any], *,
               network: str = "CONNECTED") -> str:
        counts = dict(snapshot.get("counts") or {})
        workers = dict(snapshot.get("workers") or {})
        totals = dict(snapshot.get("totals") or {})
        live = dict(snapshot.get("live") or {})
        width = _terminal_width()

        total = int(counts.get("TOTAL", 0))
        completed = int(counts.get(COMPLETED, 0))
        running = int(counts.get(RUNNING, 0))
        queued = int(counts.get(QUEUED, 0))
        paused = int(counts.get(PAUSED_MANUAL, 0)) + int(counts.get(PAUSED_NETWORK, 0))
        failed = int(counts.get(FAILED, 0))
        cancelled = int(counts.get(CANCELLED, 0))

        lines: list[str] = ["=" * width]
        headline = f"  {completed} / {total} communities complete"
        if snapshot.get("cancelled"):
            headline += "   — CANCELLED"
        elif snapshot.get("paused"):
            headline += "   — PAUSED"
        lines.append(headline)
        lines.append("  " + self._bar(completed, total, width - 8))
        lines.append("-" * width)

        summary = [f"running {running}", f"queued {queued}"]
        if paused:
            summary.append(f"paused {paused}")
        if failed:
            summary.append(f"FAILED {failed}")
        if cancelled:
            summary.append(f"cancelled {cancelled}")
        lines.append("  " + "   ".join(summary))

        elapsed = format_duration(snapshot.get("wall_s"))
        remaining = format_range(snapshot.get("remaining_low_s"),
                                 snapshot.get("remaining_high_s"))
        worker_line = (f"workers {workers.get('running', 0)} / "
                       f"{workers.get('target', 0)}"
                       + (f" (max {workers['maximum']})" if workers.get("maximum") else ""))
        lines.append(f"  runtime {elapsed}   remaining {remaining}   {worker_line}")
        lines.append(f"  network {network}   "
                     f"evidence {int(totals.get('evidence', 0) or 0):,}   "
                     f"documents {int(totals.get('documents', 0) or 0):,}   "
                     f"images {int(totals.get('images', 0) or 0):,}   "
                     f"workbooks {int(totals.get('workbooks', 0) or 0)}")

        active = [(job_id, state) for job_id, state in sorted(live.items())
                  if str(state.get("state")) in (RUNNING, PAUSING, RESUMING)]
        if active:
            lines.append("-" * width)
            name_width = max(12, min(30, width - 62))
            lines.append(f"  {'ID':<5} {'Community':<{name_width}} {'Stage':<7} "
                         f"{'Progress':<12} {'Doing':<20}")
            for job_id, state in active[: self.max_rows]:
                lines.append("  " + self._row(job_id, state, name_width, width))
            if len(active) > self.max_rows:
                lines.append(f"  ... and {len(active) - self.max_rows} more running")
        lines.append("=" * width)
        return "\n".join(line[:width] for line in lines)

    def _bar(self, done: int, total: int, width: int) -> str:
        width = max(10, width)
        if total <= 0:
            return "[" + " " * width + "]"
        filled = int(width * done / total)
        return "[" + "#" * filled + "." * (width - filled) + f"] {100 * done / total:.0f}%"

    def _row(self, job_id: str, state: Mapping[str, Any], name_width: int,
             width: int) -> str:
        name = str(state.get("name") or "")
        if len(name) > name_width:
            name = name[: name_width - 1] + "…"
        stage_no = state.get("stage_no")
        stage = f"{stage_no}/9" if stage_no is not None else "-"
        fraction = float(state.get("progress") or 0.0)
        bar_width = 10
        filled = int(bar_width * min(1.0, max(0.0, fraction)))
        progress = "#" * filled + "." * (bar_width - filled)
        doing = str(state.get("stage_name") or state.get("detail") or "")
        remaining = max(10, width - 8 - name_width - 7 - 12 - 4)
        if len(doing) > remaining:
            doing = doing[: remaining - 1] + "…"
        return (f"{job_id:<5} {name:<{name_width}} {stage:<7} "
                f"{progress:<12} {doing}")

    # -- drawing -----------------------------------------------------------
    def draw(self, snapshot: Mapping[str, Any], *, network: str = "CONNECTED",
             force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_drawn) < self.min_interval_s:
            return
        text = self.render(snapshot, network=network)
        if not force and text == self._last_signature:
            return
        self._last_drawn = now
        self._last_signature = text
        lines = text.split("\n")
        try:
            if self.redraw and self._last_lines:
                # Move up over the previous block and clear each line, so the
                # display stays in one place instead of scrolling the terminal.
                self.stream.write(f"\x1b[{self._last_lines}F")
                for _ in range(self._last_lines):
                    self.stream.write("\x1b[2K\x1b[1B")
                self.stream.write(f"\x1b[{self._last_lines}F")
            self.stream.write(text + "\n")
            self.stream.flush()
        except Exception:
            # A display that throws must not take a twelve-hour run with it.
            return
        self._last_lines = len(lines) if self.redraw else 0

    def finish(self, snapshot: Mapping[str, Any], *,
               network: str = "CONNECTED") -> None:
        """Draw once more and leave the block on screen."""
        self.draw(snapshot, network=network, force=True)
        self._last_lines = 0


def community_table(jobs: Sequence[Any], *, limit: int = 0) -> str:
    """Every community and how it ended: the table the final summary prints.

    One row per community, whatever happened to it, because a run of two hundred
    and twelve is only auditable if the twelve that did not work are as visible
    as the two hundred that did (brief §54, §107).
    """
    rows = list(jobs)[: limit or None]
    if not rows:
        return "no communities"
    name_width = min(34, max(9, max(len(getattr(j, "name", "")) for j in rows)))
    header = (f"{'ID':<5} {'Community':<{name_width}} {'Status':<26} "
              f"{'Src':>4} {'Doc':>4} {'Img':>4} {'Evid':>6} {'Confl':>6} "
              f"{'Active':>9} {'Workbook':<8}")
    lines = [header, "-" * len(header)]
    for job in rows:
        name = getattr(job, "name", "")
        if len(name) > name_width:
            name = name[: name_width - 1] + "…"
        status = getattr(job, "final_status", "") or STATE_LABELS.get(
            getattr(job, "state", ""), getattr(job, "state", ""))
        workbook = "yes" if getattr(job, "workbook_path", "") else "no"
        lines.append(
            f"{getattr(job, 'job_id', ''):<5} {name:<{name_width}} {status:<26} "
            f"{getattr(job, 'sources', 0):>4} {getattr(job, 'documents', 0):>4} "
            f"{getattr(job, 'images', 0):>4} {getattr(job, 'evidence', 0):>6} "
            f"{getattr(job, 'conflicts', 0):>6} "
            f"{format_duration(getattr(job, 'active_s', 0)):>9} {workbook:<8}")
    return "\n".join(lines)


__all__ = ["Dashboard", "STATE_LABELS", "community_table", "format_duration",
           "format_range", "supports_redraw"]
