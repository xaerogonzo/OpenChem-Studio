"""VENDORING.md fork-row maintenance after a naming-round port.

Preferred workflow (VENDORING.md, "Recording a sync"): add the row in the application
PR with ``synced YYYY-MM-DD`` before merge. When that step was skipped, use
``--append-row`` after both PRs merge. When a row was written ``pending sync``, use
``--fork N --write`` to flip it.

    uv run python tools/vendoring_mark_synced.py --fork 94 --app-squash d9ce6e4b --write
    uv run python tools/vendoring_mark_synced.py --append-row --fork 95 --app 548 ...
    uv run python tools/vendoring_mark_synced.py --check
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDORING = ROOT / "src" / "openchem" / "vendor" / "VENDORING.md"

PENDING = re.compile(
    r"(^\| fork pull request \| xaerogonzo/open-iupac-namer#(?P<num>\d+) — )pending sync",
    re.MULTILINE,
)
FORK_ROW = re.compile(
    r"^\| fork pull request \| xaerogonzo/open-iupac-namer#(?P<num>\d+)",
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


def format_sync_row(
    *,
    fork: int,
    app: int,
    synced_on: date,
    branch: str,
    base: str,
    app_squash: str,
    naming_round: int,
    context: str,
    prose: str,
) -> str:
    """One ``| fork pull request |`` line matching VENDORING.md's template."""
    ctx = f", {context}" if context else ""
    head = (
        f"| fork pull request | xaerogonzo/open-iupac-namer#{fork} — synced {synced_on.isoformat()}, "
        f"corresponding to this repository's pull request #{app} "
        f"(`{branch}`, squash on master at `{app_squash}`, base `{base}`{ctx}): "
        f"naming round {naming_round}, {prose.strip()} |"
    )
    return head


def append_sync_row(
    text: str,
    row: str,
    *,
    insert_after_fork: int | None,
) -> tuple[str, int]:
    """Insert ``row`` after the fork pull request with ``insert_after_fork``, or append."""
    fork_m = re.search(r"open-iupac-namer#(\d+)", row)
    if fork_m and f"open-iupac-namer#{fork_m.group(1)}" in text:
        return text, 0

    anchor = insert_after_fork
    if anchor is not None:
        needle = f"| fork pull request | xaerogonzo/open-iupac-namer#{anchor} —"
        idx = text.find(needle)
        if idx != -1:
            line_end = text.find("\n", idx)
            if line_end == -1:
                line_end = len(text)
            return text[: line_end + 1] + row + "\n" + text[line_end + 1 :], 1

    # Fallback: after the highest-numbered existing fork pull request row.
    last_end = -1
    for m in FORK_ROW.finditer(text):
        last_end = m.end()
    if last_end != -1:
        line_end = text.find("\n", last_end)
        if line_end == -1:
            line_end = len(text)
        return text[: line_end + 1] + row + "\n" + text[line_end + 1 :], 1

    return text + "\n" + row + "\n", 1


def _gh_json(repo: str, pr: int) -> dict:
    out = subprocess.check_output(
        ["gh", "pr", "view", str(pr), "--repo", repo, "--json", "headRefName,mergeCommit,baseRefOid"],
        text=True,
    )
    return json.loads(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fork", type=int, help="fork pull request number")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=date.today(),
        help="sync date YYYY-MM-DD (default: today, local)",
    )
    parser.add_argument(
        "--app-squash",
        help="application squash commit on master (short sha ok)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any pending sync row remains; write nothing",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write VENDORING.md",
    )
    parser.add_argument(
        "--append-row",
        action="store_true",
        help="insert a synced row (when step 3 of Recording a sync was skipped)",
    )
    parser.add_argument("--app", type=int, help="application pull request number")
    parser.add_argument("--branch", help="application PR head branch name")
    parser.add_argument("--base", help="application commit the fork held (--fork_port --base)")
    parser.add_argument("--naming-round", type=int, help="naming round number in the row prose")
    parser.add_argument(
        "--context",
        default="",
        help="short tag after base sha, e.g. 'NL-011 bucket A after fork #94'",
    )
    parser.add_argument(
        "--prose",
        help="remainder of the row after 'naming round N,' (one line)",
    )
    parser.add_argument(
        "--prose-file",
        type=Path,
        help="file containing the prose line",
    )
    parser.add_argument(
        "--insert-after-fork",
        type=int,
        help="place the new row immediately after this fork PR row (default: fork-1)",
    )
    parser.add_argument(
        "--from-gh",
        action="store_true",
        help="with --append-row, fill branch/base/app-squash from gh (app repo + --app)",
    )
    args = parser.parse_args()

    text = VENDORING.read_text(encoding="utf-8")
    if args.check:
        if PENDING.search(text):
            print("VENDORING.md still has a 'pending sync' fork row", file=sys.stderr)
            return 1
        return 0

    if args.append_row:
        if args.fork is None or args.app is None or args.naming_round is None:
            parser.error("--append-row requires --fork, --app, and --naming-round")
        prose = args.prose
        if args.prose_file:
            prose = args.prose_file.read_text(encoding="utf-8").strip()
        if not prose:
            parser.error("--prose or --prose-file is required with --append-row")

        branch = args.branch or ""
        base = args.base or ""
        app_squash = (args.app_squash or "")[:7]
        if args.from_gh:
            data = _gh_json("xaerogonzo/OpenChem-Studio", args.app)
            branch = branch or data.get("headRefName") or ""
            base = base or (data.get("baseRefOid") or "")[:7]
            mc = data.get("mergeCommit") or {}
            app_squash = app_squash or (mc.get("oid") or "")[:7]
        if not branch or not base or not app_squash:
            parser.error("--branch, --base, and --app-squash required (or use --from-gh with --app)")

        row = format_sync_row(
            fork=args.fork,
            app=args.app,
            synced_on=args.date,
            branch=branch,
            base=base,
            app_squash=app_squash,
            naming_round=args.naming_round,
            context=args.context,
            prose=prose,
        )
        insert_after = args.insert_after_fork if args.insert_after_fork is not None else args.fork - 1
        new_text, n = append_sync_row(text, row, insert_after_fork=insert_after)
        if n == 0:
            print(f"row for open-iupac-namer#{args.fork} already present", file=sys.stderr)
            return 0
        if args.write:
            VENDORING.write_text(new_text, encoding="utf-8", newline="\n")
        print(f"appended sync row for fork #{args.fork} / app #{args.app}")
        return 0

    if args.fork is None:
        parser.error("--fork is required unless --check or --append-row")

    new_text, n = mark_synced(
        text,
        fork=args.fork,
        synced_on=args.date,
        app_squash=args.app_squash,
    )
    if n == 0:
        print(f"no pending sync row for open-iupac-namer#{args.fork}", file=sys.stderr)
        return 1
    if args.write:
        VENDORING.write_text(new_text, encoding="utf-8", newline="\n")
    print(f"marked {n} row(s) synced on {args.date.isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
