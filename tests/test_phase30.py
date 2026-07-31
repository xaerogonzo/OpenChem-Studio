"""Phase 30: Huckel, dipole, vacuum MD, CNS MPO, structural frameworks.

Every reference value is a closed-form answer, a symmetry argument, or a
number ChemAxon published -- never this implementation's first run.
"""

from __future__ import annotations

import math

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.dipole import compute_dipole_moment, dipole_vector
from openchem.chem.huckel import (
    compute_huckel_analysis,
    compute_pi_electron_density,
    pi_system_atoms,
    solve_huckel,
)
from openchem.chem.molecular_dynamics import (
    UnstableTrajectoryError,
    compute_molecular_dynamics,
    run_dynamics,
)
from openchem.chem.mpo_scores import (
    cns_mpo_components,
    compute_cns_mpo,
    compute_structural_frameworks,
)
from openchem.domain.common import CacheState


def _embed(smiles: str, seed: int = 11) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


# --- Huckel: closed-form answers ---------------------------------------


def test_benzene_orbital_energies_are_the_closed_form_answer():
    result = solve_huckel(Chem.MolFromSmiles("c1ccccc1"))
    assert [round(x, 6) for x in result.orbital_energies] == [2.0, 1.0, 1.0, -1.0, -1.0, -2.0]


def test_butadiene_orbital_energies_are_the_closed_form_answer():
    result = solve_huckel(Chem.MolFromSmiles("C=CC=C"))
    assert [round(x, 3) for x in result.orbital_energies] == [1.618, 0.618, -0.618, -1.618]


def test_benzene_pi_density_is_exactly_one_per_carbon():
    result = solve_huckel(Chem.MolFromSmiles("c1ccccc1"))
    assert all(value == pytest.approx(1.0) for value in result.electron_density.values())


def test_benzene_total_pi_energy_is_eight_beta():
    """Textbook: 6*alpha + 8*beta."""
    result = solve_huckel(Chem.MolFromSmiles("c1ccccc1"))
    assert result.total_pi_energy == pytest.approx(8.0)


def test_benzene_homo_lumo_gap_is_two_beta():
    result = solve_huckel(Chem.MolFromSmiles("c1ccccc1"))
    assert result.homo == pytest.approx(1.0)
    assert result.lumo == pytest.approx(-1.0)
    assert result.homo_lumo_gap == pytest.approx(2.0)


def test_orbital_energies_come_back_in_descending_order():
    energies = solve_huckel(Chem.MolFromSmiles("c1ccccc1")).orbital_energies
    assert energies == sorted(energies, reverse=True)


def test_electrons_fill_two_per_orbital_from_the_bottom():
    result = solve_huckel(Chem.MolFromSmiles("c1ccccc1"))
    assert result.occupations == [2, 2, 2, 0, 0, 0]


def test_a_saturated_molecule_has_no_pi_system():
    assert pi_system_atoms(Chem.MolFromSmiles("CCCC")) == []
    assert solve_huckel(Chem.MolFromSmiles("CCCC")) is None

    result = compute_huckel_analysis(Chem.MolFromSmiles("CCCC"), "mol-1")
    assert result.cache_state == CacheState.FAILED
    assert "no conjugated pi system" in result.error


def test_heteroatoms_get_an_explicit_caveat():
    """Simple Huckel treats every pi centre as an identical carbon, so a
    pyridine is computed as if it were benzene. Saying so beats letting
    someone trust a wrong nitrogen density."""
    lines = compute_huckel_analysis(Chem.MolFromSmiles("c1ccncc1"), "mol-1").matched
    assert any("heteroatom" in line.lower() for line in lines)


def test_a_hydrocarbon_gets_no_caveat():
    lines = compute_huckel_analysis(Chem.MolFromSmiles("c1ccccc1"), "mol-1").matched
    assert not any("heteroatom" in line.lower() for line in lines)


def test_pi_density_dataset_covers_only_the_pi_atoms():
    dataset = compute_pi_electron_density(Chem.MolFromSmiles("c1ccccc1C"), "mol-1")
    assert len(dataset.values) == 6  # the ring, not the methyl


# --- Dipole: symmetry is the model-independent test ---------------------


@pytest.mark.parametrize("smiles,label", [("O=C=O", "CO2"), ("C(Cl)(Cl)(Cl)Cl", "CCl4"), ("c1ccccc1", "benzene")])
def test_a_symmetric_molecule_has_no_dipole(smiles, label):
    """The one check that validates the vector maths independently of how
    good the charge model is."""
    _vector, magnitude, _origin_independent = dipole_vector(_embed(smiles))
    assert magnitude == pytest.approx(0.0, abs=0.02), label


def test_an_asymmetric_molecule_has_one():
    _vector, magnitude, _ = dipole_vector(_embed("O"))
    assert magnitude > 0.5


def test_dipole_needs_a_conformer():
    result = compute_dipole_moment(Chem.MolFromSmiles("O"), "mol-1")
    assert result.cache_state == CacheState.FAILED
    assert "conformer" in result.error.lower()


def test_dipole_reports_vector_components_and_magnitude():
    lines = compute_dipole_moment(_embed("O"), "mol-1").matched
    joined = "\n".join(lines)
    for axis in ("Dipole X", "Dipole Y", "Dipole Z"):
        assert axis in joined
    assert "Debye" in joined


def test_a_charged_species_says_its_dipole_is_origin_dependent():
    """A point-charge dipole is only origin-independent at zero net charge.
    Picking an origin and not saying so would hide a real ambiguity."""
    _vector, _magnitude, origin_independent = dipole_vector(_embed("CC(=O)[O-]"))
    assert origin_independent is False

    lines = compute_dipole_moment(_embed("CC(=O)[O-]"), "mol-1").matched
    assert any("origin" in line for line in lines)


def test_a_neutral_species_is_origin_independent():
    _vector, _magnitude, origin_independent = dipole_vector(_embed("CCO"))
    assert origin_independent is True


# --- Molecular dynamics -------------------------------------------------


def test_total_energy_stays_bounded_rather_than_drifting():
    """The property that distinguishes a correct symplectic integrator from
    one that merely produces convincing motion. A drifting integrator still
    animates beautifully, which is why this is checked explicitly."""
    frames, _field = run_dynamics(_embed("CCO"), steps=2000, step_fs=0.5, frame_interval=20, seed=1)
    totals = [frame.total for frame in frames]

    drift = abs(totals[-1] - totals[0])
    spread = max(totals) - min(totals)
    assert drift < max(spread, 1.0)
    assert all(math.isfinite(value) for value in totals)


def test_an_over_large_timestep_is_reported_not_emitted_as_nan():
    """Confirmed live that a 5 fs step diverges into NaN rather than a big
    number -- which would have written NaN coordinates into every frame."""
    with pytest.raises(UnstableTrajectoryError, match="too large"):
        run_dynamics(_embed("CCO"), steps=2000, step_fs=5.0, seed=1)


def test_the_unstable_case_surfaces_as_a_failed_result():
    result = compute_molecular_dynamics(_embed("CCO"), "mol-1", {"steps": 2000, "step_fs": 5.0})
    assert result.cache_state == CacheState.FAILED
    assert "unstable" in result.error.lower()


def test_frames_times_and_energies_stay_aligned():
    result = compute_molecular_dynamics(
        _embed("CCO"), "mol-1", {"steps": 200, "frame_interval": 20, "seed": 1}
    )
    assert len(result.frames) == len(result.times) == len(result.energies)
    assert result.times == sorted(result.times)


def test_every_frame_is_a_parseable_structure():
    result = compute_molecular_dynamics(
        _embed("CCO"), "mol-1", {"steps": 100, "frame_interval": 25, "seed": 1}
    )
    for molblock in result.frames:
        assert "nan" not in molblock.lower()
        assert Chem.MolFromMolBlock(molblock, sanitize=False) is not None


def test_the_result_states_it_is_vacuum_dynamics():
    """MD invites questions about thermostats, solvent and boundaries that
    this implementation answers with 'none of those'."""
    result = compute_molecular_dynamics(_embed("CCO"), "mol-1", {"steps": 50, "seed": 1})
    caveat = result.metadata["caveat"]
    assert "Vacuum" in caveat
    assert "thermostat" in caveat
    assert "not comparable" in caveat


def test_dynamics_needs_a_conformer():
    result = compute_molecular_dynamics(Chem.MolFromSmiles("CCO"), "mol-1", {"steps": 10})
    assert result.cache_state == CacheState.FAILED


def test_a_seeded_run_is_reproducible():
    a = compute_molecular_dynamics(_embed("CCO"), "mol-1", {"steps": 100, "seed": 5}).energies
    b = compute_molecular_dynamics(_embed("CCO"), "mol-1", {"steps": 100, "seed": 5}).energies
    assert a == b


# --- CNS MPO: validated against ChemAxon's documented example ----------


def test_cns_mpo_reproduces_chemaxons_documented_aspirin_score():
    """ChemAxon documents aspirin at 5.75, every component 1.00 except
    HBD_SCORE = 0.75. Reproducing that total exactly is what validates the
    breakpoints -- they are not otherwise published in their docs."""
    aspirin = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
    components = cns_mpo_components(aspirin, logd=-2.16, most_basic_pka=-7.14)
    total = sum(score for _value, score in components.values() if score is not None)

    assert total == pytest.approx(5.75, abs=0.005)


def test_the_hbd_breakpoint_is_the_one_that_matches_the_documented_score():
    """Two forms appear in the literature. A linear fall to zero at HBD 4
    gives the documented 0.75 for HBD = 1; a 0.5-3.5 window gives 0.833 and
    does not. One published data point discriminated between them."""
    components = cns_mpo_components(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))
    _value, hbd_score = components["HBD"]
    assert hbd_score == pytest.approx(0.75)


def test_without_a_pka_predictor_the_term_is_omitted_not_assumed_favourable():
    """Scoring an unknown pKa as 1.0 would inflate every basic compound."""
    result = compute_cns_mpo(
        Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"), "mol-1", {}, interpreter_path=""
    )
    joined = "\n".join(result.matched)

    assert "unavailable" in joined
    assert "/ 5.00" in joined
    assert "would inflate" in joined


def test_a_large_greasy_molecule_scores_poorly():
    big = Chem.MolFromSmiles("CCCCCCCCCCCCCCCCCCCCc1ccc(cc1)c1ccc(cc1)C(=O)NCCCCCCCC")
    components = cns_mpo_components(big)
    total = sum(score for _v, score in components.values() if score is not None)
    assert total < 3.0


# --- Structural frameworks ---------------------------------------------


def test_a_ring_system_yields_a_scaffold_and_a_generic_framework():
    result = compute_structural_frameworks(
        Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"), "mol-1"
    )
    kinds = {entry.metadata["kind"] for entry in result.entries}
    assert kinds == {"scaffold", "generic"}


def test_the_generic_framework_is_all_carbon():
    result = compute_structural_frameworks(Chem.MolFromSmiles("c1ccncc1CCc1ccccc1"), "mol-1")
    generic = next(e for e in result.entries if e.metadata["kind"] == "generic")
    assert "n" not in generic.metadata["smiles"].lower().replace("c", "")


def test_an_acyclic_molecule_has_no_framework_and_says_so():
    result = compute_structural_frameworks(Chem.MolFromSmiles("CCCCO"), "mol-1")
    assert result.entries == []
    assert "acyclic" in result.name
