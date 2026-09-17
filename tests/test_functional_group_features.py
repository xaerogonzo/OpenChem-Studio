"""What the Functional Groups calculator reports, per FEATURE INSTANCE.

REPORTED AS A REGRESSION, AND IT WAS TWO DEFECTS WEARING ONE COAT. Measured
on master 8be42b6:

    acetyl fentanyl   tertiary_amide      and nothing else
    MPMI              nothing at all
    4-HO-MPMI         phenol              and nothing else

One cause is an id collision (`test_result_persistence.py` covers that half:
the RDKit fragment counter and this calculator shared `functional_groups`, so
each overwrote the other in the store and the older, richer-looking answer
appeared once and never again). The other is vocabulary: the naming engine's
detector answers "which group becomes the suffix", so it has no ring amines
(every amine SMARTS carries `!R`), no ethers, and no ring systems.

**INSTANCES, NOT STRINGS.** Each expectation below pins the key, the
category, the atom set and the source. A detector that produced the right
label on the wrong atoms would pass a string check and still paint the wrong
part of the molecule, which is the whole point of this result.

Asserted THROUGH THE REGISTRY, because a direct-import test has passed here
before while the registration bound a shadowed function
(`feedback_test_calculators_through_the_registry`).
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
from openchem.chem.functional_group_patterns import (
    PATTERNS,
    VOCABULARY_VERSION,
    FeatureCategory,
    FeatureSource,
    match_patterns,
)

ACETYL_FENTANYL = "CC(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1"
MPMI = "CN1CCC[C@@H]1Cc1c[nH]c2ccccc12"


def _features(smiles: str, parameters: dict | None = None) -> list[dict]:
    """The calculator's feature records, through the registry."""
    definition = next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "functional_groups"
    )
    defaults = {p.name: p.default for p in definition.parameters}
    defaults.update(parameters or {})
    result = definition.execution.compute(Chem.MolFromSmiles(smiles), "m", defaults)
    return result.provenance.parameters["features"]


def _keys(features: list[dict], category: FeatureCategory | None = None) -> list[str]:
    return [
        f["key"] for f in features
        if category is None or f["category"] == category.value
    ]


# --- the reported molecules -------------------------------------------------


def test_fentanyl_reports_the_amide_the_ring_amine_and_both_phenyls():
    features = _features(ACETYL_FENTANYL)
    by_key: dict[str, list[dict]] = {}
    for feature in features:
        by_key.setdefault(feature["key"], []).append(feature)

    # The amide, as before: the engine's own detector, on the C=O-N core plus
    # the two N-substituent carbons it claims.
    (amide,) = by_key["tertiary_amide"]
    assert amide["category"] == FeatureCategory.FUNCTIONAL_GROUP.value
    assert amide["source"] == FeatureSource.NAMING_ENGINE.value
    assert amide["atoms"] == [1, 2, 3, 4, 10]

    # The piperidine nitrogen, which nomenclature names as part of its ring
    # and a chemist calls a tertiary amine.
    (amine,) = by_key["ring_tertiary_amine"]
    assert amine["category"] == FeatureCategory.FUNCTIONAL_GROUP.value
    assert amine["label"] == "tertiary amine (ring)"
    assert 12 in amine["atoms"], "the ring N is not in the amine's atoms"

    # TWO benzene rings, as two instances of one key, plus the piperidine.
    benzenes = by_key["benzene"]
    assert len(benzenes) == 2
    assert [f["atoms"] for f in benzenes] == [[4, 5, 6, 7, 8, 9], [16, 17, 18, 19, 20, 21]]
    assert all(f["category"] == FeatureCategory.RING_SYSTEM.value for f in benzenes)
    (piperidine,) = by_key["piperidine"]
    assert piperidine["category"] == FeatureCategory.RING_SYSTEM.value


def test_mpmi_is_no_longer_empty():
    features = _features(MPMI)
    assert _keys(features, FeatureCategory.FUNCTIONAL_GROUP) == ["ring_tertiary_amine"]
    assert _keys(features, FeatureCategory.STRUCTURAL_FEATURE) == ["aromatic_amine_nh"]
    assert _keys(features, FeatureCategory.RING_SYSTEM) == ["pyrrolidine", "1H-indole"]


def test_the_indole_is_one_fused_ring_system_not_benzene_plus_pyrrole():
    """The vocabulary question this had to answer. `AnnotatedRing` already
    models a ring SYSTEM, so the calculator reads it rather than inventing a
    second notion of one."""
    rings = [f for f in _features(MPMI) if f["category"] == FeatureCategory.RING_SYSTEM.value]
    indole = next(f for f in rings if f["key"] == "1H-indole")
    assert len(indole["atoms"]) == 9
    assert "benzene" not in _keys(rings)


def test_the_summary_keeps_the_kinds_apart():
    definition = next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "functional_groups"
    )
    defaults = {p.name: p.default for p in definition.parameters}
    result = definition.execution.compute(Chem.MolFromSmiles(MPMI), "m", defaults)
    summary = result.provenance.parameters["summary"]
    assert summary == "1 functional group, 1 structural feature, 2 ring systems."


def test_every_feature_carries_exactly_one_source_and_the_vocabulary_version():
    features = _features(ACETYL_FENTANYL)
    assert features
    for feature in features:
        assert feature["source"] in {s.value for s in FeatureSource}
        assert feature["found_by"], "a feature with no detector recorded"
        assert feature["source"] == feature["found_by"][0], "the canonical source must come first"
    definition = next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "functional_groups"
    )
    result = definition.execution.compute(
        Chem.MolFromSmiles(ACETYL_FENTANYL), "m",
        {p.name: p.default for p in definition.parameters},
    )
    assert result.provenance.parameters["vocabulary_version"] == VOCABULARY_VERSION


def test_only_suffix_eligible_narrows_to_the_naming_vocabulary():
    """The existing option still means what it says: the suffix candidates
    the NAMER would consider, not the chemist's wider list."""
    features = _features(ACETYL_FENTANYL, {"only_suffix_eligible": True})
    assert _keys(features) == ["tertiary_amide"]


# --- the amine vocabulary, positive and negative ---------------------------


@pytest.mark.parametrize(
    "label,smiles,expected",
    [
        ("pyrrolidine", "C1CCNC1", "ring_secondary_amine"),
        ("piperidine", "C1CCNCC1", "ring_secondary_amine"),
        ("N-methylpiperidine", "CN1CCCCC1", "ring_tertiary_amine"),
        ("morpholine", "C1COCCN1", "ring_secondary_amine"),
        ("indole", "c1ccc2[nH]ccc2c1", "aromatic_amine_nh"),
        ("pyrrole", "c1cc[nH]c1", "aromatic_amine_nh"),
    ],
)
def test_ring_nitrogen_vocabulary(label, smiles, expected):
    assert expected in _keys(_features(smiles)), label


@pytest.mark.parametrize(
    "label,smiles,forbidden",
    [
        # THE ONE A WIDER AMINE PATTERN GETS WRONG: fentanyl's amide nitrogen
        # is in no ring, but a relaxed pattern claims any N with three carbons.
        ("fentanyl's amide N", ACETYL_FENTANYL, None),
        ("pyridine has no N-H", "c1ccncc1", "aromatic_amine_nh"),
        ("pyridine N-oxide", "[O-][n+]1ccccc1", "aromatic_amine_nh"),
        ("a lactam N is not an amine", "O=C1CCCN1", "ring_secondary_amine"),
        ("a ring sulfonamide N is not an amine", "O=S(=O)(C)N1CCCC1", "ring_tertiary_amine"),
        ("a protonated ring N is not a neutral amine", "C1CC[NH2+]CC1", "ring_secondary_amine"),
    ],
)
def test_negative_ring_nitrogen_cases(label, smiles, forbidden):
    keys = _keys(_features(smiles))
    if forbidden is None:
        # Fentanyl: the ring amine is the PIPERIDINE nitrogen, and the amide
        # nitrogen must not also be counted as one.
        amines = [
            f for f in _features(smiles)
            if f["key"].endswith("amine")
        ]
        assert len(amines) == 1, f"{label}: expected one ring amine, got {amines}"
        assert 3 not in amines[0]["atoms"], f"{label}: the amide N was claimed as an amine"
    else:
        assert forbidden not in keys, label


# --- the pattern catalogue --------------------------------------------------


def test_every_pattern_parses_and_declares_its_scope():
    for spec in PATTERNS:
        assert Chem.MolFromSmarts(spec.smarts) is not None, spec.key
        assert spec.excludes.strip(), f"{spec.key} does not say what it excludes"
        assert spec.charge_policy.strip(), f"{spec.key} does not declare a charge policy"
        assert spec.reference.strip(), f"{spec.key} has no reference"


@pytest.mark.parametrize(
    "label,smiles,expected",
    [
        ("diethyl ether", "CCOCC", {"ether"}),
        ("anisole is an aryl ether", "COc1ccccc1", {"ether"}),
        ("diphenyl ether", "c1ccccc1Oc1ccccc1", {"ether"}),
        ("THF is a cyclic ether", "C1CCOC1", {"ether"}),
        ("thioanisole", "CSc1ccccc1", {"thioether"}),
        ("dimethyl sulfide", "CSC", {"thioether"}),
        ("protonated piperidine", "C1CC[NH2+]CC1", {"ammonium"}),
        ("choline", "C[N+](C)(C)CCO", {"quaternary_ammonium"}),
        # An ester O, a furan O and a thiophene S are not ethers; a
        # pyridinium and a nitro N are not ammonium.
        ("ethyl acetate", "CC(=O)OCC", set()),
        ("furan", "c1ccoc1", set()),
        ("thiophene", "c1ccsc1", set()),
        ("thioester", "CC(=O)SC", set()),
        ("carbonate", "COC(=O)OC", set()),
        ("nitrate ester", "CO[N+](=O)[O-]", set()),
        ("sulfoxide", "CS(=O)C", set()),
        ("pyridinium", "c1cc[nH+]cc1", set()),
        ("nitrobenzene", "[O-][N+](=O)c1ccccc1", set()),
    ],
)
def test_pattern_catalogue(label, smiles, expected):
    found = {m.spec.key for m in match_patterns(Chem.MolFromSmiles(smiles))}
    assert found == expected, label


def test_a_pattern_and_the_engine_can_both_claim_a_nitrogen_without_merging():
    """Distinct features that SHARE atoms both survive; only an identical
    identity merges. Choline's nitrogen is a quaternary ammonium and is in no
    ring, so nothing else claims it -- what this pins is that the merge is by
    identity rather than by atom overlap."""
    from openchem.chem.functional_group_patterns import FeatureInstance, merge_features

    shared = frozenset({3})
    a = FeatureInstance(
        key="ring_tertiary_amine", category=FeatureCategory.FUNCTIONAL_GROUP,
        atoms=shared, anchor=3, label="tertiary amine (ring)",
        source=FeatureSource.NAMING_ENGINE, found_by=(FeatureSource.NAMING_ENGINE,),
    )
    b = FeatureInstance(
        key="piperidine", category=FeatureCategory.RING_SYSTEM,
        atoms=shared, anchor=3, label="piperidine",
        source=FeatureSource.NAMING_ENGINE, found_by=(FeatureSource.NAMING_ENGINE,),
    )
    same_as_a = FeatureInstance(
        key="ring_tertiary_amine", category=FeatureCategory.FUNCTIONAL_GROUP,
        atoms=shared, anchor=3, label="tertiary amine",
        source=FeatureSource.STRUCTURAL_PATTERN, found_by=(FeatureSource.STRUCTURAL_PATTERN,),
    )

    merged = merge_features([a, b, same_as_a])

    assert len(merged) == 2, "features sharing atoms were collapsed"
    amine = next(f for f in merged if f.key == "ring_tertiary_amine")
    assert amine.source is FeatureSource.NAMING_ENGINE, "the canonical producer changed"
    assert set(amine.found_by) == {FeatureSource.NAMING_ENGINE, FeatureSource.STRUCTURAL_PATTERN}
