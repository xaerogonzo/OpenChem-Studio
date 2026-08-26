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
    # "Thiocarbonyl_group" alert (Phase 19).
    #
    # Asserted as a SUBSET rather than an exact count. This test has now
    # broken twice purely because a new alert family was added -- BRENK,
    # then mutagenicity -- which tells you nothing about PAINS, the thing
    # it exists to check. A missing family still fails here; an added one
    # no longer does.
    rhodanine = Chem.MolFromSmiles("O=C1CSC(=S)N1")
    provider = RDKitDescriptorProvider()

    alerts = provider.compute_alerts(rhodanine, "mol-1")

    alerts_by_id = {a.alert_id: a for a in alerts}
    assert {
        "pains", "brenk", "functional_groups", "herg_risk_factors",
        "mutagenicity_alerts",
    } <= set(alerts_by_id)
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


# ---------------------------------------------------------------------------
# NP-likeness, Bertz complexity and Fsp3 -- stage 1 of the calculator families.
#
# THE ORACLE IS NOT THE PAPER FOR TWO OF THE THREE, and the tests say which is
# which rather than leaving a reader to assume. RDKit's NP model is a 2015
# re-fit on a public corpus [source:npscorer2015], and its BertzCT deliberately
# departs from [source:bertz1981] for any aromatic molecule
# [source:rdkit_bertz]. So the shipped numbers are pinned as CHANGE DETECTORS
# against the installed RDKit, and the scientific claims are asserted where an
# oracle genuinely exists -- the kekule contract below being the sharpest.
# ---------------------------------------------------------------------------


def _np_raw(smiles: str):
    """The scorer's own answer, bypassing this project's refusal.

    Used to assert the MECHANISM behind the refusal rather than its effect,
    which is the only way to show the refusal is necessary rather than a
    stylistic choice.
    """
    from openchem.chem.descriptor_providers import _load_npscorer

    npscorer, fscore = _load_npscorer()
    return npscorer.scoreMolWConfidence(Chem.MolFromSmiles(smiles), fscore)


def test_the_three_new_descriptors_are_computed():
    results = _values_by_id(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))

    assert results["np_likeness"].value == pytest.approx(0.1218, abs=1e-3)
    assert results["np_likeness_confidence"].value == pytest.approx(0.96, abs=1e-3)
    assert results["bertz_ct"].value == pytest.approx(343.2229, abs=1e-3)
    assert results["fsp3"].value == pytest.approx(1 / 9, abs=1e-6)

    for descriptor_id in ("np_likeness", "np_likeness_confidence", "bertz_ct", "fsp3"):
        assert results[descriptor_id].cache_state == CacheState.COMPLETED
        assert results[descriptor_id].provenance is not None
        assert results[descriptor_id].category == "medicinal_chemistry"


def test_a_zero_confidence_np_score_is_refused_rather_than_reported():
    """Methane shares no fragment with the training corpus.

    The refusal is not fastidiousness: see the setup assertion below, which
    shows the number that would otherwise be printed is arithmetic rather than
    a measurement.
    """
    results = _values_by_id(Chem.MolFromSmiles("C"))

    refused = results["np_likeness"]
    assert refused.cache_state == CacheState.FAILED
    assert refused.value is None
    assert refused.error is not None
    assert "training corpus" in refused.error


def test_the_refused_score_would_have_been_exactly_zero():
    """THE SETUP ASSERTION, and it is what makes the refusal defensible.

    `scoreMolWConfidence` sums `fscore[bit]` over fragments PRESENT in the
    model, so an unrecognised fragment contributes nothing. A molecule at
    confidence 0 therefore scores exactly 0.0 BY CONSTRUCTION -- byte-identical
    to a molecule genuinely judged neutral. Without this, a reader could
    reasonably think the refusal was discarding a real value.

    If a future RDKit model recognises methane, this fails and the refusal
    should be re-examined rather than the test loosened.
    """
    raw = _np_raw("C")
    assert raw.confidence == 0.0
    assert raw.nplikeness == 0.0

    # ... and the control: a molecule the model DOES recognise is not refused,
    # so the branch above is not simply "always refuse".
    recognised = _np_raw("CCC")
    assert recognised.confidence > 0.0
    assert recognised.nplikeness != 0.0


def test_the_confidence_survives_a_refused_score():
    """A blanked confidence would hide WHY the score is missing.

    0.000 is a real statement about the molecule -- "none of it was
    recognised" -- and it is the only thing on screen that explains the
    refusal beside it.
    """
    results = _values_by_id(Chem.MolFromSmiles("C"))

    confidence = results["np_likeness_confidence"]
    assert confidence.cache_state == CacheState.COMPLETED
    assert confidence.value == pytest.approx(0.0)
    assert results["np_likeness"].cache_state == CacheState.FAILED


def test_a_partially_recognised_molecule_is_scored_and_says_so():
    """Propane sits between the two extremes: 0 < confidence < 1.

    The interesting case, because it is neither refused nor fully recognised,
    and a rule keyed on `confidence == 1.0` would wrongly refuse it.
    """
    results = _values_by_id(Chem.MolFromSmiles("CCC"))

    confidence = results["np_likeness_confidence"].value
    assert 0.0 < confidence < 1.0
    assert results["np_likeness"].cache_state == CacheState.COMPLETED


def test_a_natural_product_can_score_as_synthetic():
    """CAFFEINE IS THE CASE A READER MUST NOT GET WRONG.

    It is a natural product by any account and NP-likeness scores it NEGATIVE,
    while morphine scores strongly positive. The score is a Bayesian comparison
    against a corpus, never a statement about where a molecule came from --
    which is exactly what the tier-3 help contract has to say, and what this
    test stops anybody quietly "fixing".
    """
    caffeine = _values_by_id(Chem.MolFromSmiles("Cn1cnc2c1c(=O)n(C)c(=O)n2C"))
    morphine = _values_by_id(
        Chem.MolFromSmiles("CN1CC[C@]23c4c5ccc(O)c4O[C@H]2[C@@H](O)C=C[C@H]3[C@H]1C5")
    )

    assert caffeine["np_likeness"].value < 0.0
    assert morphine["np_likeness"].value > 0.0
    # Both are fully recognised, so the sign difference is the model's verdict
    # rather than an artefact of coverage.
    assert caffeine["np_likeness_confidence"].value == pytest.approx(1.0)
    assert morphine["np_likeness_confidence"].value == pytest.approx(1.0)


def test_the_np_scorer_is_not_reached_by_the_sa_scorers_name():
    """`npscorer` HAS NO `calculateScore`, and the sibling loader does.

    Writing `_load_npscorer` from `_load_sascorer` by analogy raises
    AttributeError at runtime, which in a lazily-imported provider means the
    failure surfaces the first time a user selects a molecule rather than at
    import. Asserted on the module so the trap is recorded where the next
    author will meet it.
    """
    from openchem.chem.descriptor_providers import _load_npscorer

    npscorer, fscore = _load_npscorer()
    assert not hasattr(npscorer, "calculateScore")
    assert hasattr(npscorer, "scoreMolWConfidence")
    assert fscore, "the model must be loaded and non-empty"


def test_loading_the_np_model_writes_nothing_to_the_console(capfd):
    """`readNPModel` prints to STDERR, and a GUI process has no console to
    take it.

    The stream matters and was measured: a `redirect_stdout` written first
    captured nothing at all. This asserts the effect rather than the mechanism,
    so it still holds if RDKit changes which stream it uses.
    """
    import openchem.chem.descriptor_providers as providers

    providers._npscorer_module = None
    providers._np_model = None
    try:
        capfd.readouterr()
        providers._load_npscorer()
        captured = capfd.readouterr()
    finally:
        providers._npscorer_module = None
        providers._np_model = None

    assert "reading NP model" not in captured.out
    assert "reading NP model" not in captured.err


def test_the_np_refusal_message_survives_a_windows_console():
    """Result strings reach Windows console streams, which cannot carry them.

    **AND cp1252 IS THE WRONG CODEPAGE TO TEST AGAINST, which is what this
    guard got wrong first.** This project's notes say "cp1252" throughout,
    because that is what `sys.stdout.encoding` reports in a modern terminal --
    but a Windows console defaults to an OEM codepage, and those are STRICTER.
    Measured:

        character   cp1252   cp437   cp850   ascii
        em dash     ok       RAISES  RAISES  RAISES
        tick        RAISES   RAISES  RAISES  RAISES
        Angstrom    ok       ok      ok      RAISES

    So an em dash -- which this message originally carried -- passes a cp1252
    assertion and still renders as a replacement character on a real console.
    A guard written against cp1252 survived the mutation that put it back.

    ASCII is the intersection and the only bound worth asserting. It is
    deliberately stricter than the Angstrom row needs: a units string may
    legitimately be non-ASCII, an ERROR MESSAGE has nothing to gain from it.
    """
    results = _values_by_id(Chem.MolFromSmiles("C"))

    error = results["np_likeness"].error
    assert error is not None
    assert error.isascii(), f"non-ASCII in a result string: {error!r}"


def test_bertz_complexity_is_the_same_for_two_kekule_forms(recwarn):
    """THE ORACLE FOR RDKit's OWN DEPARTURE FROM THE PAPER.

    Its docstring names two kekule forms of one molecule that the ORIGINAL
    implementation scored differently, and says the new behaviour is the
    correct one. That is a claim this implementation can be held to and the
    1981 paper cannot supply -- so it is the acceptance test for the aromatic
    half, in place of a printed value that would be testing the wrong thing.
    """
    first = Chem.MolFromSmiles("CC2=CN=C1C3=C(C(C)=C(C=N3)C)C=CC1=C2C")
    second = Chem.MolFromSmiles("CC3=CN=C2C1=NC=C(C)C(C)=C1C=CC2=C3C")

    # Assert the setup: these really are two spellings of one molecule, or the
    # claim below is about two different structures and proves nothing.
    assert Chem.MolToSmiles(first) == Chem.MolToSmiles(second)
    assert first.GetNumAtoms() == second.GetNumAtoms()

    assert _values_by_id(first)["bertz_ct"].value == pytest.approx(
        _values_by_id(second)["bertz_ct"].value, abs=1e-9
    )


def test_two_different_molecules_can_share_a_complexity():
    """Methane and propane are both 0.

    A property of the index rather than a defect, and it belongs in the help
    contract: a reader comparing two values must not read equality as identity.
    """
    methane = _values_by_id(Chem.MolFromSmiles("C"))["bertz_ct"].value
    propane = _values_by_id(Chem.MolFromSmiles("CCC"))["bertz_ct"].value

    assert methane == propane == pytest.approx(0.0)
    # The control: the index is not simply zero everywhere.
    assert _values_by_id(Chem.MolFromSmiles("CCCC"))["bertz_ct"].value > 0.0


def test_fsp3_spans_its_full_range():
    """Benzene has no sp3 carbon; cyclohexane has nothing else."""
    assert _values_by_id(Chem.MolFromSmiles("c1ccccc1"))["fsp3"].value == pytest.approx(0.0)
    assert _values_by_id(Chem.MolFromSmiles("C1CCCCC1"))["fsp3"].value == pytest.approx(1.0)


def test_a_carbon_free_molecule_gets_zero_rather_than_a_refusal():
    """Fsp3 divides by the carbon count, and water has none.

    RDKit returns 0.0 rather than raising, and this project reports it. Pinned
    because it is a division by zero that RETURNS -- the behaviour would be
    easy to "fix" into a refusal, and 0.0 is defensible: a molecule with no
    carbon has no sp3 carbon.
    """
    results = _values_by_id(Chem.MolFromSmiles("O"))

    assert results["fsp3"].cache_state == CacheState.COMPLETED
    assert results["fsp3"].value == pytest.approx(0.0)


def test_the_new_descriptors_join_a_category_that_already_existed():
    """No new category was declared, and that is deliberate.

    `medicinal_chemistry` already carried QED and SA score -- the two the
    round-1 survey wrongly reported as unbuilt, because it enumerated
    `CALCULATOR_DEFINITIONS` and treated one surface as the whole universe.
    Asserting the shared category is what stops a later change splitting these
    five apart into a second heading meaning the same thing.
    """
    from openchem.chem.descriptor_providers import _DESCRIPTOR_SPECS

    categories = {
        spec[0]: spec[3]
        for spec in _DESCRIPTOR_SPECS
        if spec[0] in {"qed", "sa_score", "np_likeness", "bertz_ct", "fsp3"}
    }
    assert len(categories) == 5, "a descriptor went missing"
    assert set(categories.values()) == {"medicinal_chemistry"}
