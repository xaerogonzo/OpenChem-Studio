"""The Substance & Bonding calculator, and the refusal it unblocked.

Separate from `test_substance.py` because these are about what the app
REPORTS -- facts, their limitations, and the registry -- rather than about
what the perception concludes.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.oxidation_states import assign
from openchem.chem.substance import compute_substance_analysis

FERROCENE = "[Fe+2].[cH-]1cccc1.[cH-]1cccc1"
SODIUM_CHLORIDE = "[Na+].[Cl-]"
FOUR_IONS = "[Na+].[Cl-].[K+].[Br-]"


def _report(smiles: str):
    return compute_substance_analysis(Chem.MolFromSmiles(smiles), "uuid")


def _fact(report, label: str):
    return next((fact for fact in report.facts if fact.label == label), None)


# --- registration -----------------------------------------------------------


def test_the_calculator_is_registered_like_every_other():
    """Through the registry, never by direct import. A direct-import test
    passed once in this project while the registration was bound to a
    shadowed function."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    definition = next(
        (d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "substance_analysis"),
        None,
    )

    assert definition is not None
    assert definition.display_name == "Substance & Bonding"


def test_the_registered_calculator_runs():
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    definition = next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "substance_analysis"
    )
    report = definition.execution.compute(Chem.MolFromSmiles(SODIUM_CHLORIDE), "uuid")

    assert _fact(report, "Substance classification").display_value == "Ionic salt"


# --- what the report says ---------------------------------------------------


def test_a_refusal_is_a_result_not_a_failure():
    """`CacheState.FAILED` would paint a permanent red error row. "This
    structure does not encode which ions pair up" is a fact ABOUT the
    structure -- the same call `oxidation_states` makes for magnetite."""
    from openchem.domain.common import CacheState

    report = _report(FOUR_IONS)

    assert report.cache_state is not CacheState.FAILED
    assert _fact(report, "Substance classification") is not None


def test_the_refusal_reason_travels_as_a_limitation():
    """Not as the value. A refusal is still a classification with a caveat,
    rather than a blank where an answer should be."""
    fact = _fact(_report(FOUR_IONS), "Substance classification")

    assert fact.display_value == "Ambiguous ionic components"
    assert any("does not encode which ions" in text for text in fact.limitations)


def test_the_classification_carries_its_evidence():
    fact = _fact(_report(SODIUM_CHLORIDE), "Substance classification")

    assert fact.evidence
    assert any("stoichiometry 1:1" in text for text in fact.evidence)


def test_an_association_is_reported_as_not_being_a_bond():
    """`[Na+].[Cl-]` has no RDKit bond. The fact must say so rather than
    letting a reader take "ionic association" for an edge in the graph."""
    fact = _fact(_report(SODIUM_CHLORIDE), "Ionic association")

    assert fact.display_value == "Na+ <-> Cl-"
    assert any("not a bond" in text for text in fact.limitations)


def test_a_salt_says_its_formula_is_a_formula_unit():
    """**There is no NaCl molecule.** Which of the two this is costs one
    line and stops the number being read as the other one."""
    fact = _fact(_report(SODIUM_CHLORIDE), "Formula unit")

    assert any("not a molecule" in text for text in fact.evidence)


def test_ferrocene_reports_two_named_counts():
    """A bare "coordination number 10" invites the wrong convention."""
    report = _report(FERROCENE)

    assert _fact(report, "Ligand coordination").display_value == "2"
    assert _fact(report, "Donor-atom count").display_value == "10"
    assert _fact(report, "Coordination number") is None


def test_ferrocene_names_its_metal_oxidation_state():
    assert _fact(_report(FERROCENE), "Metal centre").display_value == "Fe(II)"


def test_identical_ligands_are_counted_not_listed_twice():
    assert _fact(_report(FERROCENE), "Ligands").display_value == "2 x eta5-Cp"


def test_no_geometry_is_claimed_without_a_conformer():
    """**Six things attached does not make something octahedral.** The
    absence is stated rather than left blank, so a reader can tell "not
    determined" from "nothing here to determine"."""
    fact = _fact(_report(FERROCENE), "Coordination geometry")

    assert "needs a 3D structure" in fact.display_value
    assert fact.value is None
    assert any("statement about angles" in text for text in fact.limitations)


def test_the_report_says_it_never_alters_the_structure():
    """The three-layer rule, on screen. Perception interprets, QuickFix
    suggests, and only the user changes the structure."""
    assert any("never alters it" in text for text in _report(SODIUM_CHLORIDE).limitations)


def test_a_metal_centre_highlights_the_metal():
    report = _report(FERROCENE)
    molecule = Chem.MolFromSmiles(FERROCENE)

    (index,) = _fact(report, "Metal centre").highlight
    assert molecule.GetAtomWithIdx(index).GetSymbol() == "Fe"


# --- the oxidation-state refusal this unblocked -----------------------------


def test_ferrocene_is_no_longer_refused_an_oxidation_state():
    """It was refused in as many words: "it is eta-5 coordination, which
    this rule cannot describe". The vendored perception knows better, so
    the answer no longer has to come from partitioning bonds."""
    result = assign(Chem.MolFromSmiles(FERROCENE))

    assert not result.refused
    metal = next(
        index
        for index in result.states
        if Chem.MolFromSmiles(FERROCENE).GetAtomWithIdx(index).GetSymbol() == "Fe"
    )
    assert result.states[metal] == 2


def test_the_delocalised_ring_carbons_are_left_unassigned():
    """The old answer gave them -2, -1, -1, -1, -1 -- each carbon's state
    depending on which one the charge was typed on. Reporting the metal
    and saying nothing about the ring is the honest half."""
    molecule = Chem.MolFromSmiles(FERROCENE)
    result = assign(molecule)

    assigned = {molecule.GetAtomWithIdx(i).GetSymbol() for i in result.states}
    assert assigned == {"Fe"}
    assert "left" in result.reason and "unassigned" in result.reason


def test_cobaltocene_balances_against_its_own_rings():
    """metal = total charge + number of Cp rings, so this is not a value
    pinned for iron."""
    result = assign(Chem.MolFromSmiles("[Co+2].[cH-]1cccc1.[cH-]1cccc1"))

    assert list(result.states.values()) == [2]


@pytest.mark.parametrize(
    "smiles,symbol,state",
    [("C[Li]", "Li", 1), ("[Mg+2].[Cl-].[Cl-]", "Mg", 2)],
)
def test_the_main_group_answers_the_rule_gets_right_are_untouched(smiles, symbol, state):
    molecule = Chem.MolFromSmiles(smiles)
    result = assign(molecule)

    assert not result.refused
    index = next(
        i for i in result.states if molecule.GetAtomWithIdx(i).GetSymbol() == symbol
    )
    assert result.states[index] == state


def test_a_metal_carbonyl_is_still_refused():
    """**The refusal is the feature.** Cr(CO)6 comes out at Cr(+6) where
    the answer is 0, and the vendored perception does not classify it, so
    nothing here should start answering."""
    carbonyl = "[Cr]([C-]#[O+])([C-]#[O+])([C-]#[O+])([C-]#[O+])([C-]#[O+])[C-]#[O+]"
    result = assign(Chem.MolFromSmiles(carbonyl))

    assert result.refused


def test_the_surviving_refusal_names_the_drawing_that_would_work():
    """The vendored perception recognises only the ionic drawing -- five
    bonded variants were built and none classified. So a structure with
    the metal bonded into its rings is still refused, and the message says
    which drawing is assignable rather than only what is wrong."""
    builder = Chem.RWMol()
    metal = builder.AddAtom(Chem.Atom(26))
    for _ in range(2):
        ring = [builder.AddAtom(Chem.Atom(6)) for _ in range(5)]
        for position in range(5):
            builder.AddBond(ring[position], ring[(position + 1) % 5], Chem.BondType.SINGLE)
            builder.AddBond(metal, ring[position], Chem.BondType.SINGLE)
    molecule = builder.GetMol()
    molecule.UpdatePropertyCache(strict=False)

    result = assign(molecule)

    assert result.refused
    assert "ion pair" in result.reason
