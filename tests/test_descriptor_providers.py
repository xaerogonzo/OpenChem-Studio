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
    # RDKit's own 480-entry PAINS catalog. It also trips BRENK's
    # "Thiocarbonyl_group" alert (Phase 19). compute_alerts() now returns
    # four AlertResults total (Phase 20 adds functional_groups and
    # herg_risk_factors alongside pains/brenk).
    rhodanine = Chem.MolFromSmiles("O=C1CSC(=S)N1")
    provider = RDKitDescriptorProvider()

    alerts = provider.compute_alerts(rhodanine, "mol-1")

    assert len(alerts) == 4
    alerts_by_id = {a.alert_id: a for a in alerts}
    assert set(alerts_by_id) == {"pains", "brenk", "functional_groups", "herg_risk_factors"}
    pains = alerts_by_id["pains"]
    assert pains.molecule_uuid == "mol-1"
    assert pains.matched  # at least one PAINS entry matched
    assert pains.category == "medicinal_chemistry"
    brenk = alerts_by_id["brenk"]
    assert brenk.matched
    assert brenk.category == "admet"
    assert pains.cache_state == CacheState.COMPLETED
    assert pains.provenance is not None


def test_compute_alerts_clean_molecule_has_no_matches():
    benzene = Chem.MolFromSmiles("c1ccccc1")
    provider = RDKitDescriptorProvider()

    alerts = provider.compute_alerts(benzene, "mol-1")

    assert alerts[0].matched == []


def test_compute_alerts_brenk_flags_a_known_reactive_group():
    # Confirmed live: BRENK's 105-entry catalog flags acetaldehyde as
    # "aldehyde" and leaves benzene/ethanol clean.
    acetaldehyde = Chem.MolFromSmiles("CC=O")
    provider = RDKitDescriptorProvider()

    alerts = {a.alert_id: a for a in provider.compute_alerts(acetaldehyde, "mol-1")}

    assert "aldehyde" in alerts["brenk"].matched
    assert alerts["brenk"].category == "admet"


def test_esol_solubility_matches_known_values():
    # Confirmed live against known experimental logS values (ESOL's own
    # documented accuracy is roughly +/-1 log unit; these are well within
    # that): aspirin -2.09 predicted vs. -2.19 experimental, caffeine
    # -0.53 vs. -0.8.
    aspirin = Chem.MolFromSmiles("CC(=O)OC1=CC=CC=C1C(=O)O")
    caffeine = Chem.MolFromSmiles("CN1C=NC2=C1C(=O)N(C(=O)N2C)C")

    aspirin_esol = _values_by_id(aspirin)["esol_logs"].value
    caffeine_esol = _values_by_id(caffeine)["esol_logs"].value

    assert aspirin_esol == pytest.approx(-2.09, abs=0.05)
    assert caffeine_esol == pytest.approx(-0.53, abs=0.05)


def test_bbb_permeant_true_for_a_small_low_polarity_molecule():
    # Caffeine: small, moderate TPSA (~58), well under both thresholds.
    caffeine = Chem.MolFromSmiles("CN1C=NC2=C1C(=O)N(C(=O)N2C)C")
    assert _values_by_id(caffeine)["bbb_permeant"].value is True


def test_bbb_permeant_false_for_a_large_high_tpsa_molecule():
    big_lipid = Chem.MolFromSmiles(
        "CCCCCCCCCCCCCCCCCC(=O)OCC(OC(=O)CCCCCCCCCCCCCCCCC)COC(=O)CCCCCCCCCCCCCCCCC"
    )
    assert _values_by_id(big_lipid)["bbb_permeant"].value is False


def test_bioavailability_likely_true_for_aspirin():
    aspirin = Chem.MolFromSmiles("CC(=O)OC1=CC=CC=C1C(=O)O")
    assert _values_by_id(aspirin)["bioavailability_likely"].value is True


def test_bioavailability_likely_false_for_a_large_high_logp_molecule():
    big_lipid = Chem.MolFromSmiles(
        "CCCCCCCCCCCCCCCCCC(=O)OCC(OC(=O)CCCCCCCCCCCCCCCCC)COC(=O)CCCCCCCCCCCCCCCCC"
    )
    assert _values_by_id(big_lipid)["bioavailability_likely"].value is False


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


# --- Phase 20: functional groups, extended filters, hERG risk factors -------


def test_pfizer_375_rule_fails_for_high_logp_low_tpsa_molecule():
    # Confirmed live: LogP 9.27, TPSA 0.0 -- squarely in Pfizer's flagged
    # high-risk regime (LogP > 3 and TPSA < 75).
    lipophilic = Chem.MolFromSmiles("CCCCCCCCCCCCCCCCCCCCc1ccccc1")
    assert _values_by_id(lipophilic)["pfizer_375_pass"].value is False


def test_pfizer_375_rule_passes_for_aspirin():
    aspirin = Chem.MolFromSmiles("CC(=O)OC1=CC=CC=C1C(=O)O")
    assert _values_by_id(aspirin)["pfizer_375_pass"].value is True


def test_gsk_400_rule_fails_for_a_large_high_logp_molecule():
    big_lipid = Chem.MolFromSmiles(
        "CCCCCCCCCCCCCCCCCC(=O)OCC(OC(=O)CCCCCCCCCCCCCCCCC)COC(=O)CCCCCCCCCCCCCCCCC"
    )
    assert _values_by_id(big_lipid)["gsk_400_pass"].value is False


def test_gsk_400_rule_passes_for_aspirin():
    aspirin = Chem.MolFromSmiles("CC(=O)OC1=CC=CC=C1C(=O)O")
    assert _values_by_id(aspirin)["gsk_400_pass"].value is True


def test_rule_of_three_fails_for_a_large_molecule():
    big_lipid = Chem.MolFromSmiles(
        "CCCCCCCCCCCCCCCCCC(=O)OCC(OC(=O)CCCCCCCCCCCCCCCCC)COC(=O)CCCCCCCCCCCCCCCCC"
    )
    assert _values_by_id(big_lipid)["rule_of_three_pass"].value is False


def test_rule_of_three_passes_for_a_small_fragment():
    # Phenol: MW ~94, LogP ~1.5, 1 HBD, 1 HBA -- comfortably within
    # Congreve's MW<300/LogP<=3/HBD<=3/HBA<=3.
    phenol = Chem.MolFromSmiles("Oc1ccccc1")
    assert _values_by_id(phenol)["rule_of_three_pass"].value is True


def test_functional_groups_on_aspirin():
    aspirin = Chem.MolFromSmiles("CC(=O)OC1=CC=CC=C1C(=O)O")
    provider = RDKitDescriptorProvider()

    alerts = {a.alert_id: a for a in provider.compute_alerts(aspirin, "mol-1")}
    groups = alerts["functional_groups"]

    assert groups.category == "admet"
    assert any(g.startswith("Ester") for g in groups.matched)
    assert any(g.startswith("Carboxylic Acid") for g in groups.matched)
    assert any(g.startswith("Benzene Ring") for g in groups.matched)
    # Aspirin's phenol oxygen is esterified -- must NOT show as a free phenol.
    assert not any(g.startswith("Phenol") for g in groups.matched)


def test_functional_groups_empty_for_a_bare_alkane():
    ethane = Chem.MolFromSmiles("CC")
    provider = RDKitDescriptorProvider()

    alerts = {a.alert_id: a for a in provider.compute_alerts(ethane, "mol-1")}

    assert alerts["functional_groups"].matched == []


def test_herg_risk_factors_all_present_for_verapamil():
    # Verapamil: real, well-known hERG blocker -- tertiary amine, LogP > 3,
    # two aromatic rings. All three risk factors should be listed.
    verapamil = Chem.MolFromSmiles("COc1ccc(CCN(C)CCCC(C#N)(c2ccc(OC)c(OC)c2)C(C)C)cc1OC")
    provider = RDKitDescriptorProvider()

    alerts = {a.alert_id: a for a in provider.compute_alerts(verapamil, "mol-1")}
    risk = alerts["herg_risk_factors"]

    assert risk.name == "hERG Risk Factors (not a prediction)"
    assert risk.category == "admet"
    assert any("lipophilicity" in factor for factor in risk.matched)
    assert "Basic amine present" in risk.matched
    assert any("aromatic ring" in factor for factor in risk.matched)


def test_herg_risk_factors_few_for_aspirin():
    # Aspirin: no basic amine, LogP well under 3 -- only the aromatic-ring
    # factor should show.
    aspirin = Chem.MolFromSmiles("CC(=O)OC1=CC=CC=C1C(=O)O")
    provider = RDKitDescriptorProvider()

    alerts = {a.alert_id: a for a in provider.compute_alerts(aspirin, "mol-1")}
    risk = alerts["herg_risk_factors"]

    assert "Basic amine present" not in risk.matched
    assert not any("lipophilicity" in factor for factor in risk.matched)


def test_herg_basic_amine_smarts_does_not_false_positive_on_amide_sulfonamide_or_aniline():
    """Regression test pinning the live-verified SMARTS: two earlier draft
    patterns false-positived on benzenesulfonamide and aniline before this
    was fixed during planning."""
    provider = RDKitDescriptorProvider()
    for smiles in ("CC(=O)N", "NS(=O)(=O)c1ccccc1", "Nc1ccccc1", "c1ccncc1"):
        mol = Chem.MolFromSmiles(smiles)
        alerts = {a.alert_id: a for a in provider.compute_alerts(mol, "mol-1")}
        assert "Basic amine present" not in alerts["herg_risk_factors"].matched, smiles


def test_herg_basic_amine_smarts_matches_plain_aliphatic_amines():
    provider = RDKitDescriptorProvider()
    for smiles in ("CCNCC", "CCN(CC)CC"):  # diethylamine, triethylamine
        mol = Chem.MolFromSmiles(smiles)
        alerts = {a.alert_id: a for a in provider.compute_alerts(mol, "mol-1")}
        assert "Basic amine present" in alerts["herg_risk_factors"].matched, smiles
