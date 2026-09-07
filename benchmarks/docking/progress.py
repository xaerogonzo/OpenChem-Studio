"""Where is the ranking run up to? Read-only, safe to run at any time.

    uv run --no-sync python benchmarks/docking/progress.py
    uv run --no-sync python benchmarks/docking/progress.py --watch

**IT PRINTS COMPLETION AND NEVER A RHO, WHICH IS THE WHOLE DESIGN.** This
benchmark's own p-value crossed 0.05 and came back when it was looked at
three times mid-run, and `README.md` records the rule that came out of it:
*when a run's own statistic is what says whether it is going well, report the
completion count and refuse the statistic.* A progress tool that printed the
answer would make "how is it going" and "what is the result" the same
question, which is exactly how that happened. So this reads how many searches
are DONE and nothing about what they found -- no affinity, no ordering, no
correlation.

**AND IT ANSWERS "IS IT ALIVE" SEPARATELY FROM "HOW FAR ALONG",** because
those are different questions and conflating them is how a dead run gets
reported as a slow one. A stalled run and a working one look identical in a
completion count; only the mtime of the newest write tells them apart.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"
RESULTS = HERE / "results"

#: Past this with no write, a run is reported as STALLED rather than slow.
#: The slowest single search observed on this corpus is a few minutes on a
#: highly flexible ligand, so ten minutes is comfortably past any real search
#: and far short of a whole series.
STALL_AFTER_S = 600.0


def _selection() -> list[str]:
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    return list(manifest.get("docking_selection", []))


def _expected(series_id: str) -> int:
    """Ligands in this series, from the corpus rather than from the results.

    Reading it from the RESULT file would make a half-written series look
    complete -- the denominator would shrink with the numerator.
    """
    path = DATA / "series" / f"{series_id}.json"
    if not path.is_file():
        return 0
    return len(json.loads(path.read_text(encoding="utf-8")).get("ligands", []))


def _done(series_id: str) -> tuple[int, float]:
    """Distinct (molecule, replicate) pairs on disk, and the file's mtime.

    **PAIRS, NOT LINES.** A resumed run appends, so counting lines would
    double-count anything written twice, and the resume logic itself keys on
    the pair -- so this counts what that logic counts.
    """
    path = RESULTS / f"{series_id}.jsonl"
    if not path.is_file():
        return 0, 0.0
    pairs = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue  # a torn last line is a run mid-write, not a fault
        pairs.add((row.get("molecule_chembl_id"), row.get("replicate")))
    return len(pairs), path.stat().st_mtime


def report(replicates: int = 6) -> int:
    selection = _selection()
    if not selection:
        print("no frozen selection in the manifest -- has the corpus been built?")
        return 1

    complete = partial = untouched = 0
    searches_done = searches_total = 0
    newest = 0.0
    newest_series = ""
    in_flight: list[str] = []

    for series_id in selection:
        want = _expected(series_id) * replicates
        have, mtime = _done(series_id)
        searches_total += want
        searches_done += min(have, want)
        if mtime > newest:
            newest, newest_series = mtime, series_id
        if want and have >= want:
            complete += 1
        elif have:
            partial += 1
            in_flight.append(f"{series_id} {have}/{want}")
        else:
            untouched += 1

    pct = 100.0 * searches_done / searches_total if searches_total else 0.0
    print(f"series    {complete} complete, {partial} partial, {untouched} not started"
          f"   ({len(selection)} in the frozen selection)")
    print(f"searches  {searches_done} of {searches_total}   ({pct:.1f}%)")
    for line in in_flight:
        print(f"          in flight: {line}")

    if not newest:
        print("liveness  NOTHING WRITTEN YET")
        return 0

    idle = time.time() - newest
    stamp = time.strftime("%H:%M:%S", time.localtime(newest))
    if idle > STALL_AFTER_S:
        print(f"liveness  ** STALLED ** last write {stamp}, {idle/60:.0f} min ago "
              f"({newest_series})")
        print("          a run this idle is not slow, it is gone -- check for a "
              "live process before believing a completion count")
        return 2
    print(f"liveness  running -- last write {stamp}, {idle:.0f}s ago ({newest_series})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replicates", type=int, default=6)
    parser.add_argument("--watch", action="store_true",
                        help="reprint every 60 s until interrupted")
    args = parser.parse_args()
    if not args.watch:
        return report(args.replicates)
    while True:
        print(f"\n=== {time.strftime('%H:%M:%S')} ===")
        report(args.replicates)
        time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())
