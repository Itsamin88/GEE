"""Command-line entry point. ``RUN.py`` calls straight into this."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .app import Application, RUN_MODES, collect_input
from .config import load_settings
from .logging_setup import setup_logging
from .runner import CommunityInput


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dcr",
        description="Deep documentary research crawler for intentional sustainable communities.",
    )
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
    parser.add_argument("--root", type=Path, help="Project root (defaults to the repository).")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging()
    settings = load_settings(args.root) if args.root else load_settings()
    app = Application(settings)
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
            community, mode, target = collect_input()
            community.fixture = args.fixture
        app.run(community, mode=mode, target=target)
    except KeyboardInterrupt:
        print("\nInterrupted. Everything retrieved so far is saved; run again with "
              "mode RESUME to continue.")
        return 130
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
