"""Print the pytest arguments for a scope of the naming-consumer manifest.

    python tools/naming_consumers.py --scope core,benchmark          # files, one per line
    python tools/naming_consumers.py --scope core,benchmark --args   # one line, ready for `python -m pytest`

The manifest is `tests/naming_consumers.toml`. A stage's routine runs `core` and `benchmark` after every
change and all four scopes at a milestone, so "the whole naming-consuming test set" is a list a stage can be
checked against and not a phrase.
"""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tests" / "naming_consumers.toml"
SCOPES = ("core", "benchmark", "app", "vendor")


def consumers() -> list[dict]:
    return tomllib.loads(MANIFEST.read_text(encoding="utf-8"))["consumer"]


def select(scopes: set[str]) -> list[str]:
    unknown = scopes - set(SCOPES)
    if unknown:
        raise SystemExit(f"unknown scope(s) {sorted(unknown)}; the scopes are {list(SCOPES)}")
    return [c["file"] for c in consumers() if c["scope"] in scopes]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scope", default=",".join(SCOPES), help="comma-separated scopes (default: all)")
    parser.add_argument("--args", action="store_true", help="print one space-separated line")
    args = parser.parse_args()
    files = select({s.strip() for s in args.scope.split(",") if s.strip()})
    print(" ".join(files) if args.args else "\n".join(files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
