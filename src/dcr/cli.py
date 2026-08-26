"""Command-line entry point. ``RUN.py`` calls straight into this.

Two shapes of invocation:

    python3 RUN.py                     the interactive prompts
    python3 RUN.py --name "..."        one run, non-interactively
    python3 RUN.py pause               ask a running crawl to stop safely
    python3 RUN.py resume              let it continue
    python3 RUN.py cancel              end it, keeping what it found
    python3 RUN.py status              where is it now
    python3 RUN.py runs                what is unfinished

The control verbs are deliberately usable from a second terminal while a crawl
occupies the first (brief §18).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .app import Application, RUN_MODES, collect_input
from .config import load_settings
from .console import format_status
from .control import (clear_requests, find_interrupted_runs, read_status,
                      request_cancel, request_pause, request_resume)
from .logging_setup import setup_logging
from .runner import CommunityInput

CONTROL_VERBS = ("pause", "resume", "cancel", "status", "runs", "clear-requests")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dcr",
        description="Deep documentary research crawler for intentional sustainable communities.",
        epilog="Control a running crawl with:  dcr pause | resume | cancel | status | runs",
    )
    parser.add_argument("command", nargs="?", choices=CONTROL_VERBS,
                        help="Control a crawl that is already running. Omit to start one.")
    parser.add_argument("--name", help="Community name. Omit for the interactive prompt.")
    parser.add_argument("--lat", type=float, help="Researcher latitude (optional).")
    parser.add_argument("--lon", type=float, help="Researcher longitude (optional).")
    parser.add_argument("--country", help="Country, improving local-language search.")
    parser.add_argument("--url", action="append", default=[],
                        help="A source URL. Repeat for each address; omit for none.")
    parser.add_argument("--mode", default="FULL", choices=RUN_MODES,
                        help="Run mode (default FULL).")
    parser.add_argument("--target", help="Address id for a SOURCE run.")
    parser.add_argument("--coder", default="", help="Coder id stamped on the rows.")
    parser.add_argument("--fixture", action="store_true",
                        help="Mark this run as fixture-derived test data, never research evidence.")
    parser.add_argument("--reason", default="", help="Why, for pause and cancel.")
    parser.add_argument("--no-estimate", action="store_true",
                        help="Skip the workload estimate and start crawling immediately.")
    parser.add_argument("--yes", action="store_true",
                        help="Do not ask for confirmation after the estimate.")
    parser.add_argument("--root", type=Path, help="Project root (defaults to the repository).")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _control(command: str, root: Path | None, reason: str) -> int:
    """The verbs that talk to a crawl already running in another process."""
    settings = load_settings(root) if root else load_settings()
    output_root = settings.output_root
    if command == "pause":
        request_pause(output_root, reason or "paused by the researcher")
        print("PAUSE requested. The crawl stops at its next safe boundary, writes a")
        print("checkpoint, and becomes PAUSED_MANUAL. Resume with:  dcr resume")
        return 0
    if command == "resume":
        request_resume(output_root, reason or "resumed by the researcher")
        print("RESUME requested. A crawl waiting on a pause continues from its last")
        print("checkpoint. If no crawl is running, start one in mode RESUME.")
        return 0
    if command == "cancel":
        request_cancel(output_root, reason or "cancelled by the researcher")
        print("CANCEL requested. The run ends and will NOT resume by itself.")
        print("Everything already retrieved is kept and can still be exported.")
        return 0
    if command == "clear-requests":
        clear_requests(output_root)
        print("Pending pause/resume/cancel requests cleared.")
        return 0
    if command == "status":
        print(format_status(read_status(output_root)))
        return 0
    if command == "runs":
        from .db import Database

        db = Database(settings.database_path)
        try:
            runs = find_interrupted_runs(db)
            if not runs:
                print("No unfinished runs.")
                return 0
            print(f"{len(runs)} unfinished run(s):\n")
            for run in runs:
                print(f"  {run.describe()}")
                if run.pause_reason:
                    print(f"      reason: {run.pause_reason}")
                if run.pending_tasks:
                    print(f"      {run.pending_tasks} queued task(s) waiting")
            print("\nResume the most recent with:  dcr --name \"<community>\" --mode RESUME")
        finally:
            db.close()
        return 0
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command:
        return _control(args.command, args.root, args.reason)

    setup_logging()
    settings = load_settings(args.root) if args.root else load_settings()
    app = Application(settings)
    console = None
    try:
        app.preflight()
        if args.name:
            community = CommunityInput(
                name=args.name, latitude=args.lat, longitude=args.lon,
                urls=list(args.url), country=args.country, coder_id=args.coder,
                fixture=args.fixture,
            )
            mode, target = args.mode, args.target
        else:
            resume = app.offer_resume()
            if resume is not None:
                community = CommunityInput(name=resume.community_name,
                                           coder_id=args.coder or f"DCR/{__version__}",
                                           fixture=args.fixture)
                mode, target = "RESUME", None
                print(f"\n  Resuming {resume.community_name} from "
                      f"{resume.describe()}\n")
            else:
                community, mode, target = collect_input()
                community.fixture = args.fixture

        # A pause left over from a previous session must not stop this run
        # before it starts.
        clear_requests(settings.output_root)

        estimate_first = not args.no_estimate and mode not in ("EXPORT", "AUDIT")
        if estimate_first and not args.yes and not args.name:
            estimate = app.estimate_workload(community, mode=mode)
            if estimate is not None:
                answer = input("\n  Start the crawl now? (yes / no) [yes]: ").strip().lower()
                if answer and not answer.startswith("y"):
                    print("  Nothing was crawled. Run again when you are ready.")
                    return 0
            estimate_first = False      # already done, do not repeat it

        console = _start_console(app, settings)
        app.run(community, mode=mode, target=target, estimate_first=estimate_first)
    except KeyboardInterrupt:
        print("\nInterrupted. Everything retrieved so far is saved, and the run is")
        print("recorded as unfinished rather than complete. Continue it with:")
        print('   dcr --name "<community>" --mode RESUME')
        return 130
    finally:
        if console is not None:
            console.stop()
        app.close()
    return 0


def _start_console(app: Application, settings: object) -> object | None:
    """Let the researcher type pause/resume/cancel at the running crawl."""
    from .console import ConsoleController

    controller = ConsoleController(app.settings.output_root)
    if controller.start():
        return controller
    return None


if __name__ == "__main__":
    sys.exit(main())
