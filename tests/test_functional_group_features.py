"""What the Functional Groups calculator reports, per FEATURE INSTANCE.

REPORTED AS A REGRESSION, AND IT WAS TWO DEFECTS WEARING ONE COAT. Measured
on master 8be42b6:

    acetyl fentanyl   tertiary_amide      and nothing else
    MPMI              nothing at all
    4-HO-MPMI         phenol              and nothing else

One cause was an id collision (`test_result_persistence.py` covers it); the
other was vocabulary: the naming engine's detector answers "which group
becomes the suffix", so it has no ring amines, no ethers and no ring systems.

**SINCE VOCABULARY V2 (2026-09-18)** the calculator is the FUNCTIONAL GROUPS
PROJECTION of one canonical detection (`structure_annotation.canonical_features`);
what each feature is lives in `chem/feature_vocabulary.py`, cited to the Gold
Book. The per-pattern tests this file used to hold moved to the coverage
matrix (`test_structural_features.py`), and the merge-by-identity test to
the projection tests there. What stays here is the calculator's contract,
through the registry.

**INSTANCES, NOT STRINGS.** Each expectation pins the id, the category and
the atoms. A detector that produced the right label on the wrong atoms would
pass a string check and still paint the wrong part of the molecule.

Asserted THROUGH THE REGISTRY, because a direct-import test has passed here
before while the registration bound a shadowed function
(`feedback_test_calculators_through_the_registry`).
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
from openchem.chem.feature_vocabulary import VOCABULARY_VERSION, FeatureCategory

ACETYL_FENTANYL = "CC(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1"
MPMI = "CN1CCC[C@@H]1Cc1c[nH]c2ccccc12"


def _result(smiles: str, parameters: dict | None = None):
    definition = next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "functional_groups"
    )
    defaults = {p.name: p.default for p in definition.parameters}
    defaults.update(parameters or {})
    return definition.execution.compute(Chem.MolFromSmiles(smiles), "m", defaults)


def _features(smiles: str, parameters: dict | None = None) -> list[dict]:
    """The calculator's feature records, through the registry."""
    return _result(smiles, parameters).provenance.parameters["features"]


def _shown(features: list[dict], category: FeatureCategory | None = None) -> list[str]:
    return [
        f["key"] for f in features
        if f["functional_groups_view"] != "hidden"
        and (category is None or f["category"] == category.value)
    ]


# --- the reported molecules -------------------------------------------------


def test_fentanyl_reports_the_amide_the_ring_amine_and_both_phenyls():
    by_key: dict[str, list[dict]] = {}
    for feature in _features(ACETYL_FENTANYL):
        by_key.setdefault(feature["key"], []).append(feature)

    # The amide, on its C=O-N core only: the R groups are not the amide's
    # (the marking Ertl's algorithm makes too). Labelled "amide", never
    # "tertiary amide" -- Gold Book p. 69, note 1 (FG-001).
    (amide,) = by_key["fg:carboxamide"]
    assert amide["category"] == FeatureCategory.FUNCTIONAL_GROUP.value
    assert amide["atoms"] == [1, 2, 3]
    assert amide["label"] == "amide"
    assert "naming_engine" in amide["found_by"], "the engine's amide no longer agrees"

    # The piperidine nitrogen, which nomenclature names as part of its ring
    # and a chemist calls a tertiary amine -- and ONLY that N: the amide N
    # (atom 3) bears an acyl group and is not an amine.
    (amine,) = by_key["fg:tertiary_amine"]
    assert amine["atoms"] == [13]

    benzenes = by_key["benzene"]
    assert [f["atoms"] for f in benzenes] == [[4, 5, 6, 7, 8, 9], [16, 17, 18, 19, 20, 21]]
    assert all(f["category"] == FeatureCategory.RING_SYSTEM.value for f in benzenes)
    (piperidine,) = by_key["piperidine"]
    assert piperidine["category"] == FeatureCategory.RING_SYSTEM.value


def test_mpmi_is_no_longer_empty():
    features = _features(MPMI)
    assert _shown(features, FeatureCategory.FUNCTIONAL_GROUP) == ["fg:tertiary_amine"]
    assert _shown(features, FeatureCategory.STRUCTURAL_FEATURE) == ["sf:aromatic_nh"]
    assert _shown(features, FeatureCategory.RING_SYSTEM) == ["pyrrolidine", "1H-indole"]


def test_the_indole_is_one_fused_ring_system_not_benzene_plus_pyrrole():
    """`AnnotatedRing` already models a ring SYSTEM, so the calculator reads
    it rather than inventing a second notion of one."""
    rings = [f for f in _features(MPMI) if f["category"] == FeatureCategory.RING_SYSTEM.value]
    indole = next(f for f in rings if f["key"] == "1H-indole")
    assert len(indole["atoms"]) == 9
    assert "benzene" not in [f["key"] for f in rings]


def test_the_summary_keeps_the_kinds_apart():
    summary = _result(MPMI).provenance.parameters["summary"]
    assert summary == "1 functional group, 1 structural feature, 2 ring systems."


def test_every_record_says_who_found_it_and_how_this_view_treated_it():
    result = _result(ACETYL_FENTANYL)
    assert result.provenance.parameters["vocabulary_version"] == VOCABULARY_VERSION
    for feature in result.provenance.parameters["features"]:
        assert feature["found_by"], "a feature with no detector recorded"
        assert feature["detector"] == feature["found_by"][0], "the canonical detector must come first"
        assert feature["functional_groups_view"] in {"shown", "shown_nested", "hidden"}
        assert feature["atom_inspector_view"] in {"shown", "shown_non_primary"}


def test_a_suppressed_feature_is_recorded_but_not_drawn():
    """An acetal's two oxygens are detected as ethers AND hidden by this view
    (the acetal suppresses them): recorded, so the Atom Inspector can show
    them as non-primary, but neither coloured nor counted as a group."""
    result = _result("CC(OC)OC")
    records = {(f["key"], tuple(f["atoms"])): f for f in result.provenance.parameters["features"]}
    ethers = [f for (k, _), f in records.items() if k == "fg:ether"]
    assert [f["functional_groups_view"] for f in ethers] == ["hidden", "hidden"]
    assert [f["under"] for f in ethers] == ["fg:acetal", "fg:acetal"]
    assert result.provenance.parameters["groups_detected"] == 1
    assert set(result.provenance.parameters["category_labels"].values()) == {"acetal"}


def test_only_suffix_eligible_narrows_to_the_naming_vocabulary():
    """The option still means what it says: the suffix candidates the NAMER
    would consider -- through the engine's cross-attribution, not a second
    detector."""
    features = _features(ACETYL_FENTANYL, {"only_suffix_eligible": True})
    assert _shown(features) == ["fg:carboxamide"]


def test_prefix_labels_come_from_the_engine_that_names_them():
    features = _features("CC(=O)O", {"label_mode": "Prefix form"})
    (acid,) = [f for f in features if f["key"] == "fg:carboxylic_acid"]
    assert acid["label"] == "carboxy"


# --- the amine vocabulary, positive and negative ---------------------------


@pytest.mark.parametrize(
    "label,smiles,expected",
    [
        ("pyrrolidine", "C1CCNC1", "fg:secondary_amine"),
        ("piperidine", "C1CCNCC1", "fg:secondary_amine"),
        ("N-methylpiperidine", "CN1CCCCC1", "fg:tertiary_amine"),
        ("morpholine", "C1COCCN1", "fg:secondary_amine"),
        ("indole", "c1ccc2[nH]ccc2c1", "sf:aromatic_nh"),
        ("pyrrole", "c1cc[nH]c1", "sf:aromatic_nh"),
    ],
)
def test_ring_nitrogen_vocabulary(label, smiles, expected):
    assert expected in _shown(_features(smiles)), label


@pytest.mark.parametrize(
    "label,smiles,forbidden",
    [
        ("pyridine has no N-H", "c1ccncc1", "sf:aromatic_nh"),
        ("pyridine N-oxide", "[O-][n+]1ccccc1", "sf:aromatic_nh"),
        ("a lactam N is not an amine", "O=C1CCCN1", "fg:secondary_amine"),
        ("a ring sulfonamide N is not an amine", "O=S(=O)(C)N1CCCC1", "fg:tertiary_amine"),
    ],
)
def test_negative_ring_nitrogen_cases(label, smiles, forbidden):
    assert forbidden not in _shown(_features(smiles)), label


def test_a_protonated_ring_n_is_the_amine_in_its_cationic_state():
    """One feature, two states: the pH-selected structure's N-H2+ is the
    secondary amine CATIONIC, labelled as such -- not a second key from a
    second detector (FG-006)."""
    (amine,) = [f for f in _features("C1CC[NH2+]CC1") if f["key"] == "fg:secondary_amine"]
    assert amine["charge_state"] == "cationic"
    assert amine["label"] == "secondary ammonium"
