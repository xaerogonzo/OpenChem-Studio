"""The prep-and-box survey's rules, on made-up atoms so every distance is known."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "docking" / "prep_box_core.py"
_spec = importlib.util.spec_from_file_location("prep_box_core", _PATH)
core = importlib.util.module_from_spec(_spec)
sys.modules["prep_box_core"] = core  # a dataclass looks its own module up
_spec.loader.exec_module(core)

CRYSTAL = [("C", (0.0, 0.0, 0.0)), ("C", (1.5, 0.0, 0.0)), ("O", (3.0, 0.0, 0.0))]


def test_identical_atoms_have_zero_rmsd_whatever_their_order():
    shuffled = [CRYSTAL[2], CRYSTAL[0], CRYSTAL[1]]
    assert core.assignment_rmsd(shuffled, CRYSTAL) == pytest.approx(0.0)


def test_a_uniform_shift_is_the_rmsd():
    moved = [(e, (x, y + 2.0, z)) for e, (x, y, z) in CRYSTAL]
    assert core.assignment_rmsd(moved, CRYSTAL) == pytest.approx(2.0)


def test_elements_are_never_swapped_to_lower_the_distance():
    swapped = [("O", (0.0, 0.0, 0.0)), ("C", (1.5, 0.0, 0.0)), ("C", (3.0, 0.0, 0.0))]
    assert core.assignment_rmsd(swapped, CRYSTAL) > 1.0


def test_hydrogens_are_ignored_and_missing_atoms_are_unmeasurable():
    with_h = CRYSTAL + [("H", (0.0, 1.0, 0.0))]
    assert core.assignment_rmsd(with_h, CRYSTAL) == pytest.approx(0.0)
    assert core.assignment_rmsd(CRYSTAL[:2], CRYSTAL) is None
    assert core.assignment_rmsd([], CRYSTAL) is None


def _m(rmsd, shift):
    return core.PoseMeasure(rmsd=rmsd, centroid_shift=shift)


def test_classification_separates_the_four_outcomes():
    assert core.classify([_m(1.0, 0.5), _m(5.0, 4.0)]) == core.TOP1_CORRECT
    assert core.classify([_m(4.0, 1.0), _m(1.9, 0.4)]) == core.RANKED_LOWER
    assert core.classify([_m(4.0, 1.0), _m(3.0, 2.0)]) == core.RIGHT_POCKET
    assert core.classify([_m(9.0, 8.0), _m(7.0, 6.5)]) == core.WRONG_POCKET


def test_the_two_cutoffs_are_inclusive_and_unmeasured_poses_never_count_as_correct():
    assert core.classify([_m(2.0, 0.1)]) == core.TOP1_CORRECT
    assert core.classify([_m(2.01, 3.0)]) == core.RIGHT_POCKET
    assert core.classify([_m(None, 0.1), _m(None, 0.2)]) == core.SETUP_UNMEASURABLE
    assert core.classify([_m(None, 0.1), _m(5.0, 4.0)]) == core.RIGHT_POCKET
    assert core.classify([]) == core.SETUP_DOCK


def test_the_tally_lists_every_outcome_even_at_zero():
    counts = core.tally([core.TOP1_CORRECT, core.TOP1_CORRECT, core.WRONG_POCKET])
    assert list(counts) == list(core.ORDER)
    assert counts[core.TOP1_CORRECT] == 2 and counts[core.RANKED_LOWER] == 0
