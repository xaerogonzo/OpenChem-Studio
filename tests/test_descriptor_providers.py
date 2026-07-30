from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.descriptor_providers import RDKitDescriptorProvider
from openchem.domain.common import CacheState


def _values_by_id(mol: Chem.Mol) -> dict:
    provider = RDKitDescriptorProvider()
    return {d.descriptor_id: d for d in provider.compute(mol, "mol-1")}


def test_new_scalar_descriptors_on_benzene():
    """Deterministic RDKit calls, same known-molecule-known-value pattern as
    test_descriptor_service.py's existing test_descriptor_completed_values_are_correct."""
    benzene = Chem.MolFromSmiles("c1ccccc1")
    results = _values_by_id(benzene)

    assert results["molar_refractivity"].value == pytest.approx(26.442, abs=1e-3)
    assert results["labute_asa"].value == pytest.approx(37.431, abs=1e-3)
    assert results["qed"].value == pytest.approx(0.4426, abs=1e-3)
    assert results["sa_score"].value == pytest.approx(1.0, abs=0.1)
    for descriptor_id in (
        "molar_refractivity", "labute_asa", "qed", "sa_score",
        "lipinski_pass", "veber_pass", "ghose_pass", "egan_pass",
    ):
        assert results[descriptor_id].cache_state == CacheState.COMPLETED
        assert results[descriptor_id].provenance is not None


def test_medicinal_chemistry_filters_on_benzene():
    # Benzene is tiny (MW ~78, 6 heavy atoms) -- passes Lipinski/Veber/Egan
    # (all comfortably under their thresholds) but FAILS Ghose, whose lower
    # bounds (MW >= 160, heavy atoms >= 20) a molecule this small can't meet.
    benzene = Chem.MolFromSmiles("c1ccccc1")
    results = _values_by_id(benzene)

    assert results["lipinski_pass"].value is True
    assert results["veber_pass"].value is True
    assert results["egan_pass"].value is True
    assert results["ghose_pass"].value is False


def test_lipinski_fails_for_a_large_high_logp_molecule():
    # A long-chain triglyceride-like ester: high MW, high LogP -- fails
    # multiple Lipinski criteria (MW > 500 and LogP > 5), so more than one
    # violation, which fails the "<=1 violation" rule.
    big_lipid = Chem.MolFromSmiles(
        "CCCCCCCCCCCCCCCCCC(=O)OCC(OC(=O)CCCCCCCCCCCCCCCCC)COC(=O)CCCCCCCCCCCCCCCCC"
    )
    results = _values_by_id(big_lipid)

    assert results["lipinski_pass"].value is False


def test_shape_descriptors_fail_without_a_real_3d_conformer():
    # A molecule parsed straight from SMILES (or given only 2D coords) has
    # no real 3D conformer -- Conformer.Is3D() is False either way. Shape
    # descriptors must report FAILED with an actionable message, not a
    # meaningless value computed from flat/degenerate coordinates, while
    # the rest of the descriptor batch (tested above) still succeeds.
    benzene = Chem.MolFromSmiles("c1ccccc1")
    results = _values_by_id(benzene)

    for descriptor_id in (
        "radius_of_gyration", "asphericity", "spherocity_index",
        "inertial_shape_factor", "pmi1", "pmi2", "pmi3", "npr1", "npr2", "pbf",
    ):
        descriptor = results[descriptor_id]
        assert descriptor.cache_state == CacheState.FAILED
        assert "3D conformer" in descriptor.error
        assert descriptor.value is None


def test_shape_descriptors_succeed_with_a_real_3d_conformer():
    ethanol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(ethanol, randomSeed=42)
    results = _values_by_id(ethanol)

    for descriptor_id in (
        "radius_of_gyration", "asphericity", "spherocity_index",
        "inertial_shape_factor", "pmi1", "pmi2", "pmi3", "npr1", "npr2", "pbf",
    ):
        descriptor = results[descriptor_id]
        assert descriptor.cache_state == CacheState.COMPLETED
        assert descriptor.value is not None
        assert descriptor.error is None

    assert results["radius_of_gyration"].value == pytest.approx(1.176, abs=0.01)
    assert results["npr1"].value == pytest.approx(0.245, abs=0.01)
    assert results["npr2"].value == pytest.approx(0.880, abs=0.01)


def test_compute_alerts_flags_a_known_pains_scaffold():
    # Rhodanine is a textbook PAINS alert scaffold -- confirmed live against
    # RDKit's own 480-entry PAINS catalog.
    rhodanine = Chem.MolFromSmiles("O=C1CSC(=S)N1")
    provider = RDKitDescriptorProvider()

    alerts = provider.compute_alerts(rhodanine, "mol-1")

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.alert_id == "pains"
    assert alert.molecule_uuid == "mol-1"
    assert alert.matched  # at least one PAINS entry matched
    assert alert.cache_state == CacheState.COMPLETED
    assert alert.provenance is not None


def test_compute_alerts_clean_molecule_has_no_matches():
    benzene = Chem.MolFromSmiles("c1ccccc1")
    provider = RDKitDescriptorProvider()

    alerts = provider.compute_alerts(benzene, "mol-1")

    assert alerts[0].matched == []


def test_compute_per_atom_returns_logp_mr_and_charge_datasets():
    ethanol = Chem.MolFromSmiles("CCO")
    provider = RDKitDescriptorProvider()

    datasets = provider.compute_per_atom(ethanol, "mol-1")

    by_id = {d.property_id: d for d in datasets}
    assert set(by_id) == {"crippen_logp_contrib", "crippen_mr_contrib", "gasteiger_charge"}
    for dataset in datasets:
        assert dataset.molecule_uuid == "mol-1"
        assert dataset.method == "rdkit"
        assert dataset.provenance is not None
        assert set(dataset.values) == {0, 1, 2}  # one entry per atom, ethanol has 3 heavy atoms

    # Confirmed live against RDKit directly.
    assert by_id["crippen_logp_contrib"].values[0] == pytest.approx(0.1441, abs=1e-3)
    assert by_id["crippen_mr_contrib"].values[0] == pytest.approx(2.503, abs=1e-3)
    # The hydroxyl oxygen (atom 2) should be more electronegative/charged
    # than the terminal carbon (atom 0) -- a real chemical sanity check,
    # not just "a number came out."
    assert by_id["gasteiger_charge"].values[2] < by_id["gasteiger_charge"].values[0]


def test_descriptor_ids_includes_shape_descriptors():
    provider = RDKitDescriptorProvider()
    ids = provider.descriptor_ids()

    assert "pbf" in ids
    assert "qed" in ids
    assert len(ids) == len(set(ids))  # no duplicates
