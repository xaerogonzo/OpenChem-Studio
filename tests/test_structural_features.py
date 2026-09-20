"""The v2 detector against the coverage matrix committed before it (B0).

Every expectation here comes from `tests/fixtures/structural_features/
coverage.toml`, whose atom-map numbers mark the expected atoms and roles; the
detector sees the same molecule with the maps stripped. Nothing in this file
states what a feature matches -- if a pattern is wrong, the fixture it was
written against says so.
"""

from __future__ import annotations

import random
import tomllib
from collections import Counter
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.chem.feature_vocabulary import (
    FEATURE_BY_ID,
    FEATURES,
    ChargeState,
    ObjectTreatment,
    Projection,
)
from openchem.chem.structural_features import (
    SPECS,
    detect_features,
    exclusion_violations,
    project,
)
from tests.test_feature_vocabulary import expected_instances

COVERAGE = Path(__file__).resolve().parent / "fixtures" / "structural_features" / "coverage.toml"
_DATA = tomllib.loads(COVERAGE.read_text(encoding="utf-8"))
ROWS = _DATA["feature"]
OVERLAPS = _DATA["overlap"]


def _stripped(smiles: str) -> Chem.Mol:
    """The fixture's own molecule with its map numbers cleared.

    NOT a round trip through SMILES: `MolToSmiles(canonical=False)` still
    reorders atoms around ring closures, which moved every index of a tosylate
    fixture and read as a detector defect (measured)."""
    mol = Chem.MolFromSmiles(smiles)
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    return mol


def _combined(first: Chem.Mol, second: Chem.Mol) -> Chem.Mol:
    """`CombineMols` returns a molecule with no ring perception, which RDKit
    refuses to query; the detector's precondition is a sanitized molecule."""
    mol = Chem.CombineMols(first, second)
    Chem.SanitizeMol(mol)
    return mol


def _instances(smiles: str, feature_id: str):
    return [f for f in detect_features(_stripped(smiles)) if f.feature_id == feature_id]


def _as_expected(feature) -> dict[int, int]:
    roles = FEATURE_BY_ID[feature.feature_id].roles
    return {atom: roles.index(role) + 1 for atom, role in feature.roles}


def test_every_feature_has_exactly_one_spec():
    assert set(SPECS) == {f.feature_id for f in FEATURES}


def _positive_cases():
    for row in ROWS:
        for smiles in row.get("positive", []):
            yield pytest.param(row["id"], smiles, ChargeState.NEUTRAL, id=f"{row['id']}|{smiles}")
        for charged in row.get("charged", []):
            yield pytest.param(row["id"], charged["smiles"], ChargeState(charged["state"]),
                               id=f"{row['id']}|{charged['smiles']}")


@pytest.mark.parametrize("feature_id,smiles,state", list(_positive_cases()))
def test_a_positive_yields_exactly_the_marked_instances(feature_id, smiles, state):
    """Atoms AND roles, and no instance the fixture did not mark: an extra
    detection fails as surely as a missing one."""
    got = sorted((_as_expected(f) for f in _instances(smiles, feature_id)),
                 key=lambda d: sorted(d))
    want = sorted(expected_instances(smiles), key=lambda d: sorted(d))
    assert got == want
    for feature in _instances(smiles, feature_id):
        assert feature.charge_state is state
        assert feature.label  # a label for every permitted state


def _negative_cases():
    for row in ROWS:
        for negative in row["negative"]:
            yield pytest.param(row["id"], negative["smiles"], id=f"{row['id']}|{negative['smiles']}")


@pytest.mark.parametrize("feature_id,smiles", list(_negative_cases()))
def test_a_negative_yields_no_instance(feature_id, smiles):
    assert _instances(smiles, feature_id) == []


@pytest.mark.parametrize("row", ROWS, ids=lambda r: r["id"])
def test_a_counter_ion_changes_the_component_and_nothing_else(row):
    """Generated component obligations (the matrix does not restate them):
    a counter-ion placed FIRST moves the group to component 1 with every atom
    index shifted by one, and a second copy of the molecule is a second,
    separate set of instances, in component order."""
    smiles = (row.get("positive") or [c["smiles"] for c in row["charged"]])[0]
    mol = _stripped(smiles)
    base = [f for f in detect_features(mol) if f.feature_id == row["id"]]

    salted = [f for f in detect_features(_combined(Chem.MolFromSmiles("[Na+]"), mol))
              if f.feature_id == row["id"]]
    assert [f.component for f in salted] == [1] * len(base)
    assert sorted(sorted(a - 1 for a in f.atoms) for f in salted) == sorted(sorted(f.atoms) for f in base)

    doubled = [f for f in detect_features(_combined(mol, mol))
               if f.feature_id == row["id"]]
    assert [f.component for f in doubled] == [0] * len(base) + [1] * len(base)


@pytest.mark.parametrize("fixture", OVERLAPS, ids=lambda f: f["relation"])
def test_an_overlap_fixture_is_detected_and_projected_as_declared(fixture):
    features = detect_features(Chem.MolFromSmiles(fixture["smiles"]))
    assert Counter(f.feature_id for f in features) == Counter(fixture["detected"])

    fg = project(features, Projection.FUNCTIONAL_GROUPS)
    shown = [p.feature.feature_id for p in fg if p.treatment is not ObjectTreatment.HIDDEN]
    assert Counter(shown) == Counter(fixture["functional_groups"])

    fc = project(features, Projection.FRAGMENT_COUNTS)
    counted = Counter(p.feature.feature_id for p in fc if p.treatment is not ObjectTreatment.HIDDEN)
    assert counted == Counter(fixture["fragment_counts"])

    inspector = project(features, Projection.ATOM_INSPECTOR)
    assert all(p.treatment is not ObjectTreatment.HIDDEN for p in inspector), "the inspector hides nothing"
    non_primary = [p.feature.feature_id for p in inspector
                   if p.treatment is ObjectTreatment.SHOWN_NON_PRIMARY]
    assert Counter(non_primary) == Counter(fixture["inspector_non_primary"])


@pytest.mark.parametrize("fixture", OVERLAPS, ids=lambda f: f["relation"])
def test_a_projection_does_not_depend_on_instance_order(fixture):
    """An instance hit by two relations takes the STRONGER treatment, whichever
    arrives first. In declared order the stronger one always happened to come
    last, so "take the last" passed every fixture (mutation, measured)."""
    features = detect_features(Chem.MolFromSmiles(fixture["smiles"]))
    for projection in Projection:
        forward = {p.feature.identity: p.treatment for p in project(features, projection)}
        backward = {p.feature.identity: p.treatment for p in project(features[::-1], projection)}
        assert forward == backward, projection


def _every_fixture_smiles():
    for row in ROWS:
        yield from row.get("positive", [])
        yield from (c["smiles"] for c in row.get("charged", []))
        yield from (n["smiles"] for n in row["negative"])
    yield from (f["smiles"] for f in OVERLAPS)


def test_no_fixture_violates_an_exclusion():
    """EXCLUDES is an invariant: two features that cannot both describe the
    same atoms never both do, on any molecule the matrix holds."""
    for smiles in _every_fixture_smiles():
        assert exclusion_violations(detect_features(_stripped(smiles))) == (), smiles


def test_detection_does_not_depend_on_atom_order():
    """The same structure renumbered gives the same instances, mapped through
    the renumbering, in the same order -- over every fixture, five shuffles
    each, from a fixed seed."""
    rng = random.Random(20260918)
    for smiles in _every_fixture_smiles():
        mol = _stripped(smiles)
        base = detect_features(mol)
        for _ in range(5):
            order = list(range(mol.GetNumAtoms()))
            rng.shuffle(order)
            shuffled = Chem.RenumberAtoms(mol, order)
            new_of_old = {old: new for new, old in enumerate(order)}
            got = detect_features(shuffled)
            want = sorted(
                ((f.feature_id, tuple(sorted(new_of_old[a] for a in f.atoms)), f.charge_state)
                 for f in base)
            )
            assert sorted((f.feature_id, tuple(sorted(f.atoms)), f.charge_state) for f in got) == want, smiles
            assert [f.feature_id for f in got] == [f.feature_id for f in base], smiles


# --- the naming engine as a second detector --------------------------------------

_CORPORA = [
    Path(__file__).resolve().parents[1] / "benchmarks" / "naming" / name
    for name in ("corpus.json", "heldout.json")
]


def _corpus_smiles() -> list[str]:
    import json

    out = []
    for path in _CORPORA:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("molecules", data.get("entries", []))
        out.extend(item["smiles"] for item in items)
    return out


def test_the_engine_and_v2_agree_on_the_naming_corpora():
    """Every group the naming engine perceives (227 molecules) lands on a v2
    instance its map allows -- or on a DECLARED disagreement, and every
    declared disagreement still occurs.

    Intersection, not containment: the engine anchors an alcohol, a phenol or
    a carbamate on a CARBON, and v2 marks the heteroatoms (Ertl's marking), so
    the two atom sets overlap without either containing the other. Perception
    only, no naming pass: 1.6 s for the whole population, measured.
    """
    from openchem.chem.feature_vocabulary import ENGINE_DISAGREEMENTS, ENGINE_GROUP_MAP
    from openchem.chem.structure_annotation import perceive

    undeclared, used = [], set()
    for smiles in _corpus_smiles():
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            continue
        features = detect_features(mol)
        annotation = perceive(mol)
        for group in list(annotation.groups) + list(annotation.features):
            targets = ENGINE_GROUP_MAP.get(group.type)
            if targets is None:
                continue  # ENGINE_GROUP_FALLBACK: no feature claims it, by declaration
            touching = [f for f in features if f.atoms & group.atoms]
            if any(f.feature_id in targets for f in touching):
                continue
            keys = {(group.type, f.feature_id) for f in touching} & set(ENGINE_DISAGREEMENTS)
            if not touching and (group.type, None) in ENGINE_DISAGREEMENTS:
                keys = {(group.type, None)}
            if keys:
                used |= keys
                continue
            undeclared.append(
                f"{smiles}: engine {group.type} on {sorted(group.atoms)}, v2 has "
                f"{[(f.feature_id, sorted(f.atoms)) for f in touching]}"
            )
    assert not undeclared, "\n".join(undeclared)
    assert used == set(ENGINE_DISAGREEMENTS), (
        f"declared disagreements that no longer occur: {set(ENGINE_DISAGREEMENTS) - used}"
    )


#: The engine types v3 moved from the unmapped table into the map, each with
#: one molecule that HAS it. The corpus test above cannot see a type no corpus
#: molecule contains, and a wrong mapping for one passed a mutation check (the
#: `thial` -> thioketone swap) until this existed.
#:
#: `cyanato` and `thiocyanato` were ABSENT here until naming round 6: the engine
#: perceived methyl cyanate and methyl thiocyanate as a plain `nitrile` (its own
#: log: "Unknown FG overlap: 'nitrile' vs 'cyanato' ... Treating as ambiguity"),
#: so neither type ever surfaced and their mapping could not be exercised. Round 6
#: subsumes the nitrile, so they can fire, and a wrong mapping for either would
#: now fail here.
_V3_ENGINE_EXAMPLES = {
    "cyanato": "COC#N",
    "thiocyanato": "CSC#N",
    "carbothioic_O_acid": "CC(=S)O",
    "carbothioic_S_acid": "CC(=O)S",
    "carbodithioic_acid": "CC(=S)S",
    "thionocarbamate": "CNC(=S)OC",
    "carbamothioate": "CNC(=O)SC",
    "dithiocarbamate": "CNC(=S)SC",
    "thial": "CC=S",
    "sulfinic_acid": "CS(=O)O",
    "sulfinamide": "CS(N)=O",
    "sulfenate": "CS[O-]",
}


@pytest.mark.parametrize("engine_type,smiles", sorted(_V3_ENGINE_EXAMPLES.items()))
def test_a_v3_engine_type_lands_on_the_feature_its_map_names(engine_type, smiles):
    from openchem.chem.feature_vocabulary import ENGINE_GROUP_MAP
    from openchem.chem.structure_annotation import perceive

    mol = Chem.MolFromSmiles(smiles)
    annotation = perceive(mol)
    groups = [g for g in list(annotation.groups) + list(annotation.features)
              if g.type == engine_type]
    assert groups, f"{smiles}: the engine perceives no {engine_type}, so the example is wrong"
    features = detect_features(mol)
    for group in groups:
        touching = {f.feature_id for f in features if f.atoms & group.atoms}
        assert touching & set(ENGINE_GROUP_MAP[engine_type]), (
            f"{engine_type} on {smiles} touches {sorted(touching)}, "
            f"not {ENGINE_GROUP_MAP[engine_type]}"
        )
