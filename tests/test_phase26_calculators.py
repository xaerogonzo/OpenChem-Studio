"""Phase 26 calculator batch.

Reference values here are either MarvinSketch's own published output or
textbook graph-theory values, not this implementation's first run -- a
test that only pins current behaviour would have happily locked in the
bugs found while building these (see the interaction-analysis cases).
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.elemental_analysis import (
    compute_elemental_analysis,
    dot_disconnected_formula,
    element_composition,
)
from openchem.chem.geometry_analysis import (
    NoConformerError,
    compute_geometry_analysis,
    dihedral_angle,
    force_field_energies,
    molecular_radii,
)
from openchem.chem.interaction_analysis import compute_interaction_analysis, find_interactions
from openchem.chem.substructure import (
    COMMON_PATTERNS,
    InvalidSmartsError,
    compute_substructure_search,
    find_matches,
)
from openchem.chem.surface_analysis import compute_surface_analysis, per_atom_sasa, surface_areas
from openchem.chem.topology_analysis import (
    compute_topology_analysis,
    cyclomatic_number,
    platt_index,
    randic_index,
    ring_counts,
    stereo_counts,
    wiener_index,
    wiener_polarity,
)
from openchem.domain.common import CacheState


def _embed(smiles: str, seed: int = 11) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


# --- Elemental analysis -------------------------------------------------
# Reference: MarvinSketch's own Elemental Analysis window for tyramine
# hydrochloride, the molecule in its documentation screenshot.

TYRAMINE_HCL = "NCCc1ccc(O)cc1.Cl"


def test_elemental_composition_matches_marvin_for_tyramine_hydrochloride():
    composition = element_composition(Chem.AddHs(Chem.MolFromSmiles(TYRAMINE_HCL)))

    assert composition["C"] == pytest.approx(55.34, abs=0.01)
    assert composition["H"] == pytest.approx(6.97, abs=0.01)
    assert composition["Cl"] == pytest.approx(20.42, abs=0.01)
    assert composition["N"] == pytest.approx(8.07, abs=0.01)
    assert composition["O"] == pytest.approx(9.21, abs=0.01)


def test_elemental_analysis_reports_marvins_formula_exact_mass_and_atom_count():
    lines = compute_elemental_analysis(Chem.MolFromSmiles(TYRAMINE_HCL), "mol-1").matched
    joined = "\n".join(lines)

    assert "Formula: C8H12ClNO" in joined
    assert "Exact mass: 173.060742" in joined  # Marvin: 173.060741718
    assert "Atom count: 23" in joined


def test_composition_sums_to_one_hundred_percent():
    composition = element_composition(Chem.AddHs(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")))
    assert sum(composition.values()) == pytest.approx(100.0, abs=1e-6)


def test_dot_disconnected_formula_splits_a_salt_but_not_a_single_fragment():
    salt = Chem.AddHs(Chem.MolFromSmiles(TYRAMINE_HCL))
    single = Chem.AddHs(Chem.MolFromSmiles("CCO"))

    assert "." in dot_disconnected_formula(salt)
    assert "." not in dot_disconnected_formula(single)


def test_elemental_analysis_omits_the_dot_formula_when_it_says_nothing_new():
    """Repeating the plain formula under a second heading is noise."""
    lines = compute_elemental_analysis(Chem.MolFromSmiles("CCO"), "mol-1").matched
    assert not any("Dot-disconnected" in line for line in lines)


# --- Topology -----------------------------------------------------------
# Reference: textbook values for these two molecules.


@pytest.mark.parametrize(
    "smiles,label,wiener,randic,platt,polarity",
    [
        ("c1ccccc1", "benzene", 27, 3.000, 12, 3),
        ("CCCC", "n-butane", 10, 1.914, 4, 1),
    ],
)
def test_topology_indices_match_textbook_values(smiles, label, wiener, randic, platt, polarity):
    mol = Chem.MolFromSmiles(smiles)

    assert wiener_index(mol) == wiener, label
    assert randic_index(mol) == pytest.approx(randic, abs=0.001), label
    assert platt_index(mol) == platt, label
    assert wiener_polarity(mol) == polarity, label


def test_cyclomatic_number_counts_independent_rings():
    assert cyclomatic_number(Chem.MolFromSmiles("CCCC")) == 0
    assert cyclomatic_number(Chem.MolFromSmiles("c1ccccc1")) == 1
    assert cyclomatic_number(Chem.MolFromSmiles("c1ccc2[nH]ccc2c1")) == 2  # indole


def test_ring_counts_classify_a_fused_heteroaromatic():
    counts = ring_counts(Chem.MolFromSmiles("c1ccc2[nH]ccc2c1"))  # indole

    assert counts["ring_count"] == 2
    assert counts["aromatic_ring_count"] == 2
    assert counts["carbo_ring_count"] == 1
    assert counts["hetero_ring_count"] == 1
    assert counts["heteroaromatic_ring_count"] == 1
    assert counts["fused_ring_count"] == 2
    assert counts["largest_ring_size"] == 6
    assert counts["smallest_ring_size"] == 5


def test_chiral_centres_and_asymmetric_atoms_are_not_the_same_thing():
    """Marvin's own documentation cites this exact case: 1,4-dimethyl-
    cyclohexane has two stereogenic centres and no asymmetric atoms."""
    counts = stereo_counts(Chem.MolFromSmiles("CC1CCC(C)CC1"))

    assert counts["chiral_center_count"] == 2
    assert counts["asymmetric_atom_count"] == 0


def test_szeged_and_steric_effect_index_are_deliberately_absent():
    """Both appear in Marvin's Topology Analysis and are NOT implemented:
    their literature definitions conflict and no reference value was found
    to validate against. This test exists so re-adding them is a conscious
    decision rather than an accident."""
    joined = "\n".join(compute_topology_analysis(Chem.MolFromSmiles("CCO"), "mol-1").matched).lower()

    assert "szeged" not in joined
    assert "steric" not in joined


# --- Geometry -----------------------------------------------------------


def test_geometry_needs_a_real_conformer():
    result = compute_geometry_analysis(Chem.MolFromSmiles("CCCC"), "mol-1")

    assert result.cache_state == CacheState.FAILED
    assert "conformer" in result.error.lower()


def test_anti_butane_dihedral_is_one_hundred_eighty_degrees():
    assert dihedral_angle(_embed("CCCC", seed=3), 0, 1, 2, 3) == pytest.approx(180.0, abs=1.0)


def test_molecular_radii_are_ordered_and_positive():
    radii = molecular_radii(_embed("CCCCCCCC"))

    assert 0 < radii["min_radius"] <= radii["mean_radius"] <= radii["max_radius"]


def test_geometry_reports_mmff_and_uff_and_never_calls_them_dreiding():
    """RDKit has no Dreiding. Reporting MMFF94/UFF under Marvin's label
    would produce a number that looks authoritative and cross-references
    to nothing."""
    lines = compute_geometry_analysis(_embed("CCCC", seed=3), "mol-1").matched
    joined = "\n".join(lines)

    assert "MMFF94 energy" in joined
    assert "UFF energy" in joined
    assert "not Dreiding" in joined


def test_force_field_energies_degrade_to_none_for_unparameterised_elements():
    """An exotic element must yield None rather than crashing, and must not
    silently substitute the other force field's number -- they are on
    different scales."""
    xenon = Chem.AddHs(Chem.MolFromSmiles("[Xe]"))
    AllChem.EmbedMolecule(xenon, randomSeed=1)

    assert force_field_energies(xenon) == {"mmff94": None, "uff": None}


# --- Surface areas ------------------------------------------------------


def test_surface_area_splits_sum_to_the_total():
    areas = surface_areas(_embed("CCO"))

    assert areas["asa_hydrophobic"] + areas["asa_polar"] == pytest.approx(areas["asa"], rel=1e-9)


def test_per_atom_sasa_covers_every_atom_and_sums_to_the_total():
    mol = _embed("CCO")
    values = per_atom_sasa(mol)

    assert len(values) == mol.GetNumAtoms()
    assert sum(values.values()) == pytest.approx(surface_areas(mol)["asa"], rel=1e-6)


def test_surface_analysis_needs_a_conformer():
    result = compute_surface_analysis(Chem.MolFromSmiles("CCO"), "mol-1")

    assert result.cache_state == CacheState.FAILED


def test_a_larger_molecule_has_a_larger_accessible_surface():
    assert surface_areas(_embed("CCCCCCCC"))["asa"] > surface_areas(_embed("CCO"))["asa"]


# --- Substructure search ------------------------------------------------


def test_aspirin_matches_acid_and_ester_but_not_free_phenol():
    """Aspirin's phenol oxygen is esterified, so a free-phenol pattern must
    NOT match -- the same case the Phase 20 functional-group work used."""
    aspirin = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")

    assert len(find_matches(aspirin, COMMON_PATTERNS["Carboxylic acid"])) == 1
    assert len(find_matches(aspirin, COMMON_PATTERNS["Ester"])) == 1
    assert len(find_matches(aspirin, COMMON_PATTERNS["Phenol"])) == 0


def test_invalid_smarts_is_reported_not_silently_zero_matches():
    """A silent zero would be indistinguishable from a valid pattern that
    simply doesn't match."""
    with pytest.raises(InvalidSmartsError):
        find_matches(Chem.MolFromSmiles("CCO"), "[[[not smarts")

    result = compute_substructure_search(Chem.MolFromSmiles("CCO"), "mol-1", {"smarts": "[[[not smarts"})
    assert result.cache_state == CacheState.FAILED


def test_substructure_values_cover_every_atom_not_just_the_hits():
    """A dataset holding only the matches would collapse the colour scale's
    domain to a single value and render every hit mid-scale grey."""
    aspirin = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
    result = compute_substructure_search(aspirin, "mol-1", {"smarts": COMMON_PATTERNS["Carboxylic acid"]})

    assert len(result.values) == aspirin.GetNumAtoms()
    assert set(result.values.values()) == {0.0, 1.0}


def test_custom_smarts_overrides_the_chosen_common_pattern():
    aspirin = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
    result = compute_substructure_search(
        aspirin, "mol-1", {"pattern": "Phenol", "smarts": COMMON_PATTERNS["Carboxylic acid"]}
    )

    assert sum(1 for v in result.values.values() if v) == 3  # the acid group, not the phenol


def test_no_pattern_at_all_asks_for_one():
    result = compute_substructure_search(Chem.MolFromSmiles("CCO"), "mol-1", {})
    assert result.cache_state == CacheState.FAILED


# --- Interaction analysis -----------------------------------------------
# These reference real intramolecular chemistry, and two of them are
# regression tests for bugs found by probing real geometries.


def test_salicylic_acid_intramolecular_hydrogen_bond_is_found():
    """The textbook 6-membered-ring intramolecular H-bond."""
    found = find_interactions(_embed("OC(=O)c1ccccc1O"))
    assert len(found["hydrogen_bonds"]) >= 1


def test_a_hydrogen_bond_is_never_also_reported_as_a_steric_clash():
    """An H-bond is SHORTER than the summed van der Waals radii -- that
    closeness is the interaction. Before this was fixed, salicylic acid's
    2.56 A bond appeared in both lists, which would train a user to ignore
    the clash list entirely."""
    found = find_interactions(_embed("OC(=O)c1ccccc1O"))
    bonded_pairs = {entry["atoms"] for entry in found["hydrogen_bonds"]}
    clash_pairs = {entry["atoms"] for entry in found["clashes"]}

    assert not (bonded_pairs & clash_pairs)


def test_a_five_membered_ring_hydrogen_bond_is_not_dropped():
    """Ethylene glycol's O...O sit 3 bonds apart at ~2.8 A -- a real 5-ring
    intramolecular hydrogen bond. A blanket minimum separation of 4 bonds
    silently discarded it, which is why the threshold is per-interaction."""
    assert len(find_interactions(_embed("OCCO"))["hydrogen_bonds"]) >= 1


def test_geminal_oxygens_are_not_a_hydrogen_bond():
    """A carboxyl group's two oxygens sit 2 bonds apart at ~2.2 A. That is
    bond geometry, not a contact, and must never be reported as either an
    H-bond or a clash."""
    found = find_interactions(_embed("CC(=O)O"))

    assert found["hydrogen_bonds"] == []
    assert found["clashes"] == []


def test_an_alkane_has_no_hydrogen_bonds():
    assert find_interactions(_embed("CCCCCC"))["hydrogen_bonds"] == []


def test_a_zwitterion_shows_a_salt_bridge():
    assert len(find_interactions(_embed("[NH3+]CCCC([O-])=O"))["salt_bridges"]) >= 1


def test_pi_stacking_is_conformer_dependent():
    """Folded bibenzyl conformers stack; extended ones don't. Detecting it
    in every conformer would mean the geometry check isn't working."""
    mol = Chem.AddHs(Chem.MolFromSmiles("c1ccc(cc1)CCc1ccccc1"))
    AllChem.EmbedMultipleConfs(mol, numConfs=30, randomSeed=5)
    AllChem.MMFFOptimizeMoleculeConfs(mol)

    stacked = sum(
        1
        for conf_id in range(mol.GetNumConformers())
        if find_interactions(Chem.Mol(mol, confId=conf_id))["pi_stacking"]
    )

    assert 0 < stacked < mol.GetNumConformers()


def test_no_interactions_reads_as_a_finding_not_a_failure():
    result = compute_interaction_analysis(_embed("CC"), "mol-1")

    assert result.cache_state != CacheState.FAILED
    assert "No intramolecular interactions" in result.matched[0]


def test_interaction_analysis_needs_a_conformer():
    result = compute_interaction_analysis(Chem.MolFromSmiles("CCO"), "mol-1")
    assert result.cache_state == CacheState.FAILED
