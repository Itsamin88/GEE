#!/usr/bin/env python3
"""Run the two pilot communities against the local fixture web.

These are SOFTWARE TEST CASES ONLY. Every run is stamped provenance_mode=FIXTURE
and its site_id is prefixed TEST-, so fixture output can never be mistaken for
coded research data (decision DCR-D022).

    python3 tools/run_pilot.py [--output pilot_output] [--keep]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

FIXTURE_HOSTS = (
    "pourgues.test", "ancien-pourgues.test", "annuaire.test",
    "theses.test", "facebook.test", "archive.test",
    "boekel.test", "oud-boekel.test",
)


def ensure_hosts() -> bool:
    """Point the fixture hostnames at loopback.

    The fixture serves several distinct hosts so the crawler's scope,
    independence and archive logic are exercised for real. That needs the names
    to resolve; on most developer machines and CI images this file is writable.
    """
    import socket

    missing = []
    for host in FIXTURE_HOSTS:
        try:
            socket.gethostbyname(host)
        except OSError:
            missing.append(host)
    if not missing:
        return True
    hosts_file = Path("/etc/hosts")
    line = "127.0.0.1 " + " ".join(FIXTURE_HOSTS)
    try:
        existing = hosts_file.read_text(encoding="utf-8")
        if "pourgues.test" not in existing:
            with hosts_file.open("a", encoding="utf-8") as handle:
                handle.write(f"\n# Documentary crawler test fixture\n{line}\n")
        return True
    except OSError:
        print("The pilot fixture needs these names to resolve to 127.0.0.1:")
        print("   " + line)
        print("Add that line to your hosts file and run the pilot again.")
        return False


from dcr.app import Application                     # noqa: E402
from dcr.runner import CommunityInput, CommunityRunner   # noqa: E402
from fixtures.harness import fixture_settings, fixture_urls   # noqa: E402
from fixtures.server import FixtureServer           # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="pilot_output")
    parser.add_argument("--keep", action="store_true",
                        help="keep any existing output instead of starting clean")
    parser.add_argument("--only", choices=["pourgues", "boekel"], help="run one pilot only")
    args = parser.parse_args()

    output = (ROOT / args.output).resolve()
    if output.exists() and not args.keep:
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    if not ensure_hosts():
        return 2

    server = FixtureServer().start()
    print(f"fixture web serving on 127.0.0.1:{server.port}")
    try:
        settings = fixture_settings(server.port, output, root=ROOT)
        app = Application(settings)
        app.preflight()

        pilots = [
            ("pourgues", CommunityInput(
                name="EcoVillage de Pourgues",
                latitude=43.0561, longitude=1.8342,
                urls=fixture_urls(server.port, "pourgues"),
                country="France", coder_id="PILOT", fixture=True)),
            ("boekel", CommunityInput(
                name="Boekel Ecovillage",
                latitude=51.5990, longitude=5.6720,
                urls=fixture_urls(server.port, "boekel"),
                country="Netherlands", coder_id="PILOT", fixture=True)),
        ]
        results = []
        for key, community in pilots:
            if args.only and key != args.only:
                continue
            print(f"\n{'=' * 78}\n  PILOT: {community.name}\n{'=' * 78}")
            # The estimate the researcher would see before pressing go.
            estimate = app.estimate_workload(community, mode="FULL")
            results.append(app.run(community, mode="FULL"))
            if estimate is not None:
                print(f"  estimate was {estimate.active_band} active; "
                      "the actual is recorded in run_history for the next run")

        # Prove resumability and offline regeneration on the first pilot.
        if not args.only or args.only == "pourgues":
            print(f"\n{'=' * 78}\n  PILOT: EXPORT re-run (offline, from the database)\n{'=' * 78}")
            app.run(pilots[0][1], mode="EXPORT")

        app.close()

        # -- the interruption scenarios ------------------------------------
        # A pilot that only ever runs to completion proves nothing about what
        # happens when it does not. These run the same community from scratch
        # in a workspace of their own — so there is real work to interrupt —
        # and then finish it. The research meaning of the pilots above is
        # untouched: this is a separate database, and its output is clearly
        # labelled as an interruption rehearsal.
        scenarios = output / "interruption_scenarios"
        _pilot_manual_pause(settings, pilots[0][1], scenarios / "manual_pause")
        _pilot_network_outage(settings, pilots[0][1], scenarios / "network_outage", server)
        print(f"\nAll pilot output is under {output}")
        failures = [r for r in results if r["status"] == "FAILED_TECHNICALLY"]
        return 1 if failures else 0
    finally:
        server.stop()


def _pilot_manual_pause(settings: Any, community: CommunityInput, output: Path) -> None:
    """Press PAUSE mid-crawl, close the application, then resume it."""
    from dcr.control import clear_requests, find_interrupted_runs, request_pause
    from dcr.db import Database
    import dcr.app as app_module

    print(f"\n{'=' * 78}\n  PILOT: manual pause and resume\n{'=' * 78}")
    paused_settings = _control_settings(settings, output=output,
                                        manual_pause_behavior="exit")
    clear_requests(paused_settings.output_root)

    class PausingRunner(CommunityRunner):
        def _on_page(self, page_id, parsed, context):
            found = super()._on_page(page_id, parsed, context)
            self._seen = getattr(self, "_seen", 0) + 1
            if self._seen == 2:
                request_pause(self.settings.output_root, "pilot: researcher pressed PAUSE")
            return found

    app = Application(paused_settings)
    app.preflight()
    original = app_module.CommunityRunner
    app_module.CommunityRunner = PausingRunner
    try:
        app.run(community, mode="FULL")
    finally:
        app_module.CommunityRunner = original
    db = Database(paused_settings.database_path)
    unfinished = find_interrupted_runs(db)
    db.close()
    app.close()
    print(f"  paused: {unfinished[0].describe() if unfinished else 'NO PAUSED RUN FOUND'}")

    clear_requests(paused_settings.output_root)
    print("  resuming, as the researcher would the next morning...")
    resumed = Application(_control_settings(settings, output=output))
    resumed.preflight()
    result = resumed.run(community, mode="RESUME")
    resumed.close()
    print(f"  resumed and finished as {result['report']['final_state']}")


def _pilot_network_outage(settings: Any, community: CommunityInput, output: Path,
                          server: Any) -> None:
    """Pull the plug on the network mid-crawl, then put it back."""
    from dcr.control import clear_requests
    from dcr.net.connectivity import ConnectivityMonitor
    import dcr.app as app_module

    print(f"\n{'=' * 78}\n  PILOT: internet loss and automatic resume\n{'=' * 78}")

    offline_checks = {"n": 0}

    async def prober(_url: str) -> bool:
        # Offline for the first few checks, then the connection comes back and
        # the fixture web with it.
        offline_checks["n"] += 1
        if offline_checks["n"] > 6:
            if not getattr(server, "_server", None):
                server.start()
            return True
        return False

    outage_settings = _control_settings(settings, output=output,
                                        offline_wait_interval_s=0.2,
                                        failures_before_probe=2)
    clear_requests(outage_settings.output_root)
    monitor = ConnectivityMonitor(probes=("https://a.example/", "https://b.example/"),
                                  prober=prober, check_interval_s=0.0,
                                  offline_retry_s=0.2, offline_retry_max_s=0.5)

    class CuttingRunner(CommunityRunner):
        def _on_page(self, page_id, parsed, context):
            found = super()._on_page(page_id, parsed, context)
            self._seen = getattr(self, "_seen", 0) + 1
            if self._seen == 2:
                print("  ...the network goes away")
                server.stop()
            return found

    app = Application(outage_settings, monitor=monitor)
    app.preflight()
    original = app_module.CommunityRunner
    app_module.CommunityRunner = CuttingRunner
    try:
        result = app.run(community, mode="FULL")
    finally:
        app_module.CommunityRunner = original
    app.close()
    interruptions = result["report"]["interruptions"]
    print(f"  finished as {result['report']['final_state']} after "
          f"{interruptions['pauses_network']} network pause(s), "
          f"{interruptions['connectivity_losses']} connectivity loss(es)")
    if not getattr(server, "_server", None):
        server.start()


def _control_settings(settings: Any, *, output: Path | None = None,
                      **run_control: Any) -> Any:
    """A copy of the pilot settings with run control tuned for a short demo."""
    import copy

    clone = copy.copy(settings)
    clone.app = copy.deepcopy(settings.app)
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        clone.app["paths"]["output_root"] = str(output)
        clone.app["paths"]["database"] = str(output / "dcr.sqlite3")
    clone.app["run_control"] = {
        "poll_interval_s": 0.0,
        "manual_pause_behavior": "wait",
        "resume_poll_interval_s": 0.2,
        "failures_before_probe": 2,
        "max_offline_wait_s": 30,
        **run_control,
    }
    clone.app["estimation"] = {"enabled": False}
    clone.app["retry"]["max_attempts"] = 1
    clone.app["retry"]["backoff_base_s"] = 0.05
    clone.app["network"]["timeout_connect_s"] = 2
    clone.app["network"]["timeout_read_s"] = 2
    return clone


if __name__ == "__main__":
    raise SystemExit(main())
