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


# --- the pi component ------------------------------------------------------
#
# `chi_pi = a + b*q + c*q^2` on Marsili & Gasteiger 1980's Table I, at the
# converged PEOE SIGMA charge -- the paper's own "starting POE" values. What
# is NOT here is a pi-charge iteration; docs/VALIDATION.md records three
# reconstructions of it that were measured and refused.


def _pi(smiles: str) -> dict[int, float]:
    from openchem.chem.electronic_properties import pi_orbital_electronegativities

    return pi_orbital_electronegativities(Chem.MolFromSmiles(smiles))


def test_the_shipped_pi_table_is_the_papers_table():
    """Transcription, against the 300-dpi render rather than the text layer.

    THE OCR LAYER OF THAT SCAN IS WRONG IN ONE PLACE and this is the value:
    it reads 11.13 for O-sp2's b where the page prints 11.73. One of 33
    numbers -- the same one-in-fifty-three the Drago E/C audit found -- and
    a validation that averages would never have seen it.
    """
    from openchem.chem.electronic_properties import pi_parameter_table

    table = pi_parameter_table()
    assert len(table) == 11
    assert (table["O-sp2"]["a"], table["O-sp2"]["b"], table["O-sp2"]["c"]) == (10.09, 11.73, 2.87)
    assert (table["N-sp3"]["a"], table["N-sp3"]["b"], table["N-sp3"]["c"]) == (4.54, 11.86, 7.32)
    assert (table["C-sp2"]["a"], table["C-sp2"]["b"], table["C-sp2"]["c"]) == (5.60, 8.93, 2.94)
    # "J (electron pair)" is the paper's German notation for iodine.
    assert table["I"]["paper_row"].startswith("J ")
    assert table["I"]["element"] == "I"


def test_the_two_rows_for_one_element_are_far_apart():
    """Why picking the wrong ROLE is not a rounding difference.

    Nitrogen contributing one electron to a pi bond and nitrogen donating a
    lone pair are different rows -- 7.95 against 4.54 -- so `_pi_role` is
    load-bearing rather than a tidy-up. This asserts the SPREAD, so the
    claim survives a future edition changing the values.
    """
    from openchem.chem.electronic_properties import pi_parameter_table

    table = pi_parameter_table()
    for element, pz, pair in (("N", "N-sp2", "N-sp3"), ("O", "O-sp2", "O-sp3")):
        assert table[pz]["element"] == table[pair]["element"] == element
        assert abs(table[pz]["a"] - table[pair]["a"]) > 2.0


def test_a_symmetric_ring_gives_one_value_to_every_carbon():
    values = _pi("c1ccccc1")
    assert len(values) == 6
    assert max(values.values()) - min(values.values()) == pytest.approx(0.0, abs=1e-9)


def test_a_substituent_is_felt_at_the_ortho_and_para_positions():
    """The ORDERING, which is what this quantity is for.

    Phenol: ipso > ortho > meta, and the ring keeps its mirror symmetry.
    That is the substituent effect these parameters carry, and it is
    model-independent in the way the file docstring means.
    """
    values = _pi("Oc1ccccc1")          # O=0, ipso=1, ortho=2/6, meta=3/5, para=4
    assert values[1] > values[2] > values[3]
    assert values[2] == pytest.approx(values[6], abs=1e-9)
    assert values[3] == pytest.approx(values[5], abs=1e-9)


def test_a_lone_pair_donor_falls_BELOW_the_ring_it_donates_into():
    """THE PAPER'S OWN CENTRAL POINT, asserted rather than described.

    [source:marsili1980] p 606: with neutral-state values "no transfer from
    the heteroatom to the double bond would be possible ... Generally,
    whenever a +M effect is expected none can be predicted". Inserting the
    SIGMA charge is the fix, and the test of it is that the donor's POE now
    sits below the vicinal carbon's. If this ever inverts, the +M direction
    inverts with it and every value here means the opposite thing.
    """
    for smiles, donor, ipso in (("Oc1ccccc1", 0, 1), ("Nc1ccccc1", 0, 1)):
        values = _pi(smiles)
        assert values[donor] < values[ipso], smiles


def test_pyridines_nitrogen_comes_out_BELOW_its_carbons_and_that_is_the_model():
    """Counter-intuitive, correct, and asserted ON PURPOSE.

    Bare electronegativity puts nitrogen well above carbon. Here the
    pyridine nitrogen is sigma-NEGATIVE, and the paper's mechanism is that
    "the excess negative charge will cause an additional screening of the
    pz(B) orbital which thereby LOWERS the POE of this orbital" -- so it
    lands below its sigma-positive neighbours.

    Same shape as `test_koopmans_inverts_ammonia_against_phosphine`: if a
    future change makes this agree with bare electronegativity, the
    sigma-dependence has been lost and this fails naming it.
    """
    values = _pi("c1ccncc1")           # nitrogen is atom 3
    assert values[3] < values[2]
    assert values[3] < values[4]


def test_an_atom_outside_the_pi_system_is_ABSENT_not_zero():
    """Zero is a value on this scale, and every real one is positive."""
    assert _pi("CCO") == {}
    ethylbenzene = _pi("CCc1ccccc1")
    assert 0 not in ethylbenzene and 1 not in ethylbenzene   # the ethyl carbons
    assert len(ethylbenzene) == 6                            # the ring, and only the ring


def test_asking_for_SIGMA_still_covers_the_whole_molecule():
    """THE LOAD-BEARING HALF of the pair above.

    "The dataset covers pi atoms only" is satisfied by an implementation
    that has quietly narrowed the SIGMA dataset too, which would be a
    silent regression in the component that has shipped all along.
    """
    ethanol = compute_orbital_electronegativity(Chem.MolFromSmiles("CCO"), "u")
    assert len(ethanol.values) == 3
    assert ethanol.cache_state is not CacheState.FAILED


def test_an_unknown_component_label_falls_back_and_says_which_ran():
    """Both halves, and the second is the one that matters.

    A stored project written by a future version must stay openable, so an
    unrecognised label falls back rather than raising. But sigma and pi are
    DIFFERENT QUANTITIES on different parameter sets, so a fallback nobody
    can see would silently change what a stored number means -- the
    recorded component is what stops that. Same shape as
    `test_an_unknown_method_label_falls_back_and_says_which_ran`.
    """
    mol = Chem.MolFromSmiles("Oc1ccccc1")
    fell_back = compute_orbital_electronegativity(mol, "u", {"component": "Pi (SD-POE) v2"})
    sigma = compute_orbital_electronegativity(mol, "u", {"component": "Sigma (PEOE)"})

    assert fell_back.values == sigma.values
    assert fell_back.provenance.parameters["component"] == "sigma"
    assert fell_back.method == "gasteiger_marsili"

    # AND THE OTHER DIRECTION, which is the half that discriminates. A
    # mutation hardcoding `"component": "sigma"` in the provenance SURVIVED
    # the assertions above -- of course it did: the fallback case really is
    # sigma. Only a successful PI run recording "pi" can tell a field that
    # reports what ran from one that always says the same thing.
    ran_pi = compute_orbital_electronegativity(mol, "u", {"component": "Pi (SD-POE)"})
    assert ran_pi.provenance.parameters["component"] == "pi"
    assert ran_pi.method == "marsili_sd_poe"


def test_the_two_components_are_not_the_same_numbers_under_two_labels():
    """The refusal this feature exists to avoid becoming.

    `orbital_electronegativity` used to say a pi value "would require a
    separate pi-charge iteration, which OpenChem does not run", because
    relabelling the sigma one would be worse than offering nothing. So the
    thing to assert is that they genuinely differ.
    """
    mol = Chem.MolFromSmiles("Oc1ccccc1")
    sigma = compute_orbital_electronegativity(mol, "u", {"component": "Sigma (PEOE)"})
    pi = compute_orbital_electronegativity(mol, "u", {"component": "Pi (SD-POE)"})

    assert sigma.method != pi.method
    shared = set(sigma.values) & set(pi.values)
    assert shared, "nothing to compare"
    assert all(abs(sigma.values[i] - pi.values[i]) > 0.5 for i in shared)


def test_a_molecule_with_no_pi_system_refuses_rather_than_returning_nothing():
    result = compute_orbital_electronegativity(
        Chem.MolFromSmiles("CCO"), "u", {"component": "Pi (SD-POE)"}
    )
    assert result.cache_state is CacheState.FAILED
    assert "pi system" in (result.error or "")
    assert result.values == {}


def test_include_hydrogens_does_nothing_for_pi_and_the_label_says_so():
    """A tick box that silently does nothing is worse than an absent one.

    `CalculatorSettingsDialog` builds one widget per `CalculatorParameter`
    with no conditional visibility, so "Include hydrogens" is on screen for
    the pi component too -- where hydrogen has no pi orbital and no row in
    Marsili & Gasteiger's Table I. It is IGNORED there, which is correct;
    what would not be correct is leaving the label implying otherwise.

    Found by grabbing the real settings dialog, which is the route a user
    takes and the one the `calculator` drive step bypasses by passing
    parameters straight through.
    """
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    # EXPLICIT hydrogens, or the control below cannot discriminate: a
    # molecule built straight from SMILES carries implicit ones, so
    # `include_hydrogens=True` has nothing to include and BOTH arms return
    # 7 values. Caught by this test's own control on its first run.
    mol = Chem.AddHs(Chem.MolFromSmiles("Oc1ccccc1"))
    off = compute_orbital_electronegativity(
        mol, "u", {"component": "Pi (SD-POE)", "include_hydrogens": False}
    )
    on = compute_orbital_electronegativity(
        mol, "u", {"component": "Pi (SD-POE)", "include_hydrogens": True}
    )
    assert on.values == off.values, "the pi branch must ignore include_hydrogens"

    # ... and the SIGMA arm is the control: there the tick really does
    # something, so "ignored everywhere" would satisfy the line above and
    # be a different bug.
    sigma_off = compute_orbital_electronegativity(
        mol, "u", {"component": "Sigma (PEOE)", "include_hydrogens": False}
    )
    sigma_on = compute_orbital_electronegativity(
        mol, "u", {"component": "Sigma (PEOE)", "include_hydrogens": True}
    )
    assert len(sigma_on.values) > len(sigma_off.values)

    definition = next(
        c for c in CALCULATOR_DEFINITIONS if c.calculator_id == "orbital_electronegativity"
    )
    label = next(p.label for p in definition.parameters if p.name == "include_hydrogens")
    assert "sigma" in label.lower(), (
        f"the label {label!r} does not say the tick applies to sigma only, so a "
        "user picking the pi component sees a control that does nothing"
    )
