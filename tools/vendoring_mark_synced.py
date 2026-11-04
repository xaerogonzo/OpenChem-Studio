"""Flip a VENDORING.md fork row from ``pending sync`` to ``synced`` after both PRs merge.

The naming-round workflow (VENDORING.md, "Recording a sync") should cite PR numbers in
the code PR with ``synced YYYY-MM-DD`` already in step 3, so nothing is left to edit
after merge. When a row was written as ``pending sync`` (NL-012 did), run this on
``master`` once the application and fork pull requests are merged — one commit on
master, not a second documentation PR.

    uv run python tools/vendoring_mark_synced.py --fork 94
    uv run python tools/vendoring_mark_synced.py --fork 94 --app-squash d9ce6e4b
    uv run python tools/vendoring_mark_synced.py --check

``--check`` exits 1 if any ``pending sync`` row remains (CI on master).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDORING = ROOT / "src" / "openchem" / "vendor" / "VENDORING.md"

PENDING = re.compile(
    r"(^\| fork pull request \| xaerogonzo/open-iupac-namer#(?P<num>\d+) — )pending sync",
    re.MULTILINE,
)


def mark_synced(
    text: str,
    *,
    fork: int | None,
    synced_on: date,
    app_squash: str | None,
) -> tuple[str, int]:
    """Return updated text and how many rows were changed."""
    changed = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        num = int(match.group("num"))
        if fork is not None and num != fork:
            return match.group(0)
        changed += 1
        prefix = match.group(1)
        return f"{prefix}synced {synced_on.isoformat()}"

    out = PENDING.sub(repl, text)
    if app_squash and changed and f"squash on master at `{app_squash}`" not in out:
        out = re.sub(
            rf"(open-iupac-namer#{fork} — synced {synced_on.isoformat()}, corresponding to this repository's pull request #\d+)( \()",
            rf"\1 (squash on master at `{app_squash}`\2",
            out,
            count=1,
        )
    return out, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fork", type=int, help="fork pull request number to mark synced")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=date.today(),
        help="sync date YYYY-MM-DD (default: today, local)",
    )
    parser.add_argument(
        "--app-squash",
        help="application squash commit on master to mention in the row (optional)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any pending sync row remains; write nothing",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write VENDORING.md (default when marking a fork)",
    )
    args = parser.parse_args()

    text = VENDORING.read_text(encoding="utf-8")
    if args.check:
        if PENDING.search(text):
            print("VENDORING.md still has a 'pending sync' fork row", file=sys.stderr)
            return 1
        return 0

    if args.fork is None:
        parser.error("--fork is required unless --check")

    new_text, n = mark_synced(
        text,
        fork=args.fork,
        synced_on=args.date,
        app_squash=args.app_squash,
    )
    if n == 0:
        print(f"no pending sync row for open-iupac-namer#{args.fork}", file=sys.stderr)
        return 1
    if args.write or not args.check:
        VENDORING.write_text(new_text, encoding="utf-8", newline="\n")
    print(f"marked {n} row(s) synced on {args.date.isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
