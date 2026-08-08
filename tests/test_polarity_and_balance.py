"""Bond polarity as Δχ, and ions that have to add up.

Both are small, and both are places where the tempting version is more
impressive and less true: a percentage of ionic character, and a general
"net charge" message where a specific one is available.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.bond_report import build_bond_report
from openchem.chem.checkers.representation import _check_charge, _check_charge_balance
from openchem.chem.structure_check import PARSED_MOLECULE, CheckContext


def _facts(smiles: str, bond_index: int) -> dict[str, object]:
    report = build_bond_report(Chem.MolFromSmiles(smiles), bond_index)
    return {fact.label: fact for fact in report.facts}


def _issues(smiles: str) -> list[str]:
    molecule = Chem.MolFromSmiles(smiles)
    molecule.UpdatePropertyCache(strict=False)
    context = CheckContext(mol=molecule, capabilities=frozenset({PARSED_MOLECULE}))
    return [
        issue.checker_id
        for issue in _check_charge(context) + _check_charge_balance(context)
    ]


def _balance(smiles: str):
    molecule = Chem.MolFromSmiles(smiles)
    molecule.UpdatePropertyCache(strict=False)
    return _check_charge_balance(
        CheckContext(mol=molecule, capabilities=frozenset({PARSED_MOLECULE}))
    )


# --- Δχ ---------------------------------------------------------------------


def test_the_difference_is_reported_as_a_difference():
    fact = _facts("CCO", 1)["Electronegativity difference"]

    assert fact.value == pytest.approx(0.89)
    assert fact.display_value == "0.89"


def test_no_percentage_of_ionic_character_is_reported():
    """**The failure this project keeps refusing.** The Pauling transform
    would render Δχ = 0.89 as "18.3% ionic", which is two digits of
    precision on a quantity nobody measured. The formula is named in the
    limitations instead, so a reader knows exactly what is withheld."""
    facts = _facts("CCO", 1)

    assert not any("%" in label for label in facts)
    assert not any("ionic character" in label.lower() for label in facts)
    assert any(
        "1 - exp(-(dX)^2/4)" in text
        for text in facts["Electronegativity difference"].limitations
    )


def test_the_difference_says_it_is_not_a_measurement_on_this_bond():
    """It is a difference of tabulated ATOMIC values. The actual charge
    separation depends on everything else attached, and a reader taking
    0.89 as a property of this bond would be wrong."""
    fact = _facts("CCO", 1)["Electronegativity difference"]

    assert any("not a property" in text for text in fact.limitations)


def test_the_difference_shows_both_values_it_came_from():
    evidence = " ".join(_facts("CCO", 1)["Electronegativity difference"].evidence)

    assert "C 2.55" in evidence
    assert "O 3.44" in evidence


@pytest.mark.parametrize(
    "smiles,index,positive,negative",
    [
        ("CCO", 1, "C2", "O3"),
        ("CF", 0, "C1", "F2"),
        # **The one that is easy to get backwards.** Lithium is the
        # electropositive end, so the CARBON is negative -- which is the
        # whole reason organolithiums do what they do.
        ("C[Li]", 0, "Li2", "C1"),
        ("[Mg]C", 0, "Mg1", "C2"),
    ],
)
def test_the_polarity_names_which_end_is_negative(smiles, index, positive, negative):
    """Worth more than the magnitude for most purposes: "which end is δ-"
    is what somebody predicting a reaction needs."""
    display = _facts(smiles, index)["Bond polarity"].display_value

    assert display == f"{positive}(d+) -> {negative}(d-)"


@pytest.mark.parametrize("smiles", ["CC", "FF", "OO"])
def test_a_homonuclear_bond_is_non_polar_for_the_stated_reason(smiles):
    """Not "below the threshold" -- the two atoms are the same element,
    which is a different and better reason."""
    facts = _facts(smiles, 0)

    assert facts["Electronegativity difference"].value == 0
    assert "same element" in facts["Bond polarity"].display_value
    # No band, because a convention has nothing to add here.
    assert "Polarity description" not in facts


def test_the_band_is_marked_as_a_convention_with_its_thresholds():
    """Textbooks put the ionic boundary at 1.7 or at 2.0. A bond near it
    is described differently by different sources, and the fact says so
    rather than sounding definitive."""
    fact = _facts("CCO", 1)["Polarity description"]

    from openchem.domain.structure_issue import Basis

    assert fact.basis is Basis.HEURISTIC
    assert "1.7" in " ".join(fact.evidence)
    assert any("convention" in text for text in fact.limitations)


def test_an_element_with_no_tabulated_value_says_so():
    """Rather than omitting the row, which reads as "this bond has no
    polarity"."""
    molecule = Chem.MolFromSmiles("*C", sanitize=False)
    molecule.UpdatePropertyCache(strict=False)
    fact = {f.label: f for f in build_bond_report(molecule, 0).facts}[
        "Electronegativity difference"
    ]

    assert fact.value is None
    assert "No accepted Pauling value" in fact.display_value


# --- charge balance ---------------------------------------------------------


@pytest.mark.parametrize(
    "smiles", ["[Na+].[Cl-]", "[Ca+2].[Cl-].[Cl-]", "[Na+].[Cl-].[K+].[Br-]"]
)
def test_balanced_salts_are_silent(smiles):
    """Including the four-ion case. It balances; WHICH ions pair with
    which is a question for `chem/substance.py`, which refuses it with a
    reason rather than treating it as an error."""
    assert _issues(smiles) == []


@pytest.mark.parametrize("smiles", ["[Na+].[Na+].[Cl-]", "[Ca+2].[Cl-]"])
def test_an_unbalanced_salt_is_flagged(smiles):
    assert _issues(smiles) == ["charge_balance"]


def test_the_message_names_the_two_sides_and_the_remainder():
    """"Net charge +1" is true and does not say what is wrong."""
    (issue,) = _balance("[Ca+2].[Cl-]")

    assert "+2 from the cations" in issue.message
    assert "-1 from the anions" in issue.message
    assert "+1" in issue.message
    assert "counter-ion" in issue.message


def test_a_lone_ion_gets_the_general_message_not_the_balance_one():
    """A single charged species is a deliberate ion, and "net charge +1"
    is the right thing to say about it."""
    assert _issues("[NH4+]") == ["molecule_charge"]


def test_the_two_checks_never_both_fire():
    """Without the hand-off both do, and the general one reads as a
    second, vaguer problem with the same structure."""
    for smiles in ("[Na+].[Na+].[Cl-]", "[NH4+]", "[Ca+2].[Cl-]", "[Na+].[Cl-]"):
        assert len(_issues(smiles)) <= 1, smiles


@pytest.mark.parametrize("smiles", ["CCO.c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O"])
def test_uncharged_structures_are_silent(smiles):
    assert _issues(smiles) == []


def test_a_neutral_fragment_beside_a_balanced_pair_is_silent():
    """A solvate. The water is not part of the charge question."""
    assert _issues("[Na+].[Cl-].O") == []
