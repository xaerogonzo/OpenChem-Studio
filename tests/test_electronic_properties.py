"""Polarizability and orbital electronegativity.

Polarizability is validated against EXPERIMENTAL molecular
polarizabilities, which is a stronger target than matching another tool.
Orbital electronegativity has no reference values available, so what is
pinned is the ORDERING, which is model-independent.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.electronic_properties import (
    JENSEN_POLARIZABILITY,
    atomic_polarizabilities,
    compute_atomic_polarizability,
    compute_orbital_electronegativity,
    compute_polarizability,
    molecular_polarizability,
    orbital_electronegativities,
)
from openchem.domain.common import CacheState


# --- Polarizability vs experiment ---------------------------------------


@pytest.mark.parametrize(
    "smiles,label,experimental",
    [
        ("c1ccccc1", "benzene", 10.32),
        ("ClC(Cl)(Cl)Cl", "CCl4", 10.51),
        ("c1ccccc1C", "toluene", 12.30),
        ("CCl", "chloromethane", 4.72),
        ("ClCCl", "dichloromethane", 6.48),
    ],
)
def test_aromatics_and_halides_land_within_a_few_percent_of_experiment(
    smiles, label, experimental
):
    value = molecular_polarizability(Chem.MolFromSmiles(smiles))
    assert value == pytest.approx(experimental, rel=0.05), label


def test_the_parameters_match_the_values_visible_in_chemaxons_screenshot():
    """Their per-atom display reads 1.36 for aromatic carbon and 0.39 for
    hydrogen, which identifies the Jensen parameter set."""
    assert JENSEN_POLARIZABILITY["C"] == pytest.approx(1.36, abs=0.04)
    assert JENSEN_POLARIZABILITY["H"] == pytest.approx(0.39, abs=0.01)


def test_saturated_hydrocarbons_are_overestimated_and_that_is_documented():
    """A purely atom-additive scheme has no hybridization dependence, so it
    cannot tell an sp3 carbon from an aromatic one. Known, stated, and
    pinned here so it is not mistaken for a regression."""
    value = molecular_polarizability(Chem.MolFromSmiles("CCCC"))
    assert value > 8.20  # experimental n-butane
    assert value == pytest.approx(9.19, rel=0.02)

    lines = compute_polarizability(Chem.MolFromSmiles("CCCC"), "mol-1").matched
    assert any("saturated hydrocarbons" in line for line in lines)


def test_miller_is_not_offered_and_the_description_says_why():
    """An implementation from recalled parameters missed benzene by +27%
    and CCl4 by -50%. Fitting the gaps to experiment would produce
    something that is not Miller's method wearing Miller's name."""
    from openchem.chem import electronic_properties

    assert not hasattr(electronic_properties, "miller_polarizability")
    assert "Miller" in electronic_properties.__doc__


def test_per_atom_contributions_sum_to_the_molecular_value():
    mol = Chem.MolFromSmiles("c1ccccc1O")
    assert sum(atomic_polarizabilities(mol).values()) == pytest.approx(
        molecular_polarizability(mol)
    )


def test_an_unparameterised_element_fails_rather_than_undercounting():
    """A partial sum would silently understate the molecule."""
    result = compute_polarizability(Chem.MolFromSmiles("[Pt]"), "mol-1")
    assert result.cache_state == CacheState.FAILED
    assert "Pt" in result.error


def test_polarizability_can_be_taken_on_the_major_microspecies():
    """Protonation genuinely changes polarizability, which is why Marvin
    offers the option."""
    acid = Chem.MolFromSmiles("CC(=O)O")
    plain = compute_polarizability(acid, "mol-1", {})
    at_ph = compute_polarizability(acid, "mol-1", {"major_microspecies": True, "pH": 12.0})

    assert at_ph.cache_state != CacheState.FAILED
    assert any("major microspecies" in line for line in at_ph.matched)
    assert not any("major microspecies" in line for line in plain.matched)


def test_atomic_polarizability_is_a_per_atom_dataset():
    dataset = compute_atomic_polarizability(Chem.MolFromSmiles("CCO"), "mol-1")
    assert dataset.units == "A^3"
    assert len(dataset.values) == Chem.AddHs(Chem.MolFromSmiles("CCO")).GetNumAtoms()


# --- Orbital electronegativity: ordering is the real check --------------


def test_oxygen_is_more_electronegative_than_its_carbon():
    values = orbital_electronegativities(Chem.MolFromSmiles("CCO"))
    mol = Chem.MolFromSmiles("CCO")
    oxygen = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "O")
    carbons = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "C"]

    assert all(values[oxygen] > values[carbon] for carbon in carbons)


def test_nitrogen_is_more_electronegative_than_ring_carbons():
    mol = Chem.MolFromSmiles("c1ccncc1")
    values = orbital_electronegativities(mol)
    nitrogen = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "N")
    carbons = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "C"]

    assert all(values[nitrogen] > values[carbon] for carbon in carbons)


def test_values_land_in_a_physically_sensible_range():
    """An earlier reimplementation of the PEOE iteration produced chi from
    -2.4 to 41 eV, which is what a broken implementation looks like."""
    for smiles in ("CCO", "c1ccccc1", "CC(=O)O", "c1ccsc1"):
        values = orbital_electronegativities(Chem.MolFromSmiles(smiles))
        assert values
        assert all(5.0 < value < 20.0 for value in values.values()), smiles


def test_hydrogens_are_excluded_by_default():
    """Matching Marvin, which shows values next to every atom except H."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    values = orbital_electronegativities(mol)
    assert all(mol.GetAtomWithIdx(index).GetSymbol() != "H" for index in values)

    with_hydrogens = orbital_electronegativities(mol, include_hydrogens=True)
    assert len(with_hydrogens) > len(values)


def test_only_the_sigma_component_is_offered():
    """Marvin also exposes a pi component. Relabelling sigma as pi would be
    worse than not offering it."""
    dataset = compute_orbital_electronegativity(Chem.MolFromSmiles("c1ccccc1"), "mol-1")
    assert "sigma" in dataset.name.lower()
    assert dataset.provenance.parameters["component"] == "sigma"


def test_the_result_states_that_absolute_values_are_parameter_dependent():
    dataset = compute_orbital_electronegativity(Chem.MolFromSmiles("CCO"), "mol-1")
    assert "ordering" in dataset.provenance.parameters["note"]


def test_electronegativity_can_be_taken_on_the_major_microspecies():
    result = compute_orbital_electronegativity(
        Chem.MolFromSmiles("CC(=O)O"), "mol-1", {"major_microspecies": True, "pH": 12.0}
    )
    assert result.cache_state != CacheState.FAILED
    assert result.values
