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
from dcr.runner import CommunityInput               # noqa: E402
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
            results.append(app.run(community, mode="FULL"))

        # Prove resumability and offline regeneration on the first pilot.
        if not args.only or args.only == "pourgues":
            print(f"\n{'=' * 78}\n  PILOT: EXPORT re-run (offline, from the database)\n{'=' * 78}")
            app.run(pilots[0][1], mode="EXPORT")

        app.close()
        print(f"\nAll pilot output is under {output}")
        failures = [r for r in results if r["status"] == "FAILED_TECHNICALLY"]
        return 1 if failures else 0
    finally:
        server.stop()


if __name__ == "__main__":
    raise SystemExit(main())
