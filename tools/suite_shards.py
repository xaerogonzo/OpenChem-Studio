"""Split the test suite into N shards, so no single CI job carries all of it.

    python tools/suite_shards.py --splits 3 --group 1       # CI runs 3 shards; the count is the size of tests.yml's matrix
    python tools/suite_shards.py --update=s1.xml,s2.xml,s3.xml        # per-file reported test time AND each shard's price of a collect, from one run's JUnit, in shard order
    python tools/suite_shards.py --count-qapp                          # per-file Qt-test counts (the hook's input); collects, runs nothing
    python tools/suite_shards.py --repin --splits=3
    python tools/suite_shards.py --pin-new --splits=3   # pin files that have no pin, where they sit now
    python tools/suite_shards.py --splits=3 --group=1 --slice=0:28   # only files 0..27 of that shard

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

**IT MATTERED, AND THE HOOK IS NOW IN THE COST (2026-10-06): `load_costs`.** Two shards were balanced to 32 s
(1737 s and 1769 s of a 1800 s step) and both were full, so no re-pin could have helped; and the weights, which looked even
(1023 s against 1375 s of test time), were lopsided in the half they could not see: shard 1 carried 714 s of teardown hook against
shard 2's 394 s. A shard's wall time is its tests + the hook + ~30 s, to the second in both shards of both runs read
(1737 = 1023 + 684 + 30 and 1769 = 1375 + 361 + 33), where the hook is a full `gc.collect()` after every test that requests `qapp`
(`tests/conftest.py`, `pytest_runtest_logfinish`), outside the time a test reports. So `load_costs` weighs a file by its reported
time plus `HOOK_SECONDS` (0.40) for each such test, counted at collection time by `--count-qapp`: 2601 tests, and the two shards'
own `openchem_gc_calls` JUnit properties were 1433 and 1168, which sum to 2601. 0.40 s is a mean: a collect walks the live heap, so
it cost 0.477 s in shard 1 and 0.309 s in shard 2, and a shard of different files will differ again (the three-shard prediction
for 0.309 to 0.477 is 1050 s to 1290 s per shard against 1800 s). The weights (`suite-durations.json`) stay reported time only,
as `--update` reads them from JUnit; the hook is the second table, `suite-qapp-counts.json`, and `--repin`, `--pin-new` and
`--group` all weigh on the sum.

**AND THE PRICE OF A COLLECT IS PER SHARD, NOT A MEAN (2026-10-06, CI run 743 on the first three-shard master).** The three shards paid 0.474,
0.209 and 0.075 s per collect (1386, 1025 and 190 of them) and finished in 1258, 700 and 1037 s of tests + hook, where a flat 0.40 had put every
shard at 1146 s. The price is the heap a collect walks, and the heap is the `MainWindow`s the suite has built so far, held for the whole
process by `tests/conftest.py` (`_retained_windows`: 182, 58 and 0 at the end of the three shards; 0.075 s is what a process holding none
pays). So `suite-hook-rates.json` carries each shard's measured price, `--update` writes it from the shards' JUnit, and `assign`,
`shard_costs` and the balance guard all use it. It describes a LAYOUT: moving a Qt-free file changes nobody's price (it has no collect after
it and builds no window), so that is how the table was rebalanced (31 files, 289 s, all into shard 2); moving a Qt file moves windows and
collects with it and the measurement no longer applies. `--repin` starts over and deletes the prices for that reason.

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
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

REPO = Path(__file__).resolve().parent.parent

#: Weights, regenerated with `--update`. Absent entries are not an error.
DEFAULT_DURATIONS = REPO / "tools" / "suite-durations.json"

#: Which shard each file belongs to, per split count: `{"2": {"tests/test_x.py": 0, ...}}`. 0-based.
DEFAULT_PINS = REPO / "tools" / "suite-shard-pins.json"

#: How many tests in each file request the `qapp` fixture, regenerated with `--count-qapp`. Every one of those is followed by a full
#: `gc.collect()` in `tests/conftest.py` (`pytest_runtest_logfinish`), which runs OUTSIDE the time a test reports, so no JUnit-derived weight
#: can see it. See "THE HOOK IS HALF THE COST OF A QT FILE" in the module docstring.
DEFAULT_QAPP = REPO / "tools" / "suite-qapp-counts.json"
QAPP_PLUGIN = "suite_qapp_plugin"

#: The workflow that decides how many shards CI runs: the size of its `shard: [1, 2, 3]` matrix is the only place the number is written.
WORKFLOW = REPO / ".github" / "workflows" / "tests.yml"

#: Seconds one of those collects costs when NOTHING has measured it for this split count: the collect-weighted mean of the two shards of
#: CI run 725 (0.477 and 0.309). It is a fallback, not the model: a collect walks the LIVE heap, which is the `MainWindow`s the suite has built
#: so far (`_retained_windows`), so the three shards of run 743 paid 0.474, 0.209 and 0.075 s.
HOOK_SECONDS = 0.40

#: What one collect costs IN EACH SHARD of a split, `{"3": [0.474, 0.209, 0.075]}`, regenerated with `--update=<shard 1 xml>,<shard 2 xml>,...`
#: from the shards' `openchem_gc_collect_seconds / openchem_gc_calls`. It describes a LAYOUT: `--repin` deletes the entry for its split count.
DEFAULT_RATES = REPO / "tools" / "suite-hook-rates.json"


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


def load_qapp_counts(path: Path | None = None) -> dict[str, int]:
    path = path or DEFAULT_QAPP
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_costs(durations: dict[str, float] | None = None, counts: dict[str, int] | None = None) -> dict[str, float]:
    """What a file really costs a shard: its tests' reported time PLUS the collects that follow its Qt tests.

    In CI a shard's wall time is its tests' time + its hook + ~30 s of collection, to the second, in both shards of both runs read
    (1737 = 1023 + 684 + 30 and 1769 = 1375 + 361 + 33): so this is the quantity to balance, and balancing the first term alone is what
    left shard 1 carrying 714 s of hook against shard 2's 394 s while a weight-balanced split looked even.
    """
    durations = load_durations() if durations is None else durations
    counts = load_qapp_counts() if counts is None else counts
    return {name: durations.get(name, 0.0) + HOOK_SECONDS * counts.get(name, 0) for name in sorted(set(durations) | set(counts))}


def load_hook_rates(splits: int, path: Path | None = None) -> list[float] | None:
    """What one collect costs in each shard of a `splits`-way split, or None when nothing measured that layout (a rate list of the wrong
    length is the same as none: it was made for another count)."""
    path = path or DEFAULT_RATES
    if not path.is_file():
        return None
    rates = json.loads(path.read_text(encoding="utf-8")).get(str(splits))
    return [float(r) for r in rates] if isinstance(rates, list) and len(rates) == splits else None


def placement_model(splits: int) -> dict:
    """The arguments to `assign` that price a file the way CI will: reported time plus each shard's own price per collect where a run has
    measured them, else the flat `load_costs`. `assign(files, splits=n, pins=p, **placement_model(n))` is what `--group` runs."""
    rates = load_hook_rates(splits)
    if rates is None:
        return {"durations": load_costs()}
    return {"durations": load_durations(), "counts": load_qapp_counts(), "rates": rates}


def shard_costs(
    groups: list[list[str]],
    durations: dict[str, float] | None = None,
    counts: dict[str, int] | None = None,
    rates: list[float] | None = None,
) -> list[float]:
    """What each shard costs: its files' reported time plus a collect after every Qt test, at THAT shard's measured price when `rates`
    is given and at the flat `HOOK_SECONDS` when it is not. Add ~30 s of collection and it is the shard's wall time."""
    durations = load_durations() if durations is None else durations
    counts = load_qapp_counts() if counts is None else counts
    return [
        sum(durations.get(name, 0.0) + (rates[i] if rates else HOOK_SECONDS) * counts.get(name, 0) for name in group)
        for i, group in enumerate(groups)
    ]


def ci_splits(workflow: Path | None = None) -> int:
    """How many shards CI runs, read from the workflow's matrix: what `--splits` defaults to, so `--pin-new` and `--repin` act on the table CI
    uses instead of whichever count somebody remembered (a plain `--pin-new` pinned into the 2-way table after the suite went to three shards).
    Falls back to 2 only when the file or the matrix is not there."""
    path = workflow or WORKFLOW
    if not path.is_file():
        return 2
    match = re.search(r"^\s+shard:\s*\[([0-9,\s]+)\]\s*$", path.read_text(encoding="utf-8"), re.MULTILINE)
    return len([part for part in match.group(1).split(",") if part.strip()]) if match else 2


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
    counts: dict[str, int] | None = None,
    rates: list[float] | None = None,
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

    With `counts` and `rates` (one price per collect for each shard), `durations` is REPORTED time only and a file costs
    `durations + rates[shard] * counts` on the shard it lands on: a Qt file is cheaper in a shard whose heap is light, and the totals
    that pick the lighter shard are the ones CI will measure. Without them `durations` is already the cost (`load_costs`).
    """
    if splits < 1:
        raise ValueError("splits must be >= 1")
    known = [durations[f] for f in files if f in durations]
    fallback = statistics.median(known) if known else 1.0
    pins = pins or {}
    priced = rates is not None and len(rates) == splits
    counts = counts or {}

    def cost(name: str, shard: int) -> float:
        base = durations.get(name, fallback)
        return base + rates[shard] * counts.get(name, 0) if priced else base

    # the order files are placed in: biggest first, by what a file costs on average across the shards
    flat = {name: sum(cost(name, i) for i in range(splits)) / splits if priced else durations.get(name, fallback) for name in files}

    totals = [0.0] * splits
    groups: list[list[str]] = [[] for _ in range(splits)]
    free: list[str] = []
    for name in files:
        shard = pins.get(name)
        if isinstance(shard, int) and 0 <= shard < splits:
            totals[shard] += cost(name, shard)
            groups[shard].append(name)
        else:
            free.append(name)

    for name in sorted(free, key=lambda f: (-flat[f], f)):
        index = min(range(splits), key=lambda i: (totals[i] + cost(name, i) if priced else totals[i], i))
        totals[index] += cost(name, index)
        groups[index].append(name)
    return [sorted(group) for group in groups]


def pin_new(splits: int, out_path: Path | None = None) -> list[str]:
    """Pin every file that has no pin at the shard it is ALREADY in, so nobody moves. Returns the newly
    pinned files. An unpinned file is packed among the other unpinned files, so adding one more can move an
    earlier one; pinning them (with this, in the PR that adds the test file) makes the placement permanent."""
    files = test_files()
    table = load_pins(out_path)
    pins = table.get(str(splits), {})
    groups = assign(files, splits=splits, pins=pins, **placement_model(splits))
    placed = {name: i for i, group in enumerate(groups) for name in group}
    fresh = sorted(name for name in files if name not in pins)
    table[str(splits)] = {**pins, **{name: placed[name] for name in fresh}}
    (out_path or DEFAULT_PINS).write_text(json.dumps(table, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return fresh


def slice_files(files: list[str], spec: str) -> list[str]:
    """`files[a:b]` for a spec like `"0:28"`, `":28"` or `"10:"`: a window onto one shard's file list, in the
    order pytest will run it. Used by the crash-bisect workflow to run only the part of a shard where a crash
    happens. Bounds are Python's: out-of-range ends clamp, they do not raise, so a stale window shrinks
    rather than failing; an empty result is an error (a window that selects nothing must not "pass")."""
    head, sep, tail = spec.partition(":")
    if not sep:
        raise ValueError(f"slice must look like 'a:b', got {spec!r}")
    start = int(head) if head.strip() else None
    stop = int(tail) if tail.strip() else None
    window = files[start:stop]
    if not window:
        raise ValueError(f"slice {spec!r} selects none of the {len(files)} files")
    return window


def repin(splits: int, out_path: Path | None = None, rates_path: Path | None = None) -> int:
    """Re-pack EVERY file from the current weights and commit the result as the new pins. This is the one
    operation that moves files between shards; run it on its own, not alongside other changes.

    It packs on the FLAT hook price and DELETES the measured per-shard rates for this split count: a rate is what a collect cost in a shard
    that held certain files, so after a from-scratch pack no rate describes any shard. CI measures the new layout and `--update` writes
    the rates again; until then the balance guard uses the flat price too. Moving a few files by hand (the Qt-free ones change nobody's
    rate) keeps the measurement valid, which is why that is the usual way to rebalance."""
    groups = assign(test_files(), load_costs(), splits)
    table = load_pins(out_path)
    table[str(splits)] = {name: i for i, group in enumerate(groups) for name in group}
    (out_path or DEFAULT_PINS).write_text(json.dumps(table, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    rates_file = rates_path or DEFAULT_RATES
    if rates_file.is_file():
        rates = json.loads(rates_file.read_text(encoding="utf-8"))
        if rates.pop(str(splits), None) is not None:
            rates_file.write_text(json.dumps(rates, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return len(table[str(splits)])


def count_qapp(out_path: Path | None = None) -> int:
    """Collect the suite (nothing runs) and write how many tests per file request `qapp`: the criterion `pytest_runtest_logfinish`
    uses to decide who gets a `gc.collect()`. Measured against CI run 725, the counts summed to 2601, and the two shards' own
    `openchem_gc_calls` properties were 1433 and 1168: 2601."""
    out = out_path or DEFAULT_QAPP
    scratch = out.with_suffix(".collecting.json")
    env = {**os.environ, "SUITE_QAPP_OUT": str(scratch), "PYTHONPATH": str(REPO / "tools") + os.pathsep + os.environ.get("PYTHONPATH", ""),
           "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM", "offscreen")}
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q", "-p", QAPP_PLUGIN, "-p", "no:cacheprovider"],
        cwd=REPO, env=env, capture_output=True, text=True,
    )
    if run.returncode != 0 or not scratch.is_file():
        raise SystemExit(f"collection failed ({run.returncode}):\n{run.stdout[-1500:]}\n{run.stderr[-1500:]}")
    counts = json.loads(scratch.read_text(encoding="utf-8"))
    scratch.unlink()
    out.write_text(json.dumps({k: v for k, v in sorted(counts.items()) if v > 0}, indent=1) + "\n", encoding="utf-8")
    return sum(counts.values())


def update_from_junit(xml_paths: Path | list[Path], out_path: Path | None = None, rates_path: Path | None = None) -> int:
    """Regenerate the weight table from a completed run's JUnit XML: one file for an unsharded run, or ALL the shards' files IN SHARD
    ORDER, which also records what one collect cost in each (`openchem_gc_collect_seconds / openchem_gc_calls`, written under the number
    of files given). A shard with no collects at all has no price of its own and gets the run's mean."""
    paths = [xml_paths] if isinstance(xml_paths, Path) else list(xml_paths)
    totals: dict[str, float] = {}
    collects: list[tuple[float, int] | None] = []
    for xml_path in paths:
        root = ElementTree.parse(xml_path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        props = {p.get("name"): p.get("value") for suite in suites for p in suite.iter("property")}
        calls, seconds = props.get("openchem_gc_calls"), props.get("openchem_gc_collect_seconds")
        collects.append((float(seconds), int(float(calls))) if calls is not None and seconds is not None else None)
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
    if len(paths) > 1 and all(c is not None for c in collects):
        whole = sum(s for s, _ in collects) / max(sum(n for _, n in collects), 1)
        rates_file = rates_path or DEFAULT_RATES
        table = json.loads(rates_file.read_text(encoding="utf-8")) if rates_file.is_file() else {}
        table[str(len(paths))] = [round(s / n if n else whole, 3) for s, n in collects]
        rates_file.write_text(json.dumps(table, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return len(totals)


def main(argv: list[str]) -> int:
    splits, group, update, do_repin, do_pin_new, window, do_count = ci_splits(), None, None, False, False, None, False
    for arg in argv:
        if arg.startswith("--splits="):
            splits = int(arg.split("=", 1)[1])
        elif arg.startswith("--group="):
            group = int(arg.split("=", 1)[1])
        elif arg.startswith("--slice="):
            window = arg.split("=", 1)[1]
        elif arg == "--repin":
            do_repin = True
        elif arg == "--pin-new":
            do_pin_new = True
        elif arg == "--count-qapp":
            do_count = True
        elif arg.startswith("--update="):
            update = [Path(part) for part in arg.split("=", 1)[1].split(",") if part]
        else:
            print(__doc__)
            return 2

    if do_count:
        print(f"{count_qapp()} tests request qapp; per-file counts written to {DEFAULT_QAPP}")
        return 0

    if update is not None:
        count = update_from_junit(update)
        print(f"wrote {count} file weights to {DEFAULT_DURATIONS}")
        if len(update) > 1:
            print(f"hook rates for {len(update)} shards: {load_hook_rates(len(update))} (in {DEFAULT_RATES})")
        return 0

    if do_pin_new:
        fresh = pin_new(splits)
        print(f"pinned {len(fresh)} new file(s) where they already sit: {fresh}")
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
    shard = assign(test_files(), splits=splits, pins=pins, **placement_model(splits))[group - 1]
    for name in slice_files(shard, window) if window is not None else shard:
        print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
