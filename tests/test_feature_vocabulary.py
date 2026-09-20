"""The v2 structural-feature vocabulary and its coverage matrix, before any detector.

Branch B's contract (plan B0): the ontology and the fixture obligations are
committed BEFORE the patterns, so the patterns are tested against them rather
than the other way round. These tests hold the two to their own declared
shape; `test_structural_features.py` (B1) runs the detector against them.

**A FIXTURE IS ITS OWN EXPECTATION.** Atom-map numbers mark the expected
atoms: role i (1-based) of instance k (0-based) carries map 10*k + i. So a
fixture cannot drift from the index list it would otherwise need, and the
checks below can say exactly which atom a malformed row mislabels.
"""

from __future__ import annotations

import json
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.chem.feature_vocabulary import (
    ENGINE_GROUP_FALLBACK,
    ENGINE_GROUP_MAP,
    FEATURE_BY_ID,
    FEATURES,
    ChargeState,
    DefinitionSource,
    RelationKind,
    RELATIONS,
    validate_vocabulary,
)

ROOT = Path(__file__).resolve().parents[1]
COVERAGE = ROOT / "tests" / "fixtures" / "structural_features" / "coverage.toml"
ENGINE_GROUPS = ROOT / "src" / "openchem" / "vendor" / "data" / "functional_groups.json"
ERTL_SI = ROOT / "tests" / "fixtures" / "structural_features" / "ertl_si_representatives.json"


def _coverage() -> dict:
    return tomllib.loads(COVERAGE.read_text(encoding="utf-8"))


def _rows() -> list[dict]:
    return _coverage()["feature"]


def expected_instances(smiles: str) -> list[dict[int, int]]:
    """{atom index: role index} per instance, instance order, from the maps.

    Shared with the detector tests, which is why it is a plain function.
    """
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, f"unparseable fixture {smiles}"
    by_instance: dict[int, dict[int, int]] = defaultdict(dict)
    for atom in mol.GetAtoms():
        tag = atom.GetAtomMapNum()
        if tag:
            by_instance[tag // 10][atom.GetIdx()] = tag % 10
    return [by_instance[k] for k in sorted(by_instance)]


def _canonical(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(mol)


def test_the_vocabulary_is_consistent():
    assert validate_vocabulary() == []


def test_the_matrix_covers_every_feature_once_in_declared_order():
    """One table per feature and nothing else: a feature with no obligations
    is a feature nothing will ever test."""
    assert [row["id"] for row in _rows()] == [f.feature_id for f in FEATURES]


@pytest.mark.parametrize("row", _rows(), ids=lambda r: r["id"])
def test_every_feature_carries_its_obligations(row):
    feature = FEATURE_BY_ID[row["id"]]
    states = set(feature.labels)
    assert row.get("negative"), "no negative fixture: nothing tests what it must NOT match"
    for negative in row["negative"]:
        assert negative.get("why"), f"{negative['smiles']}: a negative without its reason"
    if ChargeState.NEUTRAL in states:
        assert row.get("positive"), "detectable when neutral, but no neutral positive"
    else:
        assert not row.get("positive"), "has no neutral state, so a neutral positive contradicts it"
    charged_states = {ChargeState(c["state"]) for c in row.get("charged", [])}
    assert charged_states == states - {ChargeState.NEUTRAL}, (
        "every non-neutral state needs a charged fixture, and no other state may have one"
    )


@pytest.mark.parametrize("row", _rows(), ids=lambda r: r["id"])
def test_every_marked_fixture_names_real_roles_and_the_defining_atom(row):
    feature = FEATURE_BY_ID[row["id"]]
    fixtures = list(row.get("positive", [])) + [c["smiles"] for c in row.get("charged", [])]
    for smiles in fixtures:
        instances = expected_instances(smiles)
        assert instances, f"{smiles}: a positive with no marked atom"
        for k, roles in enumerate(instances):
            assert set(roles.values()) <= set(range(1, len(feature.roles) + 1)), (
                f"{smiles}: instance {k} uses a role number {feature.feature_id} does not have"
            )
            assert 1 in roles.values(), (
                f"{smiles}: instance {k} has no atom of role 1 ({feature.roles[0]})"
            )
        tags = {a.GetAtomMapNum() // 10 for a in Chem.MolFromSmiles(smiles).GetAtoms() if a.GetAtomMapNum()}
        assert tags == set(range(len(instances))), f"{smiles}: instance numbers are not 0..n-1"


@pytest.mark.parametrize("row", _rows(), ids=lambda r: r["id"])
def test_a_charged_fixture_is_actually_in_its_state(row):
    """The state is MEASURED off the marked atoms, the way the detector will
    measure it -- so a fixture cannot claim a charge its drawing lacks."""
    for charged in row.get("charged", []):
        mol = Chem.MolFromSmiles(charged["smiles"])
        for roles in expected_instances(charged["smiles"]):
            total = sum(mol.GetAtomWithIdx(i).GetFormalCharge() for i in roles)
            state = (ChargeState.NEUTRAL if total == 0
                     else ChargeState.ANIONIC if total < 0 else ChargeState.CATIONIC)
            assert state.value == charged["state"], charged["smiles"]


@pytest.mark.parametrize("row", _rows(), ids=lambda r: r["id"])
def test_negatives_parse_and_carry_no_marks(row):
    for negative in row["negative"]:
        mol = Chem.MolFromSmiles(negative["smiles"])
        assert mol is not None, negative["smiles"]
        assert not any(a.GetAtomMapNum() for a in mol.GetAtoms()), (
            f"{negative['smiles']}: a negative expects no instance, so it marks no atom"
        )


def test_every_declared_relation_has_an_overlap_fixture():
    """A relation nobody exercises is a relation nothing tests."""
    covered = set()
    for fixture in _coverage()["overlap"]:
        covered |= set(_parse_relation(fixture["relation"]))
    for relation in RELATIONS:
        if relation.kind is RelationKind.EXCLUDES:
            continue  # an invariant over every fixture, not a molecule of its own
        assert (relation.subject, relation.kind, relation.object) in covered, (
            f"no overlap fixture for {relation.subject} {relation.kind.value} {relation.object}"
        )


def _parse_relation(text: str) -> list[tuple[str, RelationKind, str]]:
    """"A kind B, C" -> [(A, kind, B), (A, kind, C)], each one a DECLARED
    relation. Parsed exactly: a substring test passed while three of the four
    acyl-halide relations had no fixture at all."""
    subject, kind, rest = text.split(" ", 2)
    triples = [(subject, RelationKind(kind), obj.strip()) for obj in rest.split(",")]
    declared = {(r.subject, r.kind, r.object) for r in RELATIONS}
    for triple in triples:
        assert triple in declared, f"overlap fixture names an undeclared relation {triple}"
    return triples


@pytest.mark.parametrize("fixture", _coverage()["overlap"], ids=lambda f: f["relation"])
def test_an_overlap_fixture_projects_only_what_it_detects(fixture):
    detected = Counter(fixture["detected"])
    for feature_id in detected:
        assert feature_id in FEATURE_BY_ID, feature_id
    assert not Counter(fixture["functional_groups"]) - detected
    assert not Counter(fixture["inspector_non_primary"]) - detected
    counts = Counter(fixture["fragment_counts"])
    assert not counts - detected, "a projection cannot count what was not detected"


def test_normative_and_overlap_fixtures_are_different_molecules():
    """Plan B0: normative, Ertl-mapping and overlap fixtures are different
    molecules, so a relation fixture cannot quietly stand in for a
    definition's own positive."""
    normative = set()
    for row in _rows():
        for smiles in row.get("positive", []):
            normative.add(_canonical(smiles))
        for charged in row.get("charged", []):
            normative.add(_canonical(charged["smiles"]))
        for negative in row["negative"]:
            normative.add(_canonical(negative["smiles"]))
    overlap = {_canonical(f["smiles"]) for f in _coverage()["overlap"]}
    assert not normative & overlap, sorted(normative & overlap)
    ertl = {
        _canonical(r["smiles"])
        for r in json.loads(ERTL_SI.read_text(encoding="utf-8"))["representatives"]
    }
    assert not normative & ertl, sorted(normative & ertl)
    assert not overlap & ertl, sorted(overlap & ertl)


def test_every_engine_group_type_is_mapped_or_justified():
    """The engine's vocabulary reaches this one only through the map, and a
    new engine type must not arrive unaccounted for."""
    data = json.loads(ENGINE_GROUPS.read_text(encoding="utf-8"))
    types = {
        group["name"]
        for section in ("suffix_groups", "prefix_only_groups", "structural_groups")
        for group in data[section]
    }
    declared = set(ENGINE_GROUP_MAP) | set(ENGINE_GROUP_FALLBACK)
    assert types - declared == set(), "engine types with no mapping and no justification"
    assert declared - types == set(), "mapping entries for engine types that no longer exist"
    for engine_type, why in ENGINE_GROUP_FALLBACK.items():
        assert len(why) > 20, f"{engine_type}: an unmapped type needs a real justification"


def test_a_refused_class_carries_its_reason_and_is_not_also_a_feature():
    """Plan F0: a class that stays out does so as a STRUCTURED status. A
    refusal with no reason is a silence, and one that is also a feature is a
    contradiction."""
    from openchem.chem.feature_vocabulary import EXCLUDED_CLASSES

    assert EXCLUDED_CLASSES, "the refused classes are the point of the table"
    labels = {label.lower() for f in FEATURES for label in f.labels.values()}
    for name, why in EXCLUDED_CLASSES.items():
        assert len(why) > 60, f"{name}: a refusal needs a real reason"
        assert name.lower() not in labels, f"{name} is refused and also a feature"


def test_a_blue_book_definition_says_the_gold_book_has_none():
    """The Gold Book is the normative source; falling back is allowed only
    where it is silent, and the note must say it was checked."""
    for feature in FEATURES:
        if feature.definition.source is DefinitionSource.BLUE_BOOK:
            assert "Gold Book has no" in feature.operationalisation, feature.feature_id
