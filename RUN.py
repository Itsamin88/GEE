#!/usr/bin/env python3
"""PRESS RUN.

Open this project in PyCharm, right-click this file and choose Run, or press
the green ▶ button. The program will ask for the community name, optionally its
coordinates, and any URLs you already have — then do the rest itself.

Nothing else needs configuring. If an optional feature is missing (a browser, an
OCR engine, an API key) the program says so at startup and carries on without it.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `src/` importable without installing the package, so RUN works from a
# fresh checkout with nothing but `pip install -r requirements.txt`.
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> int:
    try:
        from dcr.cli import main as cli_main
    except ImportError as exc:                       # pragma: no cover
        print("A required package is missing:", exc)
        print("\nIn PyCharm's terminal, run:")
        print("    pip install -r requirements.txt")
        return 1
    return cli_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
