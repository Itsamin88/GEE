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

CONTROL_VERBS = ("pause", "resume", "cancel", "status", "runs", "clear-requests",
                 "retry-failed", "export", "reconcile", "audit")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dcr",
        description="Deep documentary research crawler for intentional sustainable communities.",
        epilog="Control a running crawl with:  dcr pause | resume | cancel | status | runs",
    )
    parser.add_argument("command", nargs="?", choices=CONTROL_VERBS,
                        help="Control a run that is already going, or recover one. "
                             "Omit to start a run.")
    parser.add_argument("community", nargs="?",
                        help="A community id (C007) for the control verbs that take "
                             "one. Omit to act on the whole run.")
    parser.add_argument("--communities", type=Path,
                        help="A CSV or JSON file of communities to run, instead of "
                             "typing them in.")
    parser.add_argument("--workers", type=int,
                        help="Most communities to research at once. The default "
                             "adapts to the machine; this is an upper bound, not a "
                             "target.")
    parser.add_argument("--single", action="store_true",
                        help="Research ONE community in this process, the way earlier "
                             "versions did. Useful for debugging a single crawl.")
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


def _control(command: str, root: Path | None, reason: str,
             community: str | None = None) -> int:
    """The verbs that talk to a run already going in another process.

    All of them work from a second terminal while the first is occupied by the
    dashboard, and all of them work when nothing is running at all — a pause
    left for a run that has not started yet is honoured when it does
    (brief §18, §33, §35).
    """
    settings = load_settings(root) if root else load_settings()
    output_root = settings.output_root

    if community and command in ("pause", "resume", "cancel"):
        return _control_one(settings, command, community, reason)
    if command in ("retry-failed", "export", "reconcile", "audit"):
        return _recover(settings, command, community, reason)

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
        from .orchestrator.recovery import find_interrupted
        from .orchestrator.store import RunStore

        store = RunStore(output_root / "run.sqlite3")
        try:
            runs = find_interrupted(store)
            if not runs:
                print("No unfinished runs.")
                return 0
            print(f"{len(runs)} unfinished run(s):\n")
            for run in runs:
                print(f"  {run.describe()}")
            print("\nContinue the most recent by running the program again: it offers")
            print("to resume before it offers to start anything new.")
        finally:
            store.close()
        return 0
    return 1


def _control_one(settings: object, command: str, job_id: str, reason: str) -> int:
    """Pause, resume or cancel ONE community without touching the others (§34)."""
    from .control import request_cancel as cancel_one
    from .control import request_pause as pause_one
    from .control import request_resume as resume_one
    from .orchestrator.store import RunStore

    store = RunStore(settings.output_root / "run.sqlite3")
    try:
        job = store.job(job_id.upper())
        if job is None:
            print(f"No community {job_id!r} in this run. Try:  dcr status")
            return 1
        directory = Path(job.output_dir)
        if command == "pause":
            pause_one(directory, reason or f"{job.job_id} paused by the researcher")
            print(f"PAUSE requested for {job.job_id} ({job.name}).")
            print("It stops at its next safe boundary and its worker goes to the next")
            print("community in the queue. Everything else keeps running.")
        elif command == "resume":
            resume_one(directory, reason or f"{job.job_id} resumed")
            store.update_job(job.job_id, {"state": "QUEUED",
                                          "detail": "resume requested"})
            print(f"RESUME requested for {job.job_id}; it goes back in the queue.")
        else:
            cancel_one(directory, reason or f"{job.job_id} cancelled")
            print(f"CANCEL requested for {job.job_id}. Everything it already found "
                  "is kept.")
        return 0
    finally:
        store.close()


def _recover(settings: object, command: str, job_id: str | None, reason: str) -> int:
    """The recovery verbs, none of which touches the network (§102, §103, §105)."""
    from .orchestrator.recovery import (find_interrupted, plan_resume, apply_resume,
                                        queue_offline_pass)
    from .orchestrator.store import RunStore

    store = RunStore(settings.output_root / "run.sqlite3")
    try:
        runs = find_interrupted(store, limit=1)
        if not runs:
            latest = store.latest_run()
            if latest is None:
                print("No run to recover. Start one by running the program.")
                return 1
            run_id = str(latest["run_id"])
        else:
            run_id = runs[0].run_id

        if command == "retry-failed":
            plan = plan_resume(store, run_id, retry_failed=True)
            print(plan.describe())
            moved = apply_resume(store, plan)
            print(f"\n{moved} community(ies) requeued. Run the program to work them.")
            return 0

        mode = command.upper()
        queued = queue_offline_pass(store, run_id, mode,
                                    job_ids=[job_id.upper()] if job_id else None)
        if not queued:
            print(f"Nothing to {mode}: no community in {run_id} has stored evidence.")
            return 1
        print(f"{mode} queued for {len(queued)} community(ies), offline — no page")
        print("will be fetched. Run the program to carry it out.")
        return 0
    finally:
        store.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command:
        return _control(args.command, args.root, args.reason, args.community)

    setup_logging()
    settings = load_settings(args.root) if args.root else load_settings()
    if args.single or args.name:
        # One community, in this process. The multi-community path is the
        # default; this exists for debugging a single crawl, and for the
        # non-interactive `--name` form that scripts and the test suite use.
        return _run_single(settings, args)
    return _run_many(settings, args)


def _run_many(settings, args) -> int:
    """The default: however many communities the researcher has, in parallel."""
    from .orchestrator import prompts
    from .orchestrator.recovery import (apply_resume, find_interrupted, plan_resume,
                                        queue_offline_pass, repair)
    from .orchestrator.session import RunSession, read_community_file

    print(prompts.BANNER)
    session = RunSession(settings=settings)
    try:
        _preflight(settings)

        # A run that did not finish is offered before anything new is started.
        # Quietly starting a second run beside an unfinished one would leave the
        # researcher with two half-finished cohorts (brief §100).
        interrupted = find_interrupted(session.store)
        if interrupted and not args.communities:
            choice = prompts.offer_resume(interrupted)
            if choice is not None:
                run_id, action = choice
                return _continue_run(session, run_id, action, args)

        if args.communities:
            entries = read_community_file(args.communities)
            print(f"  {len(entries)} communities read from {args.communities}")
        else:
            entries = prompts.collect_communities(
                output_root=settings.output_root, coder=args.coder)
        if not entries:
            print("  No communities entered. Nothing to do.")
            return 0

        plan = session.create(entries, mode=args.mode)
        prompts.show_queue(plan)
        if not args.no_estimate:
            prompts.show_estimate(session.estimate_text(
                workers_high=args.workers or 16))
        if not args.yes and not prompts.confirm_start():
            print("  Nothing was crawled. The queue is saved; run again to start it.")
            return 0

        summary = session.start(workers_max=args.workers)
        prompts.show_summary(summary, settings.output_root)
        return 0 if not summary["communities"]["failed"] else 2
    except KeyboardInterrupt:
        print("\n\nInterrupted. Everything retrieved so far is saved and the run is")
        print("recorded as unfinished rather than complete. Run the program again")
        print("and it will offer to resume.")
        return 130
    finally:
        session.close()


def _continue_run(session, run_id: str, action: str, args) -> int:
    """Resume, retry or rebuild a run that did not finish (brief §100-§105)."""
    from .orchestrator import prompts
    from .orchestrator.plan import RunPlan
    from .orchestrator.recovery import (apply_resume, plan_resume,
                                        queue_offline_pass, repair)

    session.run_id = run_id
    repair(session.store, run_id)

    if action in ("resume", "retry"):
        plan = plan_resume(session.store, run_id, retry_failed=(action == "retry"))
        prompts.show_recovery_plan(plan)
        if not args.yes and not prompts.ask_yes("\n  Continue?", True):
            return 0
        apply_resume(session.store, plan)
    else:
        queued = queue_offline_pass(session.store, run_id, action.upper())
        if not queued:
            print(f"  Nothing to {action.upper()}: no community has stored evidence.")
            return 1
        print(f"  {action.upper()} queued for {len(queued)} community(ies). "
              "No page will be fetched.")

    # Rebuild the plan from the queue: the jobs are already in the database and
    # the scheduler works from them, not from what was typed originally.
    session.plan = RunPlan(run_id=run_id, mode=args.mode)
    from .orchestrator.plan import CommunityJob

    for job in session.store.jobs(run_id):
        session.plan.jobs.append(CommunityJob(
            job_id=job.job_id, site_id=job.site_id, name=job.name, urls=job.urls,
            latitude=job.latitude, longitude=job.longitude, country=job.country,
            coder_id=job.coder_id, mode=job.mode, fixture=job.fixture,
            workload_units=job.workload_units, estimate_low_s=job.estimate_low_s,
            estimate_high_s=job.estimate_high_s, priority=job.priority,
            output_dir=job.output_dir, database_path=job.database_path,
        ))
    summary = session.start(workers_max=args.workers)
    prompts.show_summary(summary, session.output_root)
    return 0 if not summary["communities"]["failed"] else 2


def _preflight(settings) -> None:
    """Audit the workbook template and report the optional features, once."""
    from .config import detect_optional_features
    from .workbook_audit import audit

    result = audit(settings.workbook_template, settings.schema)
    result.raise_if_failed()
    features = detect_optional_features(settings)
    missing = [f for f in features if not f.available]
    if missing:
        print(f"  {len(features) - len(missing)} of {len(features)} optional features "
              "available. Without the others the program still runs and records what")
        print("  it could not do:")
        for feature in missing[:6]:
            print(f"    - {feature.name}: {feature.degrades_to}")
        print()


def _run_single(settings, args) -> int:
    """One community, in this process — the shape earlier versions had."""
    from .app import Application, collect_input

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
