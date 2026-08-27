"""What the researcher is asked, and how little of it there is.

Ten steps, of which eight are typing and two are waiting (brief §99). The
program has to be usable by someone who studies communities, not by someone who
writes crawlers, so everything technical has a default and nothing technical is
asked for.

The one place this departs from the brief's literal wording is entering the
communities. §6 shows them typed in one at a time, which is exactly right for
five and absurd for two hundred and twelve — nobody is typing six hundred URLs
at a prompt without a mistake. So the question is asked once, up front:

    How will you enter the communities?
      1. type them in            fine for a handful
      2. read them from a file   CSV or JSON — the usual way for a cohort

Both produce the same queue. The file is a convenience, not a different mode,
and the program writes an example file so the first-time answer is obvious.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .. import __version__
from .dashboard import format_duration
from .recovery import InterruptedRun, RecoveryPlan

BANNER = f"""
==============================================================================
  PARALLEL DOCUMENTARY RESEARCH CRAWLER  v{__version__}
  Stage 1 documentary coding for intentional sustainable communities
------------------------------------------------------------------------------
  Enter as many communities as you have. They are researched in parallel, and
  each runs until it stops producing evidence — not until a clock says so.

  This program records what published sources SAY. It does not evaluate
  ecological performance, never infers a practice from a photograph, and never
  estimates an area or a polygon.
==============================================================================
"""

EXAMPLE_CSV = """name,country,latitude,longitude,urls
Tamera,Portugal,37.7167,-8.5333,https://www.tamera.org; https://www.facebook.com/tamera
EcoVillage de Pourgues,France,43.0561,1.8342,https://www.pourgues.org
Findhorn,Scotland,,,https://www.findhorn.org; https://en.wikipedia.org/wiki/Findhorn_Ecovillage
"""


def prompt(text: str, default: str = "", *, reader: Callable[[str], str] = input) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = reader(f"{text}{suffix}: ").strip()
    except EOFError:
        return default
    return answer or default


def ask_yes(text: str, default: bool = True, *,
            reader: Callable[[str], str] = input) -> bool:
    answer = prompt(text, "yes" if default else "no", reader=reader).lower()
    return answer.startswith("y")


def ask_int(text: str, default: int | None = None, *, minimum: int = 0,
            reader: Callable[[str], str] = input) -> int:
    while True:
        answer = prompt(text, "" if default is None else str(default), reader=reader)
        try:
            value = int(answer)
        except ValueError:
            print(f"  {answer!r} is not a whole number.")
            continue
        if value < minimum:
            print(f"  It needs to be at least {minimum}.")
            continue
        return value


def float_or_none(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        print(f"  {value!r} is not a number; ignoring it.")
        return None


# ===========================================================================
# Entering the communities
# ===========================================================================
def write_example_file(path: Path) -> Path:
    """Leave an example beside the output, so 'a CSV' means something concrete."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(EXAMPLE_CSV, encoding="utf-8")
    return path


def collect_one(index: int, *, reader: Callable[[str], str] = input,
                coder: str = "") -> dict[str, Any]:
    """One community, typed."""
    print(f"\n--- Community {index} " + "-" * 52)
    name = ""
    while not name:
        name = prompt("  Name", reader=reader)
        if not name:
            print("  A name is required.")

    latitude = float_or_none(prompt("  Latitude (optional)", reader=reader))
    longitude = float_or_none(prompt("  Longitude (optional)", reader=reader))
    if (latitude is None) != (longitude is None):
        print("  Only one coordinate was given; both are needed, so both are ignored.")
        print("  coordinate_agreement will be left blank rather than guessed.")
        latitude = longitude = None
    country = prompt("  Country (optional, improves local-language search)",
                     reader=reader) or None

    print("  URLs — one per line. Website, old domain, Facebook, YouTube, a")
    print("  directory listing, an academic page: paste them all. Empty line to finish.")
    urls: list[str] = []
    while True:
        line = prompt(f"    URL {len(urls) + 1}", reader=reader)
        if not line:
            break
        if line.strip().upper() == "NONE":
            urls = []
            break
        urls.append(line.strip())

    return {"name": name, "latitude": latitude, "longitude": longitude,
            "country": country, "urls": urls, "coder_id": coder, "mode": "FULL"}


def collect_communities(*, reader: Callable[[str], str] = input,
                        output_root: Path | None = None,
                        coder: str = "") -> list[dict[str, Any]]:
    """How many communities, and then their details (brief §6)."""
    from .session import read_community_file

    print("\nHow will you enter the communities?")
    print("  1. type them in            — fine for a handful")
    print("  2. read them from a file   — CSV or JSON, the usual way for a cohort")
    choice = prompt("\nChoice", "1", reader=reader).strip()

    if choice.startswith("2"):
        if output_root is not None:
            example = write_example_file(Path(output_root) / "example_communities.csv")
            print(f"\n  An example file has been written to:\n    {example}")
        while True:
            given = prompt("\n  Path to your community file", reader=reader)
            if not given:
                print("  No file given; falling back to typing them in.")
                break
            try:
                entries = read_community_file(Path(given).expanduser())
            except Exception as exc:
                print(f"  Could not read it: {exc}")
                continue
            if not entries:
                print("  That file has no communities in it (a `name` column is required).")
                continue
            for entry in entries:
                entry.setdefault("coder_id", coder)
                if coder and not entry.get("coder_id"):
                    entry["coder_id"] = coder
            print(f"\n  {len(entries)} communities read from {given}.")
            return entries

    count = ask_int("\nNumber of communities", 1, minimum=1, reader=reader)
    return [collect_one(index, reader=reader, coder=coder)
            for index in range(1, count + 1)]


# ===========================================================================
# The queue, and the decision to start
# ===========================================================================
def show_queue(plan: Any, *, limit: int = 25) -> None:
    print("\n" + "=" * 78)
    print("  THE QUEUE")
    print("=" * 78)
    print(plan.table(limit=limit))


def show_estimate(text: str) -> None:
    print("\n" + "=" * 78)
    print(text)
    print("=" * 78)


def confirm_start(*, reader: Callable[[str], str] = input) -> bool:
    print("\n  While it runs you can type, in another terminal:")
    print("    dcr pause          stop everything at the next safe boundary")
    print("    dcr resume         carry on")
    print("    dcr cancel         end the run, keeping everything already found")
    print("    dcr pause C007     pause one community and free its worker")
    print("    dcr status         where the run has got to")
    return ask_yes("\n  Start all of them now?", True, reader=reader)


# ===========================================================================
# Picking up an interrupted run
# ===========================================================================
def offer_resume(runs: Sequence[InterruptedRun], *,
                 reader: Callable[[str], str] = input) -> tuple[str, str] | None:
    """Offer to continue a run that did not finish. Returns (run_id, action).

    Actions: `resume`, `retry`, `export`, `reconcile`, `audit`, or None to start
    something new. A run the researcher deliberately paused is never restarted
    without being asked (brief §100).
    """
    if not runs:
        return None
    print("\n" + "=" * 78)
    print("  PREVIOUS RUN DETECTED")
    print("=" * 78)
    for index, run in enumerate(runs[:5], start=1):
        print(f"  {index}. {run.describe()}")
    print("-" * 78)
    print("  What would you like to do?")
    print("    1. RESUME ALL       continue where it stopped")
    print("    2. RETRY FAILED     resume, and try the failed communities again")
    print("    3. EXPORT           rebuild workbooks from stored evidence, no network")
    print("    4. RECONCILE        redo reconciliation from stored evidence, no network")
    print("    5. AUDIT            check evidence and workbooks offline")
    print("    6. NEW RUN          leave it untouched and start something else")
    choice = prompt("\n  Choice", "1", reader=reader).strip()
    actions = {"1": "resume", "2": "retry", "3": "export", "4": "reconcile",
               "5": "audit", "6": ""}
    action = actions.get(choice, "resume")
    if not action:
        return None
    return runs[0].run_id, action


def show_recovery_plan(plan: RecoveryPlan) -> None:
    print("\n  Resuming this run would:")
    print(plan.describe())


# ===========================================================================
# The end
# ===========================================================================
def show_summary(summary: Mapping[str, Any], output_root: Path) -> None:
    communities = summary.get("communities", {})
    evidence = summary.get("evidence", {})
    timing = summary.get("time", {})
    print("\n" + "=" * 78)
    print("  RUN COMPLETE")
    print("=" * 78)
    print(f"  {communities.get('completed', 0)} of {communities.get('total', 0)} "
          f"communities completed in "
          f"{format_duration(timing.get('wall_clock_s'))}")
    for status, count in sorted((communities.get("by_final_status") or {}).items()):
        print(f"    {count:>4}  {status}")
    print()
    print(f"  {evidence.get('sources', 0):,} sources, "
          f"{evidence.get('documents', 0):,} documents, "
          f"{evidence.get('images', 0):,} high-value images")
    print(f"  {evidence.get('evidence_items', 0):,} evidence items, "
          f"{evidence.get('claims', 0):,} claims, "
          f"{evidence.get('conflicts', 0):,} conflicts")
    print(f"  {evidence.get('workbooks_verified', 0)} workbooks written AND reopened")
    if timing.get("wall_clock_s") and timing.get("total_active_s"):
        speedup = timing["total_active_s"] / timing["wall_clock_s"]
        print(f"\n  Observed speed-up: {speedup:.1f}x "
              "(total active processing / wall-clock, measured)")
    print(f"\n  Outputs are in:\n    {output_root}")
    print("    one directory per community, each with its own workbook in 09_final/")
    print("    global_summary.md, community_status_table.csv, global_error_log.csv")
    if communities.get("failed"):
        print(f"\n  {communities['failed']} community(ies) FAILED — see "
              "global_error_log.csv. Retry them with:  dcr retry-failed")
    print("=" * 78)


__all__ = [
    "BANNER", "EXAMPLE_CSV", "ask_int", "ask_yes", "collect_communities",
    "collect_one", "confirm_start", "float_or_none", "offer_resume", "prompt",
    "show_estimate", "show_queue", "show_recovery_plan", "show_summary",
    "write_example_file",
]
