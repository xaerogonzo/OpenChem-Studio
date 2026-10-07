"""Guards for the CI shard splitter.

**THE FAILURE THIS FILE EXISTS FOR IS SILENT.** If the splitter ever
drops a test file -- an off-by-one in the bin packing, a glob that stops
matching, a stale committed list -- that file runs in NO shard, every job
stays green, and the coverage is gone with nothing to notice. Every other
property here is secondary to the partition being exact.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "tests.yml"
CRASH_RATE_WORKFLOW = REPO / ".github" / "workflows" / "windows-crash-rate.yml"
SHARD_SCRIPT = REPO / "tools" / "ci_suite_shard.ps1"


def _ci_splits() -> int:
    """How many shards CI runs: the size of the Windows suite job's matrix, which is the ONLY place the number is written
    (`tests.yml` hands it to the script as `strategy.job-total`)."""
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"^\s+shard:\s*\[([0-9,\s]+)\]\s*$", text, re.MULTILINE)
    assert match, "tests.yml no longer has a `shard: [1, 2, ...]` matrix"
    shards = [int(part) for part in match.group(1).split(",")]
    assert shards == list(range(1, len(shards) + 1)), f"the matrix {shards} is not 1..N"
    return len(shards)


def _module():
    """The tool, loaded by path -- `tools/` is not a package.

    Registered in `sys.modules` before execution for the reason
    `tests/test_suite_timings.py` documents at length: a module that
    defines a dataclass without being registered raises out of
    `dataclasses._process_class` instead of anywhere useful.
    """
    if "_suite_shards" in sys.modules:
        return sys.modules["_suite_shards"]
    spec = importlib.util.spec_from_file_location(
        "_suite_shards", REPO / "tools" / "suite_shards.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_suite_shards"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("splits", [1, 2, 3, 5])
def test_every_test_file_lands_in_exactly_one_shard(splits):
    """The partition is exact: no file dropped, none run twice.

    Dropped is the dangerous half -- it removes coverage while every job
    stays green. Duplicated only wastes time, but it is the same
    arithmetic error pointing the other way, so both are asserted.
    """
    module = _module()
    files = module.test_files()
    groups = module.assign(files, module.load_durations(), splits)

    flat = [name for group in groups for name in group]
    assert sorted(flat) == sorted(files), "a file was dropped or duplicated"
    assert len(flat) == len(set(flat)), "a file appears in more than one shard"
    assert len(groups) == splits


def test_the_glob_agrees_with_what_git_tracks():
    """Cross-check the file set against an INDEPENDENT view of it.

    Every other guard here partitions whatever `test_files()` returns, so
    all of them would still pass if that function silently stopped seeing
    half the suite. Git's index is the one cheap second opinion available.
    """
    module = _module()
    tracked = subprocess.run(
        ["git", "ls-files", "tests/test_*.py"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.split()

    assert sorted(module.test_files()) == sorted(tracked)


def test_a_file_the_weight_table_has_never_heard_of_is_still_assigned():
    """A NEW test file must run, even before anyone regenerates weights.

    This is the rot that a committed per-shard file list would have, and
    the reason the set being partitioned is read from disk rather than
    from `suite-durations.json`. The weights may be stale; the file list
    may not be.
    """
    module = _module()
    files = module.test_files() + ["tests/test_a_brand_new_file.py"]
    groups = module.assign(files, module.load_durations(), 2)

    flat = [name for group in groups for name in group]
    assert "tests/test_a_brand_new_file.py" in flat
    assert sorted(flat) == sorted(files)


def test_an_empty_weight_table_still_partitions_everything():
    """No weights at all is imbalance, not breakage.

    `suite-durations.json` is regenerated from a CI artifact and could be
    absent in a fresh checkout or a fork. That must cost balance, never
    coverage.
    """
    module = _module()
    files = module.test_files()
    groups = module.assign(files, {}, 2)

    flat = [name for group in groups for name in group]
    assert sorted(flat) == sorted(files)


def test_the_assignment_is_deterministic():
    """The two shards are computed by two SEPARATE processes on CI.

    `--group=1` and `--group=2` each run the packer from scratch. If the
    result depended on dict order or on an unstable sort, the two jobs
    would disagree about who owns a file -- and the file would be dropped
    or run twice, invisibly.
    """
    module = _module()
    files = module.test_files()
    durations = module.load_durations()

    first = module.assign(files, durations, 2)
    second = module.assign(list(reversed(files)), dict(reversed(list(durations.items()))), 2)

    assert first == second


def test_the_shards_are_balanced_enough_to_be_worth_sharding():
    """A split that piles everything into one shard buys nothing.

    Loose on purpose -- 25% is far wider than the 0.0% measured, because
    the weights model per-test time only and the suite keeps growing. It
    is here to catch a packer that stopped packing, not to police drift.
    """
    module = _module()
    durations = module.load_durations()
    if not durations:
        pytest.skip("no weight table committed; balance is not defined")

    groups = module.assign(module.test_files(), durations, 2)
    totals = [sum(durations.get(name, 0.0) for name in group) for group in groups]

    assert sum(totals) > 0
    assert abs(totals[0] - totals[1]) / sum(totals) < 0.25, (
        f"shards weigh {totals[0]:.0f} s against {totals[1]:.0f} s"
    )


def test_the_weight_table_only_names_files_that_exist():
    """A weight for a deleted file is harmless; a lot of them means rot.

    Regenerating is one command against any run's JUnit artifact, and
    this is what says it is due.
    """
    module = _module()
    durations = module.load_durations()
    if not durations:
        pytest.skip("no weight table committed")

    known = set(module.test_files())
    stale = sorted(name for name in durations if name not in known)

    assert len(stale) < 25, (
        f"{len(stale)} weights name files that no longer exist: {stale[:5]}... "
        "Regenerate with `python tools/suite_shards.py --update=<junit.xml>`."
    )


# --- pinned placement: adding a test file must not move any other file ----------------------------------


def _pins(module, splits=None):
    """The pin table for `splits` shards; by default the one CI uses, which is the size of the workflow's matrix."""
    return module.load_pins().get(str(_ci_splits() if splits is None else splits), {})


def test_adding_a_test_file_moves_no_other_file():
    """THE POINT OF THE PINS. Without them, adding one file re-sorted everything and about fifty files
    changed shard, so a PR's shard held a combination master had never run (docs/LESSONS.md, "ADDING A TEST
    FILE RE-BALANCES THE SHARDS"). Compared against the table-free packer to show the difference is real."""
    module = _module()
    files = module.test_files()
    durations = module.load_durations()
    n = _ci_splits()
    pins = _pins(module)
    assert pins, f"no pin table committed for {n} shards"

    def placement(groups):
        return {name: i for i, group in enumerate(groups) for name in group}

    extra = files + ["tests/test_a_brand_new_file.py", "tests/test_another_new_file.py"]
    before = placement(module.assign(files, durations, n, pins))
    after = placement(module.assign(extra, durations, n, pins))
    # PINNED files are what is guaranteed not to move. An UNPINNED file is packed among the other unpinned
    # ones, so adding files can move it (a pass on master that depended on that luck failed in every leg of
    # the crash measurement's control arm, whose tree has one file fewer). `--pin-new` makes it permanent.
    assert {k: v for k, v in after.items() if k in before and k in pins} == {k: v for k, v in before.items() if k in pins}

    # The control: with no pins the same addition does reshuffle existing files (if it ever stops doing so
    # the pins are no longer what is keeping this test green, and it should be looked at).
    loose_before = placement(module.assign(files, durations, n))
    loose_after = placement(module.assign(extra, durations, n))
    assert any(loose_after[k] != v for k, v in loose_before.items()), "the control no longer reshuffles"


def test_the_committed_pins_are_what_the_split_uses():
    module = _module()
    pins = _pins(module)
    files = module.test_files()
    groups = module.assign(files, module.load_costs(), _ci_splits(), pins)
    placed = {name: i for i, group in enumerate(groups) for name in group}
    assert all(placed[name] == shard for name, shard in pins.items() if name in placed)


@pytest.mark.parametrize("table", [2, 3])
@pytest.mark.parametrize("splits", [1, 2, 3, 5])
def test_pinned_assignment_is_still_an_exact_partition(splits, table):
    """Pins made for one shard count must never drop a file when asked for another: an out-of-range pin is
    ignored, not obeyed. Both committed tables are checked (the 2-way one is kept for the crash-rate workflow)."""
    module = _module()
    files = module.test_files() + ["tests/test_a_brand_new_file.py"]
    pins = _pins(module, table)
    groups = module.assign(files, module.load_durations(), splits, pins)
    flat = [name for group in groups for name in group]
    assert sorted(flat) == sorted(files)


def test_a_pin_for_a_deleted_file_is_ignored():
    module = _module()
    files = module.test_files()
    pins = dict(_pins(module), **{"tests/test_deleted_long_ago.py": 1})
    groups = module.assign(files, module.load_durations(), _ci_splits(), pins)
    assert sorted(name for group in groups for name in group) == sorted(files)


def test_a_new_file_goes_to_the_lighter_shard():
    module = _module()
    pins = {"tests/test_a.py": 0, "tests/test_b.py": 0, "tests/test_c.py": 1}
    durations = {"tests/test_a.py": 10.0, "tests/test_b.py": 10.0, "tests/test_c.py": 1.0}
    groups = module.assign(["tests/test_a.py", "tests/test_b.py", "tests/test_c.py", "tests/test_new.py"],
                           durations, 2, pins)
    assert "tests/test_new.py" in groups[1]


def test_the_pins_have_not_rotted():
    """A pin table is placement, not a list of what exists, so a few unpinned or stale entries are fine.
    Many mean balance has drifted (every unpinned file piles onto whichever shard was lighter)."""
    module = _module()
    pins = _pins(module)
    files = set(module.test_files())
    unpinned = sorted(files - set(pins))
    stale = sorted(set(pins) - files)
    assert len(unpinned) < 25, (
        f"{len(unpinned)} test files have no pin ({unpinned[:3]}...). Re-pin in a PR of its own: "
        f"`python tools/suite_shards.py --repin --splits={_ci_splits()}` (it balances on `load_costs`, the hook included)."
    )
    assert len(stale) < 25, f"{len(stale)} pins name files that no longer exist: {stale[:3]}..."


def test_the_pinned_shards_are_balanced_on_what_a_shard_costs():
    """Balanced on `load_costs`, not on reported test time: a shard's CI wall time is its tests + the `gc.collect()` after each Qt
    test + ~30 s, so a split balanced on the first term alone is lopsided in the second (shard 1 carried 714 s of collects against
    shard 2's 394 s, while the weights said they were even). Measured on the committed tables: the 3-way table is at 0.09% (spread
    over total cost), the old packer's 3-way table, made on reported time, at 2.0%, and the 2-way split CI ran until 2026-10-06 at
    7.2%. The tolerance is 1%: wide enough for files added since (each goes to the lightest shard), narrow enough to fail a table that
    was made without the hook. The weights are committed, so this does not move with the runner's noise."""
    module = _module()
    if not module.load_costs():
        pytest.skip("no weight table committed")
    n = _ci_splits()
    groups = module.assign(module.test_files(), splits=n, pins=_pins(module), **module.placement_model(n))
    totals = module.shard_costs(groups, rates=module.load_hook_rates(n))
    assert max(totals) - min(totals) < 0.01 * sum(totals), f"shards cost {[round(t) for t in totals]} s"


def test_the_pinned_shards_are_balanced_on_the_prices_a_run_measured_not_on_the_mean():
    """The mean price (0.40 s) hid the whole problem: CI run 743 measured a collect at 0.474, 0.209 and 0.075 s in the three shards
    (`_retained_windows` grows through a shard, and every collect walks it), so a table balanced on the mean looked level at 1146 s a
    shard and ran 1258, 700 and 1037. The measured prices are committed; this is the same sum as the guard above with the mean put
    back, and it has to be LOPSIDED, or the prices are not doing anything and the guard above is the old model under a new name."""
    module = _module()
    n = _ci_splits()
    rates = module.load_hook_rates(n)
    if rates is None:
        pytest.skip(f"no measured hook prices for {n} shards (`--repin` deletes them): run `--update=<shard 1 xml>,<shard 2 xml>,...` on a CI run")
    groups = module.assign(module.test_files(), splits=n, pins=_pins(module), **module.placement_model(n))
    measured = module.shard_costs(groups, rates=rates)
    flat = module.shard_costs(groups)
    assert max(measured) - min(measured) < max(flat) - min(flat), (measured, flat)


def test_the_hook_prices_are_a_list_per_split_count_with_one_price_per_shard(tmp_path):
    module = _module()
    committed = __import__("json").loads(module.DEFAULT_RATES.read_text(encoding="utf-8"))
    assert all(len(v) == int(k) and all(0.0 < r < 2.0 for r in v) for k, v in committed.items()), committed
    # a list made for another split count is no list at all, so a layout nobody measured is priced flat, not by somebody else's numbers
    path = tmp_path / "rates.json"
    path.write_text('{"3": [0.4, 0.2, 0.1]}', encoding="utf-8")
    assert module.load_hook_rates(3, path) == [0.4, 0.2, 0.1]
    assert module.load_hook_rates(2, path) is None
    assert module.load_hook_rates(3, tmp_path / "missing.json") is None
    path.write_text('{"3": [0.4, 0.2]}', encoding="utf-8")
    assert module.load_hook_rates(3, path) is None


def test_pin_new_pins_unpinned_files_where_they_already_sit_and_moves_nobody(tmp_path):
    module = _module()
    out = tmp_path / "pins.json"
    files = module.test_files()

    module.pin_new  # noqa: B018 - exists
    # Start from the committed table minus a few entries, to have something to pin.
    table = module.load_pins()
    dropped = sorted(_pins(module))[:3]
    table["2"] = {k: v for k, v in table["2"].items() if k not in dropped}
    out.write_text(__import__("json").dumps(table), encoding="utf-8")

    # Where those files SIT with their pins removed: the packer puts each on the lighter shard once the pinned files are counted. That is
    # what `pin_new` must record. It is NOT where the committed pins had them: which shard is lighter changes whenever any test file is
    # added, so comparing with the old pins failed for a PR that added one file and said nothing about this tool.
    # (`pin_new` packs on what a shard costs -- reported time plus the hook -- so this has to, or the two agree only when the lighter shard
    # happens to be the same on both measures, which the 2026-10-06 weights stopped doing)
    sit_now = module.assign(files, splits=2, pins=table["2"], **module.placement_model(2))
    placed_now = {name: i for i, group in enumerate(sit_now) for name in group}

    fresh = module.pin_new(2, out)
    assert set(dropped) <= set(fresh)
    pinned = __import__("json").loads(out.read_text(encoding="utf-8"))["2"]
    assert all(name in pinned for name in files)
    # Every previously pinned file kept its pin; the re-pinned ones landed where the packer had put them.
    assert all(pinned[k] == v for k, v in table["2"].items())
    assert all(pinned[name] == placed_now[name] for name in dropped)


# --- slice: run only a window of one shard (the crash-bisect workflow) -----------------------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [("0:2", ["a", "b"]), (":2", ["a", "b"]), ("2:", ["c", "d"]), ("1:3", ["b", "c"]), ("0:99", ["a", "b", "c", "d"])],
)
def test_slice_is_a_window_onto_the_shards_file_list(spec, expected):
    assert _module().slice_files(["a", "b", "c", "d"], spec) == expected


@pytest.mark.parametrize("spec", ["5:", "3:1", "abc", "1-3", ""])
def test_a_slice_that_selects_nothing_or_is_malformed_is_an_error_not_a_pass(spec):
    """An empty window would run zero tests and report a clean pass, which a measurement would count."""
    with pytest.raises(ValueError):
        _module().slice_files(["a", "b", "c", "d"], spec)


def test_the_cli_slice_is_a_prefix_of_the_unsliced_shard():
    module = _module()
    shard = module.assign(module.test_files(), module.load_costs(), _ci_splits(), _pins(module))[0]
    assert module.slice_files(shard, "0:5") == shard[:5]


# --- the number of shards has ONE source, and the pins and costs are what CI will actually run -----------------


def test_the_workflow_runs_exactly_the_shards_the_committed_pins_cover():
    """THE DANGEROUS MISMATCH IS A MATRIX SMALLER THAN THE SPLIT. `--splits=3` with a matrix of [1, 2] runs two thirds of the suite and
    every job is green; `--splits=2` with [1, 2, 3] fails shard 3 outright, which is the kind one. So the matrix is the split count
    (below), and the pin table made for that count has to exist and cover every file, or a shard would be packed from weights and
    move files that nobody chose to move."""
    module = _module()
    n = _ci_splits()
    pins = _pins(module)
    files = module.test_files()
    assert pins, f"the workflow runs {n} shards and `tools/suite-shard-pins.json` has no table for {n}"
    assert not (set(files) - set(pins)), (
        f"files with no pin in the {n}-way table: {sorted(set(files) - set(pins))[:3]}. A PR that adds a test file runs "
        "`python tools/suite_shards.py --pin-new` (its default is the matrix's size, so it pins into the table CI uses)."
    )
    groups = module.assign(files, module.load_costs(), n, pins)
    flat = [name for group in groups for name in group]
    assert sorted(flat) == sorted(files) and len(groups) == n and all(groups), "the CI split is not an exact, non-empty partition"


def test_the_split_count_is_written_once_and_the_script_cannot_default_it():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    suite_job = workflow.split("\n  gates:")[0]
    # both attempts of the suite step take the count from the matrix itself
    runs = re.findall(r"^\s+run: \./tools/ci_suite_shard\.ps1 .*$", suite_job, re.MULTILINE)
    assert len(runs) == 2, "the suite job no longer runs the shard script exactly twice (an attempt and its retry)"
    assert all("-Splits ${{ strategy.job-total }}" in run for run in runs), f"an attempt that does not pass the matrix size: {runs}"
    assert re.search(r"^\s+name: test suite \${{ matrix\.shard }}/\${{ strategy\.job-total }}\s*$", suite_job, re.MULTILINE), (
        "the job name no longer says how many shards there are")
    assert not re.search(r"--splits[= ]\d", suite_job), "a literal split count in the workflow"

    script = SHARD_SCRIPT.read_text(encoding="utf-8")
    assert re.search(r"\[Parameter\(Mandatory\)\]\[int\]\$Splits", script), "-Splits must be mandatory: a default is a silent 2-way split"
    assert not re.search(r"--splits=\d", script), "the script hard-codes a split count"
    assert "--splits=$Splits" in script

    # the crash-rate workflow samples the 2-way split its records were measured on, and says so by passing 2 explicitly
    crash = CRASH_RATE_WORKFLOW.read_text(encoding="utf-8")
    assert crash.count("ci_suite_shard.ps1") == 2 and crash.count("-Splits 2") == 2
    assert "--splits=2" in crash and _pins(_module(), 2), "the 2-way pin table must stay committed for it"


def test_the_default_split_count_is_the_workflows_matrix_size(tmp_path):
    """`--pin-new` and `--repin` default to the count CI runs, so the habit of running them with no argument pins into the table CI
    uses (with a default of 2, a plain `--pin-new` filled the retired 2-way table and the 3-way guard failed for a PR that did
    everything the docs said)."""
    module = _module()
    assert module.ci_splits() == _ci_splits()
    script = REPO / "tools" / "suite_shards.py"
    default = subprocess.run([sys.executable, str(script), "--group=1"], capture_output=True, text=True)
    explicit = subprocess.run([sys.executable, str(script), f"--splits={_ci_splits()}", "--group=1"], capture_output=True, text=True)
    assert default.returncode == 0 and default.stdout.strip() and default.stdout == explicit.stdout
    # and when the matrix cannot be read, the old default, not a crash
    assert module.ci_splits(tmp_path / "missing.yml") == 2
    odd = tmp_path / "odd.yml"
    odd.write_text("jobs:\n  suite:\n    strategy:\n      matrix:\n        os: [a]\n", encoding="utf-8")
    assert module.ci_splits(odd) == 2


def test_a_files_cost_is_its_reported_time_plus_the_collects_after_its_qt_tests():
    module = _module()
    costs = module.load_costs({"tests/test_a.py": 10.0, "tests/test_b.py": 5.0}, {"tests/test_a.py": 10, "tests/test_c.py": 3})
    assert costs["tests/test_a.py"] == pytest.approx(10.0 + 10 * module.HOOK_SECONDS)
    assert costs["tests/test_b.py"] == 5.0                                   # no Qt tests: no hook
    assert costs["tests/test_c.py"] == pytest.approx(3 * module.HOOK_SECONDS)  # a file the timing table has not met still has a hook


def test_the_hook_term_keeps_a_qt_heavy_file_from_sharing_a_shard_it_would_overload():
    """The failure this is for: three files, a and b of equal reported time but a with 100 Qt tests (40 s of collects), and c of 60 s.
    Packed on reported time alone, a and b look interchangeable and share a shard; with the hook, a is alone and b joins c."""
    module = _module()
    files = ["tests/test_a.py", "tests/test_b.py", "tests/test_c.py"]
    times = {"tests/test_a.py": 50.0, "tests/test_b.py": 50.0, "tests/test_c.py": 60.0}
    blind = module.assign(files, times, 2)
    aware = module.assign(files, module.load_costs(times, {"tests/test_a.py": 100}), 2)
    assert any({"tests/test_a.py", "tests/test_b.py"} <= set(group) for group in blind), "the control changed"
    assert ["tests/test_a.py"] in aware and ["tests/test_b.py", "tests/test_c.py"] in aware


def test_a_collect_costs_what_its_shard_charges_and_a_qt_free_file_costs_the_same_everywhere():
    """The property the rebalance relies on: a file that never requests `qapp` has no collect after it and builds no window, so moving
    it changes only the reported time it carries; a Qt file costs differently in a shard with a heavy heap than in one with a light one."""
    module = _module()
    assert module.shard_costs([["f"], ["f"]], {"f": 7.0}, {}, [0.5, 1.0]) == [7.0, 7.0]
    assert module.shard_costs([["g"], ["g"]], {"g": 1.0}, {"g": 10}, [0.5, 1.0]) == [6.0, 11.0]
    assert module.shard_costs([["g"], ["g"]], {"g": 1.0}, {"g": 10}) == pytest.approx([1.0 + 10 * module.HOOK_SECONDS] * 2)  # no rates: flat


def test_a_new_file_goes_where_it_is_cheapest_at_each_shards_own_price():
    module = _module()
    # (1) the shard that LOOKS lighter on the mean price is the heavier one at its own: y's 100 collects cost 100 s there, not 40
    files = ["tests/test_x.py", "tests/test_y.py", "tests/test_z.py"]
    pins = {"tests/test_x.py": 0, "tests/test_y.py": 1}
    reported = {"tests/test_x.py": 100.0, "tests/test_y.py": 50.0, "tests/test_z.py": 1.0}
    counts = {"tests/test_y.py": 100}
    assert module.assign(files, module.load_costs(reported, counts), 2, pins)[1][-1] == "tests/test_z.py", "the control changed"
    priced = module.assign(files, reported, 2, pins, counts, [0.5, 1.0])
    assert "tests/test_z.py" in priced[0]
    # (2) a Qt-heavy new file goes to the shard whose collects are cheap, even when the totals tie and index order would say otherwise
    files = ["tests/test_x.py", "tests/test_y.py", "tests/test_w.py"]
    pins = {"tests/test_x.py": 0, "tests/test_y.py": 1}
    reported = {"tests/test_x.py": 100.0, "tests/test_y.py": 100.0, "tests/test_w.py": 1.0}
    placed = module.assign(files, reported, 2, pins, {"tests/test_w.py": 100}, [1.0, 0.1])
    assert "tests/test_w.py" in placed[1]
    # prices for another count are ignored, never mis-applied: the shard count is the length
    assert module.assign(files, reported, 2, pins, {"tests/test_w.py": 100}, [1.0, 0.1, 0.1]) == module.assign(files, reported, 2, pins)


def test_the_placement_model_prices_with_the_measured_rates_where_there_are_some_and_flat_where_there_are_none():
    """The committed pins cover every file, so the only thing that reaches this is a test file with no pin yet (what `--pin-new` and the
    CI `--group` call place): it has to go by the same prices the guard balances on."""
    module = _module()
    n = _ci_splits()
    measured = module.placement_model(n)
    assert measured["rates"] == module.load_hook_rates(n) and measured["counts"] == module.load_qapp_counts()
    assert measured["durations"] == module.load_durations(), "with prices, `durations` is reported time only: the hook is added per shard"
    unmeasured = module.placement_model(n + 5)
    assert set(unmeasured) == {"durations"} and unmeasured["durations"] == module.load_costs()


def _junit(path, cases, calls=None, seconds=None):
    props = ""
    if calls is not None:
        props = (f'<properties><property name="openchem_gc_calls" value="{calls}"/>'
                 f'<property name="openchem_gc_collect_seconds" value="{seconds}"/></properties>')
    body = "".join(f'<testcase classname="tests.{name}" name="t{i}" time="{t}"/>' for i, (name, t) in enumerate(cases))
    path.write_text(f'<testsuites><testsuite name="pytest">{props}{body}</testsuite></testsuites>', encoding="utf-8")


def test_update_writes_the_weights_of_every_shard_and_each_shards_price_of_a_collect(tmp_path):
    import json

    module = _module()
    _junit(tmp_path / "1.xml", [("test_a", 3.0), ("test_a", 2.0), ("test_b", 1.0)], calls=10, seconds=5.0)
    _junit(tmp_path / "2.xml", [("test_c", 4.0)], calls=10, seconds=1.0)
    _junit(tmp_path / "3.xml", [("test_d", 7.5)], calls=0, seconds=0.0)       # no Qt test: no price of its own, the run's mean
    durations, rates = tmp_path / "durations.json", tmp_path / "rates.json"
    count = module.update_from_junit([tmp_path / "1.xml", tmp_path / "2.xml", tmp_path / "3.xml"], durations, rates)
    assert count == 4
    assert json.loads(durations.read_text(encoding="utf-8")) == {
        "tests/test_a.py": 5.0, "tests/test_b.py": 1.0, "tests/test_c.py": 4.0, "tests/test_d.py": 7.5}
    assert json.loads(rates.read_text(encoding="utf-8")) == {"3": [0.5, 0.1, 0.3]}     # 6 s over 20 collects is 0.3
    # one file is an unsharded run: it has weights and no per-shard prices to write, and an existing table is left alone
    module.update_from_junit(tmp_path / "1.xml", durations, rates)
    assert json.loads(rates.read_text(encoding="utf-8")) == {"3": [0.5, 0.1, 0.3]}
    # an artifact from before the hook published its counters has no price to read; the weights still update and no price is invented
    _junit(tmp_path / "old1.xml", [("test_a", 1.0)])
    _junit(tmp_path / "old2.xml", [("test_b", 1.0)])
    other = tmp_path / "other.json"
    module.update_from_junit([tmp_path / "old1.xml", tmp_path / "old2.xml"], durations, other)
    assert not other.exists()


def test_repin_deletes_the_prices_it_makes_stale_and_only_for_its_own_split_count(tmp_path):
    import json

    module = _module()
    pins, rates = tmp_path / "pins.json", tmp_path / "rates.json"
    rates.write_text(json.dumps({"2": [0.4, 0.3], "3": [0.5, 0.2, 0.1]}), encoding="utf-8")
    module.repin(3, pins, rates)
    assert json.loads(rates.read_text(encoding="utf-8")) == {"2": [0.4, 0.3]}
    assert set(json.loads(pins.read_text(encoding="utf-8"))["3"]) == set(module.test_files())


def test_the_qapp_counts_name_only_files_that_exist_and_are_positive():
    module = _module()
    counts = module.load_qapp_counts()
    assert counts, "no qapp-count table committed: the hook is invisible to the split"
    files = set(module.test_files())
    assert not (set(counts) - files), f"counts for files that do not exist: {sorted(set(counts) - files)[:3]}"
    assert all(isinstance(v, int) and v > 0 for v in counts.values())


def test_the_qapp_counting_plugin_counts_what_the_hook_collects_after(tmp_path):
    """The plugin must use the criterion `tests/conftest.py` uses for who gets a gc.collect(), checked on a file that defines its own
    `qapp`: one test requests it directly, one through another fixture, one not at all."""
    sample = tmp_path / "test_sample_qt.py"
    sample.write_text(
        "import pytest\n\n"
        "@pytest.fixture\ndef qapp():\n    return object()\n\n"
        "@pytest.fixture\ndef window(qapp):\n    return object()\n\n"
        "def test_direct(qapp):\n    pass\n\n"
        "def test_through_another_fixture(window):\n    pass\n\n"
        "def test_no_qt():\n    pass\n",
        encoding="utf-8",
    )
    out = tmp_path / "counts.json"
    import json
    import os

    env = {**os.environ, "SUITE_QAPP_OUT": str(out), "PYTHONPATH": str(REPO / "tools")}
    run = subprocess.run(
        [sys.executable, "-m", "pytest", str(sample), "--collect-only", "-q", "-p", "suite_qapp_plugin", "-p", "no:cacheprovider",
         "--rootdir", str(tmp_path)],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(out.read_text(encoding="utf-8")) == {"test_sample_qt.py": 2}
    # and the criterion is the conftest's own, character for character, so the two cannot drift apart unseen
    assert '"qapp" in getattr(item, "fixturenames", ())' in (REPO / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert '"qapp" in getattr(item, "fixturenames", ())' in (REPO / "tools" / "suite_qapp_plugin.py").read_text(encoding="utf-8")
