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
