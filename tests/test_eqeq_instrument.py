"""TRIAGE.md 2.9: the EQeq instrument and its result pins.

The corpus tests need the ACS accompanying files (structures and the published source), which are
not in the repository; they skip with a named reason when absent. The parameter table IS committed,
so the table tests always run.
"""

from __future__ import annotations

import importlib.util
import math
import pathlib
import sys

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("eqeq_check", ROOT / "benchmarks" / "charges" / "models" / "eqeq_check.py")
eq = importlib.util.module_from_spec(_spec)
sys.modules["eqeq_check"] = eq
_spec.loader.exec_module(eq)

needs_structures = pytest.mark.skipif(not eq.STRUCTURES.exists(),
                                      reason="the Wilmer 2012 accompanying structures are not on this machine")


# --- the reconstructed table ----------------------------------------------------------------------


def test_the_table_reproduces_values_printed_in_both_sources():
    table = eq.parameter_table()
    assert table["H"]["potentials"][0] == 13.598
    assert table["C"]["potentials"][:4] == [11.26, 24.383, 47.887, 64.492]
    assert table["O"]["potentials"][0] == 13.618  # Moore prints oxygen's SYMBOL as the digit 0
    assert table["Zn"]["potentials"][:3] == [9.394, 17.964, 39.722]
    # Andersen's recommended affinities, including the one whose minus sign the scan prints as "2".
    assert table["C"]["affinity"] == pytest.approx(1.26212, abs=1e-5)
    assert table["O"]["affinity"] == pytest.approx(1.46111, abs=1e-5)
    assert table["N"]["affinity"] == pytest.approx(-0.07, abs=1e-5)
    assert table["N"]["affinity"] < 0, "nitrogen does not bind an extra electron"


def test_an_element_with_no_bound_anion_has_no_affinity_and_refuses_at_a_neutral_centre():
    table = eq.parameter_table()
    assert table["Mg"]["affinity"] is None and table["Mg"]["affinity_as_printed"] == "<0"
    # At its +2 centre magnesium never reads the affinity, which is why the corpus runs.
    chi, hardness = eq.electronegativity_and_hardness("Mg", 2, table)
    assert chi == pytest.approx(0.5 * (80.143 + 15.035))
    assert hardness == pytest.approx(80.143 - 15.035)
    # At a neutral centre it refuses rather than substituting zero.
    with pytest.raises(KeyError, match="electron affinity"):
        eq.electronegativity_and_hardness("Mg", 0, table)


def test_hydrogen_uses_the_papers_ad_hoc_affinity_not_the_measured_one():
    table = eq.parameter_table()
    chi, hardness = eq.electronegativity_and_hardness("H", 0, table)
    assert chi == pytest.approx(0.5 * (13.598 + eq.HYDROGEN_I0))
    assert hardness == pytest.approx(13.598 - eq.HYDROGEN_I0)
    assert eq.HYDROGEN_I0 == -2.0
    assert table["H"]["affinity"] == pytest.approx(0.754204, abs=1e-6)  # kept, and deliberately unused


# --- the model ------------------------------------------------------------------------------------


def test_the_constants_are_the_codes_own_not_the_articles():
    """`EQeq_v1_00.cpp` uses k = 14.4 and lambda = 1.2, so a pair carries 8.64 eV A. Reading the
    article alone gives 14.399645/1.67 = 8.6226, and that 0.2% is visible in the third decimal."""
    assert (eq.COULOMB_EV_ANGSTROM, eq.COULOMB_SCALING) == (14.4, 1.2)
    assert eq.COULOMB_SCALING * eq.COULOMB_EV_ANGSTROM / 2 == pytest.approx(8.64)
    assert eq.COULOMB_EV_ANGSTROM / eq.DIELECTRIC == pytest.approx(8.6227, abs=1e-3)


def test_the_orbital_term_carries_TWO_a_and_meets_the_papers_own_limit():
    """The article's eq 64 prints J/K where the code has 2J/k. The limit the paper states is the
    check: two overlapping atoms of the same element interact with an energy equal to the hardness."""
    hardness = np.array([[10.0]])
    distance = np.array([[1e-6]])
    coulomb = eq.COULOMB_EV_ANGSTROM
    pair = (eq.COULOMB_SCALING * coulomb / 2) * (1.0 / distance + eq.orbital_overlap(hardness, distance, coulomb))
    # The limit is lambda * J, not J: the paper states the overlapped pair energy "will be equal to
    # the chemical hardness", which holds at lambda = 1 and its own code runs lambda = 1.2.
    assert float(pair[0, 0]) == pytest.approx(eq.COULOMB_SCALING * 10.0, rel=1e-3)

    # At a BONDED distance -- where this term does its work, and where the two readings separate --
    # the article's form differs from the code's by exactly a * exp(-(ar)^2).
    bonded = np.array([[1.5]])
    a = hardness / coulomb
    as_printed = np.exp(-((a * bonded) ** 2)) * (a - a * a * bonded - 1.0 / bonded)
    code = eq.orbital_overlap(hardness, bonded, coulomb)
    assert not np.allclose(as_printed, code)
    difference = float(a[0, 0] * np.exp(-((a[0, 0] * bonded[0, 0]) ** 2)))
    assert float(code[0, 0] - as_printed[0, 0]) == pytest.approx(difference, rel=1e-9)
    # The scale of the mistake: at 1.5 A the code's term is -0.0004 and the article's reading -0.235,
    # a spurious short-range term on every bonded pair -- which is why the light atoms missed.
    assert float(code[0, 0]) == pytest.approx(-0.00039, abs=1e-5)
    assert float(as_printed[0, 0]) == pytest.approx(-0.2350, abs=1e-4)


def test_the_published_rounding_is_replicated_including_its_neutrality_nudge():
    charges = np.array([0.2004, 0.2004, -0.2004, -0.2004])
    assert np.allclose(eq.round_charges(charges), [0.2, 0.2, -0.2, -0.2])
    # A set that no longer sums to zero after rounding: the FIRST n atoms move by one unit.
    charges = np.array([0.0005, 0.0005, 0.0005, -0.0015])
    rounded = eq.round_charges(charges)
    assert abs(rounded.sum()) < 1e-9
    assert rounded[0] != pytest.approx(round(charges[0], 3))


def test_the_cell_vectors_of_an_orthorhombic_cell_are_its_lengths():
    vectors = eq.cell_vectors([6.8179, 16.1430, 13.9390], [90.0, 90.0, 90.0])
    assert np.allclose(vectors, np.diag([6.8179, 16.1430, 13.9390]), atol=1e-9)


# --- the corpus -----------------------------------------------------------------------------------


@needs_structures
def test_the_deposited_files_reproduce_the_papers_table_2():
    """The oracle's own check, independent of our model: mean |EQeq - REPEAT| per MOF."""
    printed = {"MIL-47": 0.11, "IRMOF-1": 0.16, "IRMOF-3": 0.24, "ZIF-8": 0.16, "HKUST-1": 0.15}
    for name, expected in printed.items():
        eqeq = eq.read_structure(eq.STRUCTURES / f"{name}_EQeq.mol")
        repeat = eq.read_structure(eq.STRUCTURES / f"{name}_REPEAT.mol")
        match = eq.match_by_position(eqeq, repeat)
        assert float(np.mean(np.abs(eqeq["charges"] - repeat["charges"][match]))) == pytest.approx(expected, abs=5e-3)


@needs_structures
def test_the_four_files_of_a_mof_do_not_share_an_atom_order():
    """Why `match_by_position` exists: index-by-index, MIL-47 reads 0.47 against a printed 0.11."""
    eqeq = eq.read_structure(eq.STRUCTURES / "MIL-47_EQeq.mol")
    repeat = eq.read_structure(eq.STRUCTURES / "MIL-47_REPEAT.mol")
    assert eqeq["elements"] != repeat["elements"]
    assert float(np.mean(np.abs(eqeq["charges"] - repeat["charges"]))) > 0.4
    match = eq.match_by_position(eqeq, repeat)
    assert float(np.mean(np.abs(eqeq["charges"] - repeat["charges"][match]))) == pytest.approx(0.112, abs=1e-3)


@needs_structures
@pytest.mark.parametrize("name", ["MIL-47", "IRMOF-1", "ZIF-8"])
def test_result_pin_every_atom_matches_the_published_charge(name):
    """Section 3.9's headline on three of the twelve, chosen for size and for covering Zn, V and N."""
    structure = eq.read_structure(eq.STRUCTURES / f"{name}_EQeq.mol")
    charges = eq.solve(structure, eq.parameter_table(), shells=2, factor=1.0)
    assert np.array_equal(eq.round_charges(charges), structure["charges"])
    assert float(np.abs(np.sum(charges))) < 1e-9


@needs_structures
def test_result_pin_the_published_charges_are_the_papers_5x5x5_setting():
    """**THE LATTICE SUM IS NOT FULLY CONVERGED, and the published numbers are L = 2.** Measured:
    MIL-47 moves by up to 5.4e-04 between L = 2 and L = 3, which changes the third decimal of 10 of
    its 72 atoms, so only 86% still match the printed charges at L = 3. IRMOF-1 moves by 8e-10 and
    none of its atoms change. The paper calls the 5x5x5 to 7x7x7 change negligible; for MIL-47 it is
    visible at the precision the charges are printed to."""
    table = eq.parameter_table()
    mil = eq.read_structure(eq.STRUCTURES / "MIL-47_EQeq.mol")
    near, far = eq.solve(mil, table, 2, 1.0), eq.solve(mil, table, 3, 1.0)
    assert float(np.max(np.abs(near - far))) == pytest.approx(5.4e-4, abs=1e-4)
    assert np.array_equal(eq.round_charges(near), mil["charges"])
    assert int(np.sum(eq.round_charges(far) != mil["charges"])) == 10

    irmof = eq.read_structure(eq.STRUCTURES / "IRMOF-1_EQeq.mol")
    assert float(np.max(np.abs(eq.solve(irmof, table, 2, 1.0) - eq.solve(irmof, table, 3, 1.0)))) < 1e-8
