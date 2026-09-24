"""When two per-atom results can honestly be set side by side, and when they must be refused.

The point of `domain/compare.py` is what it REFUSES: a table that tabulates whatever it is handed
publishes a wrong difference, because a value for atom 5 of one structure beside a value for atom 5
of another reads as a comparison and is not one. Each refusal here is a way that has happened.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from openchem.domain.common import Provenance
from openchem.domain.compare import (
    DIFFERENT_ATOMS,
    DIFFERENT_INPUT,
    DIFFERENT_MOLECULES,
    DIFFERENT_STRUCTURE,
    DIFFERENT_UNITS,
    MAX_COMPARED,
    SAME_RESULT_TWICE,
    TOO_FEW,
    TOO_MANY,
    ComparedResult,
    Comparison,
    CompareRefusal,
    compare,
)
from openchem.domain.scientific_result import PerAtomDataset


def _dataset(method="eem", values=None, *, units="e", molecule="m1", parameters=None, **extra) -> PerAtomDataset:
    return PerAtomDataset(
        timestamp=0.0,
        property_id="geometry_partial_charge",
        name=f"Partial Charge ({method})",
        units=units,
        method=method,
        molecule_uuid=molecule,
        values=values if values is not None else {0: -0.40, 1: 0.10, 2: 0.30},
        provenance=Provenance(created_by="core", method=method, parameters=parameters or {}),
        **extra,
    )


def _result(method="eem", values=None, fingerprint="f1", calculation_input="geometry", **kw) -> ComparedResult:
    return ComparedResult(_dataset(method, values, **kw), fingerprint, calculation_input)


def _two() -> list[ComparedResult]:
    return [
        _result("eem", {0: -0.40, 1: 0.10, 2: 0.30}),
        _result("qeq", {0: -0.55, 1: 0.05, 2: 0.50}),
    ]


def test_two_methods_line_up_atom_by_atom():
    outcome = compare(_two())
    assert isinstance(outcome, Comparison)
    assert [row.index for row in outcome.rows] == [0, 1, 2]
    assert outcome.units == "e"
    first = outcome.rows[0]
    assert first.values == (-0.40, -0.55)
    assert first.deltas == pytest.approx((-0.15,)), "the FIRST result is the reference"
    assert first.spread == pytest.approx(0.15)


def test_the_largest_spread_names_the_atom_the_methods_disagree_about():
    outcome = compare(_two())
    assert outcome.largest_spread().index == 2  # 0.30 vs 0.50


def test_three_results_have_a_delta_for_each_later_one_and_a_spread_over_all():
    third = _result("gasteiger", {0: -0.30, 1: 0.20, 2: 0.10})
    outcome = compare([*_two(), third])
    row = outcome.rows[2]
    assert row.values == (0.30, 0.50, 0.10)
    assert row.deltas == pytest.approx((0.20, -0.20))
    assert row.spread == pytest.approx(0.40)


def test_one_result_is_not_a_comparison():
    refusal = compare(_two()[:1])
    assert isinstance(refusal, CompareRefusal) and refusal.code == TOO_FEW


def test_more_than_four_is_refused():
    many = [_result(f"m{i}") for i in range(MAX_COMPARED + 1)]
    assert compare(many).code == TOO_MANY


def test_different_molecules_are_refused():
    a, b = _two()
    b = replace(b, dataset=replace(b.dataset, molecule_uuid="m2"))
    assert compare([a, b]).code == DIFFERENT_MOLECULES


def test_an_edit_between_the_runs_is_refused_and_the_message_says_to_rerun():
    """The same molecule with a different drawing: atom 5 of one is not atom 5 of the other."""
    a, b = _two()
    refusal = compare([a, replace(b, input_fingerprint="f2")])
    assert refusal.code == DIFFERENT_STRUCTURE
    assert "again" in refusal.message


def test_a_stated_fingerprint_beside_an_unstated_one_cannot_be_confirmed_and_is_refused():
    a, b = _two()
    assert compare([a, replace(b, input_fingerprint="")]).code == DIFFERENT_STRUCTURE


def test_no_fingerprint_stated_anywhere_compares_as_equal():
    a, b = _two()
    assert isinstance(compare([replace(a, input_fingerprint=""), replace(b, input_fingerprint="")]), Comparison)


def test_a_drawing_beside_a_conformer_is_refused():
    """A conformer carries explicit hydrogens, so its atoms are not the drawing's."""
    a, b = _two()
    assert compare([a, replace(b, calculation_input="drawing")]).code == DIFFERENT_INPUT


def test_two_protonation_states_are_different_structures_even_on_one_drawing():
    """pH-dependent charges are keyed by their OWN microspecies, renumbered where a proton leaves."""
    a = _result("mmff94_ph_5", structure_fingerprint="species-a")
    b = _result("mmff94_ph_9", structure_fingerprint="species-b")
    assert compare([a, b]).code == DIFFERENT_STRUCTURE


def test_a_microspecies_result_beside_a_drawing_result_is_refused():
    a = _result("eem")
    b = _result("mmff94_ph_7", structure_fingerprint="species-a")
    assert compare([a, b]).code == DIFFERENT_STRUCTURE


def test_different_units_are_refused_and_named():
    a, b = _two()
    refusal = compare([a, replace(b, dataset=replace(b.dataset, units="kcal/mol"))])
    assert refusal.code == DIFFERENT_UNITS
    assert "kcal/mol" in refusal.message and "e" in refusal.message


def test_different_atoms_are_refused():
    a, b = _two()
    refusal = compare([a, replace(b, dataset=replace(b.dataset, values={0: 0.1, 1: 0.2}))])
    assert refusal.code == DIFFERENT_ATOMS


def test_a_result_compared_with_itself_is_refused():
    a = _result("eem")
    assert compare([a, _result("eem")]).code == SAME_RESULT_TWICE


def test_the_same_method_with_different_parameters_is_a_different_result():
    """A pH of 5 and a pH of 9 are two calculations even though the method's name is one."""
    a = _result("mmff94", parameters={"pH": 5.0})
    b = _result("mmff94", parameters={"pH": 9.0})
    assert isinstance(compare([a, b]), Comparison)


def test_the_text_is_tab_separated_with_units_and_the_reference_named():
    text = compare(_two()).as_text({0: "O", 1: "C", 2: "H"})
    lines = text.splitlines()
    assert lines[0] == "Units: e"
    assert lines[1].split("\t")[:2] == ["atom", "element"]
    assert lines[1].split("\t")[-1] == "delta Partial Charge (qeq) - Partial Charge (eem)"
    assert lines[2].split("\t")[:2] == ["1", "O"]
