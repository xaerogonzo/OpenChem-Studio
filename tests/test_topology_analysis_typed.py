"""The Topology Analysis calculator carries the graph indices and ten of the counts of its report as NUMBERS (typing the values of the report calculators that carry rounded text, `docs/DERIVED_SCORES_DESIGN.md` section 3).

Until now every line of the report was text (`'6.11'`) that the project table parsed back, so a derived score over the Randic index would have changed with the decimal-places setting. The producer holds
the number, so the producer hands it over: the same `Fact`, with its `value` the number and its `display_value` still the rounded text.

**THE LINES A PERSON SEES MUST NOT MOVE**, which is what `tests/fixtures/topology_analysis_lines.json` is: every line, label, unit, basis and table-cell text of the calculator over a panel of molecules and
every way of asking (the decimal places it is given, and the ones it is not allowed to take), recorded from the code BEFORE the change. `observe` is the one function that produced the fixture and that
reads it back.

**THE TYPED NUMBERS ARE THE EIGHT GRAPH INDICES AND TEN OF THE COUNTS, AND NO OTHER FACT OF THE REPORT.** The ten are the counts that are neither an always-on descriptor under another label (atoms, rings, rotatable
bonds, stereocentres: identical on every molecule compared) nor ambiguous (the ring sizes read 0 when there is no ring, and the aromatic, aliphatic and heteroaromatic ring counts test the atoms for aromaticity, which is not
RDKit's count). An index is an `int` where it is one by construction and a plain `float` otherwise: the project file's codec refuses a NumPy float, so a number that had been left as one would fail to SAVE, which is a defect no
display would show.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.bootstrap import build_service_container
from openchem.chem.calculator_options import decimals
from openchem.chem.result_reduction import reduce_result
from openchem.domain import result_codec
from openchem.domain.calculator import CalculationRefusal

FIXTURE = Path(__file__).parent / "fixtures" / "topology_analysis_lines.json"

#: Chosen for what each exercises: a one-atom molecule (every index is zero), a chain whose Szeged index must equal its Wiener index and a ring and a cage it must exceed it on, a fused system, a molecule
#: whose two stereogenic centres are not asymmetric atoms (the module's own example), a ring of 18, a zwitterion, a salt the registry reduces to its parent, a salt it computes on its largest component (a refusal until group 3 of the refusal audit), a metal complex it refuses, and a metal ion.
PANEL = {
    "water": "O",
    "methane": "C",
    "ethanol": "CCO",
    "butane": "CCCC",
    "isobutane": "CC(C)C",
    "cyclopropane": "C1CC1",
    "benzene": "c1ccccc1",
    "pyridine": "c1ccncc1",
    "naphthalene": "c1ccc2ccccc2c1",
    "cubane": "C12C3C4C1C5C2C3C45",
    "adamantane": "C1C2CC3CC1CC(C2)C3",
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "L-alanine": "N[C@@H](C)C(=O)O",
    "trans-1,4-dimethylcyclohexane": "C[C@H]1CC[C@@H](C)CC1",
    "18-crown-6": "C1COCCOCCOCCOCCOCCO1",
    "glycine zwitterion": "[NH3+]CC(=O)[O-]",
    "metformin hydrochloride": "CN(C)C(=N)NC(N)=N.Cl",
    "sodium acetate": "CC(=O)[O-].[Na+]",
    "ionic ferrocene": "[Fe+2].c1cc[cH-]c1.c1cc[cH-]c1",
    "tetramethylsilane": "C[Si](C)(C)C",
    "copper(II)": "[Cu+2]",
}

#: Every way of asking: the default, the decimal places at both ends of their range, one past each end (clamped) and one that is not a number (falls back to the default).
ASKS = {
    "default": {},
    "0 places": {"decimal_places": 0},
    "1 place": {"decimal_places": 1},
    "8 places": {"decimal_places": 8},
    "99 places": {"decimal_places": 99},
    "not a number": {"decimal_places": "x"},
}

#: The facts whose value is the number, in the order the report lists them, and what each is (a count of pairs, paths or edges is an `int`).
INDICES = {
    "Platt index": int,
    "Randic index": float,
    "Balaban index": float,
    "Harary index": float,
    "Hyper Wiener index": int,
    "Wiener index": int,
    "Szeged index": int,
    "Wiener polarity": int,
}

#: The ten counts whose value is the number as well, each an `int` (a count of atoms, bonds or rings).
COUNTS = {
    label: int
    for label in (
        "Bond count", "Cyclomatic number", "Ring atom count", "Ring bond count", "Chain atom count", "Chain bond count", "Carbo ring count", "Hetero ring count", "Fused ring count", "Asymmetric atom count",
    )
}

#: Every typed fact of the report.
TYPED = {**INDICES, **COUNTS}


def observe(registry, smiles: str, parameters: dict) -> dict:
    """What the calculator says for one molecule asked one way, through the registry: the lines, the facts without their values, and the cells the project table would hold (text only)."""
    mol = Chem.MolFromSmiles(smiles)
    try:
        result = registry.compute("topology_analysis", mol, "uuid", dict(parameters))
    except CalculationRefusal as refusal:
        return {"refused": refusal.code}
    return {
        "state": result.cache_state.value,
        "error": result.error,
        "summary": result.error_summary,
        "inapplicable": result.inapplicable,
        "method": result.provenance.method,
        "lines": list(result.matched),
        "facts": [[f.category.value, f.label, f.display_value, f.units, f.source, f.basis.value] for f in result.facts],
        "cells": [[column.column_id, column.units, cell.text] for column, cell in reduce_result(result, "topology_analysis", "Topology Analysis")],
    }


@pytest.fixture(scope="module")
def registry():
    return build_service_container().calculator_registry


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_the_fixture_covers_every_molecule_asked_every_way(golden):
    assert set(golden) == {f"{name} | {ask}" for name in PANEL for ask in ASKS}


@pytest.mark.parametrize("ask", sorted(ASKS))
def test_no_line_label_unit_basis_or_cell_text_moved(registry, golden, ask):
    moved = {
        f"{name} | {ask}": observe(registry, smiles, ASKS[ask])
        for name, smiles in PANEL.items()
        if observe(registry, smiles, ASKS[ask]) != golden[f"{name} | {ask}"]
    }
    assert not moved, f"what a person sees moved for: {sorted(moved)}"


def _compute(registry, smiles: str, parameters: dict | None = None):
    return registry.compute("topology_analysis", Chem.MolFromSmiles(smiles), "uuid", dict(parameters or {}))


def _typed(result) -> dict:
    return {f.label: f.value for f in result.facts if not isinstance(f.value, str)}


def _completed(registry, name: str, parameters: dict | None = None):
    """The result for a panel molecule, or None where the registry declines it (a salt, a metal complex): there is no number to type."""
    try:
        result = _compute(registry, PANEL[name], parameters)
    except CalculationRefusal:
        return None
    return result if result.cache_state.value == "completed" else None


@pytest.mark.parametrize("name", sorted(PANEL))
def test_the_indices_and_ten_counts_have_their_number_typed_and_no_other_fact_does(registry, name):
    result = _completed(registry, name)
    if result is None:
        return
    typed = _typed(result)
    assert set(typed) == set(TYPED), name
    for label, kind in TYPED.items():
        assert type(typed[label]) is kind, f"{name}: {label} is {type(typed[label]).__name__}, and the project file's codec takes only the exact types int and float"
        assert math.isfinite(typed[label])
    assert all(isinstance(f.value, str) for f in result.facts if f.label not in TYPED), "the other counts are still text"


@pytest.mark.parametrize("ask", sorted(ASKS))
def test_each_line_is_its_typed_number_rounded_and_nothing_else(registry, ask):
    places = decimals(ASKS[ask])
    for name in PANEL:
        result = _completed(registry, name, ASKS[ask])
        if result is None:
            continue
        for fact in result.facts:
            if fact.label not in TYPED:
                continue
            expected = f"{fact.value:.{places}f}" if TYPED[fact.label] is float else str(fact.value)
            assert fact.display_value == expected, f"{name} | {ask}: {fact.label}"
            assert fact.units == "", "an index carries no unit"


def test_the_number_does_not_depend_on_the_decimal_places(registry):
    """The point of typing: a display setting must not move a score."""
    for name in PANEL:
        low, high = _completed(registry, name, {"decimal_places": 0}), _completed(registry, name, {"decimal_places": 8})
        if low is None:
            continue
        assert _typed(low) == _typed(high), name


def test_the_values_a_person_can_check_by_hand(registry):
    """Benzene and n-butane, the two molecules the module's header checks against published values, and the identity it validates the Szeged index by."""
    benzene, butane = _typed(_completed(registry, "benzene")), _typed(_completed(registry, "butane"))
    assert (benzene["Wiener index"], benzene["Platt index"], benzene["Wiener polarity"]) == (27, 12, 3)
    assert benzene["Randic index"] == pytest.approx(3.0)
    assert (butane["Wiener index"], butane["Platt index"], butane["Wiener polarity"]) == (10, 4, 1)
    assert butane["Randic index"] == pytest.approx(1.914, abs=5e-4)
    for tree in ("ethanol", "butane", "isobutane", "L-alanine"):
        typed = _typed(_completed(registry, tree))
        assert typed["Szeged index"] == typed["Wiener index"], f"{tree}: Szeged equals Wiener on any acyclic graph"
    for cyclic in ("benzene", "naphthalene", "cubane", "adamantane", "aspirin", "caffeine", "18-crown-6"):
        typed = _typed(_completed(registry, cyclic))
        assert typed["Szeged index"] > typed["Wiener index"], f"{cyclic}: Szeged exceeds Wiener where there is a ring of four or more atoms"


def test_szeged_does_not_exceed_wiener_where_every_ring_is_a_triangle(registry):
    """The calculator used to say Szeged "strictly exceeds" Wiener "for a cyclic graph". Measured 2026-10-15: not for cyclopropane (3 and 3), nor for any molecule here whose only rings are triangles."""
    for smiles in ("C1CC1", "C1CO1", "C1CN1", "C1CC12CC2", "C1CC1C1CC1"):
        typed = _typed(_compute(registry, smiles))
        assert typed["Szeged index"] == typed["Wiener index"], smiles
    ring_of_four = _typed(_compute(registry, "C1CCC1"))
    assert (ring_of_four["Wiener index"], ring_of_four["Szeged index"]) == (8, 16)


def test_a_single_atom_has_every_index_zero_and_is_still_a_number(registry):
    for name in ("water", "methane", "copper(II)"):
        typed = _typed(_completed(registry, name))
        assert {typed[label] for label in INDICES} == {0}, name
        assert typed["Chain atom count"] == 1 and typed["Ring atom count"] == 0 and typed["Bond count"] == 0, "the one atom is in no ring"


def test_a_salt_reads_as_its_parent_and_a_salt_with_no_parent_reads_as_its_largest_component(registry):
    """The registry hands this calculator the ChEMBL parent (it used to print RDKit's unreachable-pair sentinel as a Wiener index of 400000009), so a counter-ion adds nothing."""
    with_chloride = _typed(_completed(registry, "metformin hydrochloride"))
    assert with_chloride == _typed(_compute(registry, "CN(C)C(=N)NC(N)=N")), "the hydrochloride's indices are the free base's"
    assert max(with_chloride.values()) < 1e6
    # Group 3 of the refusal audit: a salt with no single parent is computed on its largest component (acetic acid, whose
    # indices these are), and the metal complex, whose ligand ions are not it, is still refused.
    assert _typed(_completed(registry, "sodium acetate")) == _typed(_compute(registry, "CC(=O)O"))
    assert _completed(registry, "ionic ferrocene") is None


def test_an_index_is_of_the_graph_without_hydrogens_so_a_conformer_is_a_different_number(registry):
    """Why a score reads the DRAWING's result and never a conformer's (`calculator.py`: eight calculators change only by the explicit hydrogens): ethanol is 3 atoms as drawn and 9 as a conformer."""
    drawn = _typed(_compute(registry, "CCO"))
    embedded = _typed(registry.compute("topology_analysis", Chem.AddHs(Chem.MolFromSmiles("CCO")), "uuid", {}))
    assert drawn["Wiener index"] == 4 and embedded["Wiener index"] != drawn["Wiener index"]


def test_the_project_table_cell_holds_the_exact_number_and_shows_the_rounded_text(registry):
    for places, text in ((None, "6.11"), (0, "6"), (8, "6.10906091")):
        result = _compute(registry, PANEL["aspirin"], {} if places is None else {"decimal_places": places})
        [(column, cell)] = [(c, k) for c, k in reduce_result(result, "topology_analysis", "Topology Analysis") if c.label == "Randic index"]
        assert column.column_id == "calculator:topology_analysis:Randic index" and column.units == "" and column.numeric
        assert cell.text == text
        assert cell.value == _typed(result)["Randic index"], "the exact number, not the rounded one"
        assert places in (None, 8) or cell.value != float(cell.text)


def test_a_typed_report_is_saved_and_reopened_whole(registry):
    """The project file's codec takes only the exact types int, float and str: a NumPy float left in a fact would fail the SAVE, which no display shows."""
    result = _compute(registry, PANEL["aspirin"])
    restored = result_codec.decode(json.loads(json.dumps(result_codec.encode(result))))
    assert restored == result and _typed(restored) == _typed(result)
    assert [type(v) for v in _typed(restored).values()] == [type(v) for v in _typed(result).values()]


# --- approved as score outputs ---------------------------------------------------------------------------------------------------------


def _approved_topology() -> dict:
    from openchem.domain.score_outputs import APPROVED

    prefix = "calculator:topology_analysis:"
    return {entry.output_id[len(prefix):]: entry for entry in APPROVED if entry.output_id.startswith(prefix)}


def test_exactly_the_typed_facts_are_approved_each_dimensionless_and_each_with_an_endpoint_of_its_own():
    approved = _approved_topology()
    assert list(approved) == sorted(TYPED), "the table is sorted by id"
    assert all(entry.unit == "1" and entry.carried_as == "" for entry in approved.values())
    assert len({entry.endpoint for entry in approved.values()}) == len(TYPED) == 18, "eighteen different quantities: none of them is a consensus of another"


def test_the_counts_that_are_duplicates_or_ambiguous_are_not_approved():
    from openchem.domain.score_outputs import approved_output

    for label in (
        "Atom count", "Ring count", "Rotatable bond count", "Chiral center count",  # the always-on descriptors under other labels
        "Largest ring size", "Smallest ring size",  # 0 when there is no ring
        "Aromatic ring count", "Aliphatic ring count", "Heteroaromatic ring count",  # atom-based aromaticity, which is not RDKit's count
    ):
        assert approved_output(f"calculator:topology_analysis:{label}") is None, label


def test_the_eight_indices_and_the_ten_counts_can_each_be_named_in_one_formula():
    from openchem.domain.score_outputs import check_inputs

    for labels in (list(INDICES), list(COUNTS)):
        approved = _approved_topology()
        units = check_inputs([(f"i{n}", approved[label].output_id) for n, label in enumerate(labels)])
        assert len(units) == len(labels)


@pytest.mark.parametrize("name", ["aspirin", "caffeine", "benzene", "cubane", "18-crown-6"])
def test_a_score_reads_the_same_number_whatever_the_decimal_places(registry, name):
    from openchem.domain.score_outputs import accept_value

    for label, entry in _approved_topology().items():
        read = []
        for places in (0, 1, 8):
            [fact] = [f for f in _completed(registry, name, {"decimal_places": places}).facts if f.label == label]
            read.append(accept_value(entry, fact.value, fact.units))
        assert read[0] == read[1] == read[2], f"{name}: {label} moved with the setting: {read}"
        assert type(read[0]) is float


# --- the ten counts: what they are, and why the other counts are left out ----------------------------------------------------------------------

#: Worked out by hand from the structures, not read off the calculator: a ring of atoms and the bonds between them, and what is left outside.
COUNT_VALUES = {
    "benzene": {"Bond count": 6, "Cyclomatic number": 1, "Ring atom count": 6, "Ring bond count": 6, "Chain atom count": 0, "Chain bond count": 0, "Carbo ring count": 1, "Hetero ring count": 0, "Fused ring count": 0, "Asymmetric atom count": 0},
    "naphthalene": {"Bond count": 11, "Cyclomatic number": 2, "Ring atom count": 10, "Ring bond count": 11, "Chain atom count": 0, "Chain bond count": 0, "Carbo ring count": 2, "Hetero ring count": 0, "Fused ring count": 2, "Asymmetric atom count": 0},
    "aspirin": {"Bond count": 13, "Cyclomatic number": 1, "Ring atom count": 6, "Ring bond count": 6, "Chain atom count": 7, "Chain bond count": 7, "Carbo ring count": 1, "Hetero ring count": 0, "Fused ring count": 0, "Asymmetric atom count": 0},
    "caffeine": {"Bond count": 15, "Cyclomatic number": 2, "Ring atom count": 9, "Ring bond count": 10, "Chain atom count": 5, "Chain bond count": 5, "Carbo ring count": 0, "Hetero ring count": 2, "Fused ring count": 2, "Asymmetric atom count": 0},
    "18-crown-6": {"Bond count": 18, "Cyclomatic number": 1, "Ring atom count": 18, "Ring bond count": 18, "Chain atom count": 0, "Chain bond count": 0, "Carbo ring count": 0, "Hetero ring count": 1, "Fused ring count": 0, "Asymmetric atom count": 0},
    "L-alanine": {"Bond count": 5, "Cyclomatic number": 0, "Ring atom count": 0, "Ring bond count": 0, "Chain atom count": 6, "Chain bond count": 5, "Carbo ring count": 0, "Hetero ring count": 0, "Fused ring count": 0, "Asymmetric atom count": 1},
    "cubane": {"Bond count": 12, "Cyclomatic number": 5, "Ring atom count": 8, "Ring bond count": 12, "Chain atom count": 0, "Chain bond count": 0, "Carbo ring count": 6, "Hetero ring count": 0, "Fused ring count": 6, "Asymmetric atom count": 0},
}


@pytest.mark.parametrize("name", sorted(COUNT_VALUES))
def test_the_counts_a_person_can_check_by_hand(registry, name):
    typed = _typed(_completed(registry, name))
    assert {label: typed[label] for label in COUNTS} == COUNT_VALUES[name]


def test_the_counts_obey_the_identities_that_define_them_on_every_molecule_of_the_panel(registry):
    for name in PANEL:
        result = _completed(registry, name)
        if result is None:
            continue
        typed = _typed(result)
        text = {f.label: int(f.display_value) for f in result.facts if f.label in ("Atom count", "Ring count")}
        assert typed["Ring atom count"] + typed["Chain atom count"] == text["Atom count"], name
        assert typed["Ring bond count"] + typed["Chain bond count"] == typed["Bond count"], name
        assert typed["Carbo ring count"] + typed["Hetero ring count"] == text["Ring count"], name
        assert typed["Cyclomatic number"] == typed["Bond count"] - text["Atom count"] + 1, f"{name}: one component, the parent"
        assert typed["Fused ring count"] <= text["Ring count"], name


def _always_on(name: str) -> dict:
    from openchem.chem.descriptor_providers import RDKitDescriptorProvider

    return {value.descriptor_id: value.value for value in RDKitDescriptorProvider().compute(Chem.MolFromSmiles(PANEL[name]), "uuid")}


def _single_component_names() -> list[str]:
    return [name for name, smiles in PANEL.items() if "." not in smiles]


def test_the_four_counts_left_out_are_the_always_on_descriptors_under_other_labels(registry):
    """Why they are not approved: identical on every single-component molecule of the panel, so a score gains nothing and has to run this calculator to read what is always there."""
    duplicates = {"Atom count": "heavy_atom_count", "Ring count": "ring_count", "Rotatable bond count": "num_rotatable_bonds", "Chiral center count": "num_stereocenters"}
    for name in _single_component_names():
        result = _completed(registry, name)
        if result is None:
            continue
        text = {f.label: float(f.display_value) for f in result.facts if f.label in duplicates}
        always_on = _always_on(name)
        for label, descriptor in duplicates.items():
            assert text[label] == float(always_on[descriptor]), f"{name}: {label} against {descriptor}"


def test_the_cyclomatic_number_is_not_the_ring_count_on_a_cage_so_it_is_offered(registry):
    """RDKit lists cubane's six faces as six rings and the cyclomatic number is the five that are independent: the two are different quantities, and only the second is not an always-on descriptor."""
    for name, (cyclomatic, rings) in {"cubane": (5, 6), "adamantane": (3, 4), "benzene": (1, 1)}.items():
        result = _completed(registry, name)
        assert (_typed(result)["Cyclomatic number"], int([f.display_value for f in result.facts if f.label == "Ring count"][0])) == (cyclomatic, rings), name


def test_the_asymmetric_atom_count_is_not_the_stereocentre_descriptor_on_a_cage_or_a_symmetric_ring(registry):
    """Four different substituents (the legacy rule) against the always-on stereocentre count: they differ where a centre is stereogenic without being asymmetric, as the module says. So this one is offered."""
    differ = {}
    for name in _single_component_names():
        result = _completed(registry, name)
        if result is None:
            continue
        counts = (_typed(result)["Asymmetric atom count"], int(_always_on(name)["num_stereocenters"]))
        if counts[0] != counts[1]:
            differ[name] = counts
    assert differ == {"cubane": (0, 8), "adamantane": (0, 4), "trans-1,4-dimethylcyclohexane": (0, 2)}


def test_the_ring_sizes_read_zero_without_a_ring_which_is_why_they_are_left_out(registry):
    for name in ("water", "butane", "ethanol"):
        result = _completed(registry, name)
        shown = {f.label: f.display_value for f in result.facts if f.label in ("Largest ring size", "Smallest ring size")}
        assert shown == {"Largest ring size": "0", "Smallest ring size": "0"}, name
