"""Guards for the CI shard splitter.

**THE FAILURE THIS FILE EXISTS FOR IS SILENT.** If the splitter ever
drops a test file -- an off-by-one in the bin packing, a glob that stops
matching, a stale committed list -- that file runs in NO shard, every job
stays green, and the coverage is gone with nothing to notice. Every other
property here is secondary to the partition being exact.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


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


def _pins(module, splits=2):
    return module.load_pins().get(str(splits), {})


def test_adding_a_test_file_moves_no_other_file():
    """THE POINT OF THE PINS. Without them, adding one file re-sorted everything and about fifty files
    changed shard, so a PR's shard held a combination master had never run (docs/LESSONS.md, "ADDING A TEST
    FILE RE-BALANCES THE SHARDS"). Compared against the table-free packer to show the difference is real."""
    module = _module()
    files = module.test_files()
    durations = module.load_durations()
    pins = _pins(module)
    assert pins, "no pin table committed for 2 shards"

    def placement(groups):
        return {name: i for i, group in enumerate(groups) for name in group}

    extra = files + ["tests/test_a_brand_new_file.py", "tests/test_another_new_file.py"]
    before = placement(module.assign(files, durations, 2, pins))
    after = placement(module.assign(extra, durations, 2, pins))
    # PINNED files are what is guaranteed not to move. An UNPINNED file is packed among the other unpinned
    # ones, so adding files can move it (a pass on master that depended on that luck failed in every leg of
    # the crash measurement's control arm, whose tree has one file fewer). `--pin-new` makes it permanent.
    assert {k: v for k, v in after.items() if k in before and k in pins} == {k: v for k, v in before.items() if k in pins}

    # The control: with no pins the same addition does reshuffle existing files (if it ever stops doing so
    # the pins are no longer what is keeping this test green, and it should be looked at).
    loose_before = placement(module.assign(files, durations, 2))
    loose_after = placement(module.assign(extra, durations, 2))
    assert any(loose_after[k] != v for k, v in loose_before.items()), "the control no longer reshuffles"


def test_the_committed_pins_are_what_the_split_uses():
    module = _module()
    pins = _pins(module)
    files = module.test_files()
    groups = module.assign(files, module.load_durations(), 2, pins)
    placed = {name: i for i, group in enumerate(groups) for name in group}
    assert all(placed[name] == shard for name, shard in pins.items() if name in placed)


@pytest.mark.parametrize("splits", [1, 2, 3, 5])
def test_pinned_assignment_is_still_an_exact_partition(splits):
    """Pins made for 2 shards must never drop a file when asked for another count: an out-of-range pin is
    ignored, not obeyed."""
    module = _module()
    files = module.test_files() + ["tests/test_a_brand_new_file.py"]
    pins = _pins(module, 2)
    groups = module.assign(files, module.load_durations(), splits, pins)
    flat = [name for group in groups for name in group]
    assert sorted(flat) == sorted(files)


def test_a_pin_for_a_deleted_file_is_ignored():
    module = _module()
    files = module.test_files()
    pins = dict(_pins(module), **{"tests/test_deleted_long_ago.py": 1})
    groups = module.assign(files, module.load_durations(), 2, pins)
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
        "`python tools/suite_shards.py --repin --splits=2`."
    )
    assert len(stale) < 25, f"{len(stale)} pins name files that no longer exist: {stale[:3]}..."


def test_the_pinned_shards_are_balanced_enough():
    module = _module()
    durations = module.load_durations()
    if not durations:
        pytest.skip("no weight table committed")
    groups = module.assign(module.test_files(), durations, 2, _pins(module))
    totals = [sum(durations.get(name, 0.0) for name in group) for group in groups]
    assert abs(totals[0] - totals[1]) / sum(totals) < 0.25, f"shards weigh {totals[0]:.0f} s vs {totals[1]:.0f} s"


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

    # WHERE THE PACKER PUTS THEM NOW, with those pins gone -- the contract of `pin_new`. It used to be
    # compared with their placement under the FULL pin table, which holds only while the greedy packer
    # happens to send them back to the shard they were pinned in: adding one pinned test file anywhere
    # flipped it, and the failure named a file the change never touched.
    sitting = module.assign(files, module.load_durations(), 2, table["2"])
    placed_now = {name: i for i, group in enumerate(sitting) for name in group}

    fresh = module.pin_new(2, out)
    assert set(dropped) <= set(fresh)
    pinned = __import__("json").loads(out.read_text(encoding="utf-8"))["2"]
    assert all(name in pinned for name in files)
    # Every previously pinned file kept its pin; the re-pinned ones landed where the packer had put them.
    assert all(pinned[k] == v for k, v in table["2"].items())
    assert all(pinned[name] == placed_now[name] for name in dropped)
