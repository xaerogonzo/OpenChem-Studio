"""Split the test suite into N shards, so no single CI job carries all of it.

    python tools/suite_shards.py --splits 2 --group 1
    python tools/suite_shards.py --update=suite-timings-windows.xml
    python tools/suite_shards.py --repin --splits=2

WHY THIS EXISTS. The Windows suite runs ~34 minutes against a 45-minute
job timeout -- 76% of budget -- and **the timeout is PER JOB**. Two shards
is roughly 17 minutes each. That buys headroom without touching a single
test, which matters because the other lever was measured and refused: the
per-test `gc.collect()` in `tests/conftest.py` is 30% of the wall clock,
and every cheaper collect policy either crashes the suite or costs more.
See docs/LESSONS.md, "A THIRD OF THE SUITE WAS IN NO TEST".

**THE ASSIGNMENT IS COMPUTED FROM THE FILES THAT EXIST, NEVER FROM A
COMMITTED LIST.** A list of files per shard rots the moment somebody adds
a test file, and it rots SILENTLY: the new file runs in no shard at all
and nothing goes red. So `suite-durations.json` is only a WEIGHT table.
The set being partitioned is always `tests/test_*.py` as it is on disk,
and a file the table has never heard of still gets a shard -- it is
weighted at the median, which cannot be right but can only cost balance.

**WEIGHTS ARE PER-TEST TIME ONLY, AND THAT IS A STATED APPROXIMATION.**
The suite's wall clock is ~1315 s: ~883 s of per-test time, which these
weights model, and ~410 s of teardown hook, which they do not. Qt-heavy
files therefore carry more real cost than their weight says. The worst
case is an IMBALANCED pair, never a wrong one -- if all 410 s landed in
one shard it would be ~14 minutes against ~7, both far inside the budget.
Every run publishes per-shard JUnit, so the real balance is measurable
rather than assumed; if it ever matters, attribute the hook per file in
`tests/conftest.py` and regenerate.

**A FILE KEEPS ITS SHARD WHEN ANOTHER FILE IS ADDED (`suite-shard-pins.json`).** Plain bin packing
re-sorts everything, so adding one test file moved about fifty others between shards and every PR
ran a combination of files master had never run: a green master said nothing about the PR's shard
(docs/LESSONS.md, "ADDING A TEST FILE RE-BALANCES THE SHARDS"). So each file's shard is PINNED in a
committed table, and only a file with no pin is packed -- onto whichever shard is lighter once the
pinned files are counted -- which moves no pinned file. The pin table is still only a PLACEMENT hint:
the set partitioned is read from disk, a pin for a deleted file is ignored, and a file with no pin
still runs. Balance drifts as unpinned files accumulate; `--repin` re-packs everything from the
current weights (that one commit moves files, deliberately, and should be its own PR).

**FILE GRANULARITY, NOT TEST GRANULARITY**, and that is load-bearing.
Tests in this suite depend on their neighbours within a file --
`test_that_deferred_delete_was_flushed_before_this_test_started` reads
state its predecessor left. Splitting inside a file would break those in
a way that looks like a real failure.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from xml.etree import ElementTree

REPO = Path(__file__).resolve().parent.parent

#: Weights, regenerated with `--update`. Absent entries are not an error.
DEFAULT_DURATIONS = REPO / "tools" / "suite-durations.json"

#: Which shard each file belongs to, per split count: `{"2": {"tests/test_x.py": 0, ...}}`. 0-based.
DEFAULT_PINS = REPO / "tools" / "suite-shard-pins.json"


def test_files(root: Path | None = None) -> list[str]:
    """Every test file pytest would collect, as repo-relative POSIX paths.

    `tests/vendor` is excluded by `norecursedirs` in pyproject.toml and
    has no `test_*.py` at the top level of `tests/` to confuse this;
    measured 2026-09-12, the glob and the suite's own JUnit agree at 328
    files, which is the check that this matches what pytest collects.
    """
    base = (root or REPO) / "tests"
    return sorted(p.relative_to(root or REPO).as_posix() for p in base.glob("test_*.py"))


def load_durations(path: Path | None = None) -> dict[str, float]:
    path = path or DEFAULT_DURATIONS
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_pins(path: Path | None = None) -> dict[str, dict[str, int]]:
    path = path or DEFAULT_PINS
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def assign(
    files: list[str],
    durations: dict[str, float],
    splits: int,
    pins: dict[str, int] | None = None,
) -> list[list[str]]:
    """Greedy longest-processing-time bin packing, deterministic.

    Ties break on the file NAME, not on dict order, so two machines
    running this on the same tree produce the same shards -- a split that
    differed between the `--group 1` and `--group 2` invocations would
    drop or duplicate files with nothing to notice.

    `pins` (file -> 0-based shard) fixes where a file goes: pinned files are placed first, exactly
    where the table says, and only the REST are packed, onto the lighter shards. A pin outside
    `0..splits-1` is ignored (the table was made for another split count), so it can cost balance and
    never drop a file.
    """
    if splits < 1:
        raise ValueError("splits must be >= 1")
    known = [durations[f] for f in files if f in durations]
    fallback = statistics.median(known) if known else 1.0
    pins = pins or {}

    totals = [0.0] * splits
    groups: list[list[str]] = [[] for _ in range(splits)]
    free: list[str] = []
    for name in files:
        shard = pins.get(name)
        if isinstance(shard, int) and 0 <= shard < splits:
            totals[shard] += durations.get(name, fallback)
            groups[shard].append(name)
        else:
            free.append(name)

    for name in sorted(free, key=lambda f: (-durations.get(f, fallback), f)):
        index = min(range(splits), key=lambda i: (totals[i], i))
        totals[index] += durations.get(name, fallback)
        groups[index].append(name)
    return [sorted(group) for group in groups]


def repin(splits: int, out_path: Path | None = None) -> int:
    """Re-pack EVERY file from the current weights and commit the result as the new pins. This is the one
    operation that moves files between shards; run it on its own, not alongside other changes."""
    groups = assign(test_files(), load_durations(), splits)
    table = load_pins(out_path)
    table[str(splits)] = {name: i for i, group in enumerate(groups) for name in group}
    (out_path or DEFAULT_PINS).write_text(json.dumps(table, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return len(table[str(splits)])


def update_from_junit(xml_path: Path, out_path: Path | None = None) -> int:
    """Regenerate the weight table from a completed run's JUnit XML."""
    root = ElementTree.parse(xml_path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    totals: dict[str, float] = {}
    for suite in suites:
        for case in suite.iter("testcase"):
            parts = [p for p in (case.get("classname") or "").split(".") if p]
            if len(parts) < 2:
                continue
            name = f"tests/{parts[1]}.py"
            totals[name] = totals.get(name, 0.0) + float(case.get("time", 0.0) or 0.0)
    out = out_path or DEFAULT_DURATIONS
    out.write_text(
        json.dumps({k: round(v, 3) for k, v in sorted(totals.items())}, indent=1) + "\n",
        encoding="utf-8",
    )
    return len(totals)


def main(argv: list[str]) -> int:
    splits, group, update, do_repin = 2, None, None, False
    for arg in argv:
        if arg.startswith("--splits="):
            splits = int(arg.split("=", 1)[1])
        elif arg.startswith("--group="):
            group = int(arg.split("=", 1)[1])
        elif arg == "--repin":
            do_repin = True
        elif arg.startswith("--update="):
            update = Path(arg.split("=", 1)[1])
        else:
            print(__doc__)
            return 2

    if update is not None:
        count = update_from_junit(update)
        print(f"wrote {count} file weights to {DEFAULT_DURATIONS}")
        return 0

    if do_repin:
        print(f"pinned {repin(splits)} files across {splits} shards in {DEFAULT_PINS}")
        return 0

    if group is None:
        print(__doc__)
        return 2
    if not 1 <= group <= splits:
        print(f"--group must be between 1 and {splits}")
        return 2

    pins = load_pins().get(str(splits), {})
    for name in assign(test_files(), load_durations(), splits, pins)[group - 1]:
        print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
