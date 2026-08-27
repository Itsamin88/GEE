"""Point the fixture hostnames at loopback, shared by the pilot and the benchmark.

The fixture web serves several distinct hosts on purpose: the crawler's scope
rules, its per-host politeness and its independence grouping all key on the
host, and a fixture served entirely from `localhost` would exercise none of
them. That means the names have to resolve, which on most machines means one
line in the hosts file.
"""

from __future__ import annotations

import socket
from pathlib import Path

FIXTURE_HOSTS = (
    "pourgues.test", "ancien-pourgues.test", "annuaire.test",
    "theses.test", "facebook.test", "archive.test",
    "boekel.test", "oud-boekel.test",
    # The Tamera-shaped stress case.
    "stress.test",
)


def hosts_resolve() -> bool:
    try:
        for host in FIXTURE_HOSTS:
            socket.gethostbyname(host)
        return True
    except OSError:
        return False


def ensure_hosts(*, quiet: bool = False) -> bool:
    """True when every fixture name resolves; tries to add them if it may."""
    if hosts_resolve():
        return True
    hosts_file = Path("/etc/hosts") if Path("/etc/hosts").exists() else Path(
        r"C:\Windows\System32\drivers\etc\hosts")
    line = "127.0.0.1 " + " ".join(FIXTURE_HOSTS)
    try:
        existing = hosts_file.read_text(encoding="utf-8")
        if line not in existing:
            with hosts_file.open("a", encoding="utf-8") as handle:
                handle.write("\n" + line + "\n")
    except OSError:
        pass
    if hosts_resolve():
        return True
    if not quiet:
        print("The fixture web needs these names to resolve to 127.0.0.1:")
        print("   " + line)
        print(f"Add that line to {hosts_file} and run this again.")
    return False
