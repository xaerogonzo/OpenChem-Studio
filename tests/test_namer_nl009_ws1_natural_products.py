"""NL-009 (WS1): re-measure the four round-24 natural products on the current engine (2026-11-08).

Round 25 fixed the stereo paths (D-183..D-185); round 89 unanchored stripping further protects bridged R/S.
Classification:
  * galantamine and ibogaine — exact names, full OPSIN read-back;
  * atropine and scopolamine — correct but underspecified (pseudoasymmetric centre omitted; app note).
The ``bis([1,3]dioxolo)pyran`` OPSIN-limit case stays on NL-057, not these four structures.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem
from rdkit.Chem import inchi

from openchem.chem.naming_providers import derived_name_for_structure

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# From ``tests/test_round25_stereo_and_esters.py`` (re-measured 2026-11-08).
CASES = (
    (
        "galantamine",
        "COc1ccc2c3c1O[C@H]1C[C@@H](O)C=C[C@@]31CCN(C)C2",
        "(4aS,6R,8aS)-3-methoxy-11-methyl-4a,5,9,10,11,12-hexahydro-6H-[1]benzofuro[3a,3,2-ef][2]benzazepin-6-ol",
        False,
    ),
    (
        "ibogaine",
        "CC[C@H]1C[C@H]2C[C@@H]3[C@H]1N(C2)CCc1c3[nH]c2ccc(OC)cc12",
        "(6R,6aS,7S,9S)-7-ethyl-2-methoxy-5,6,6a,7,8,9,10,12,13-nonahydro-6,9-methanopyrido[1',2':1,2]azepino[4,5-b]indole",
        False,
    ),
    (
        "atropine",
        "CN1[C@H]2CC[C@@H]1C[C@@H](C2)OC(=O)C(CO)c1ccccc1",
        "(1R,5S)-8-methyl-8-azabicyclo[3.2.1]octan-3-yl 3-hydroxy-2-phenylpropanoate",
        True,
    ),
    (
        "scopolamine",
        "CN1[C@H]2C[C@H](OC(=O)[C@H](CO)c3ccccc3)C[C@@H]1[C@H]1O[C@@H]21",
        "(1R,2R,4S,5S)-9-methyl-3-oxa-9-azatricyclo[3.3.1.0^{2,4}]nonan-7-yl (2S)-3-hydroxy-2-phenylpropanoate",
        True,
    ),
)


@pytest.mark.parametrize("label,smiles,expected_name,partial_stereo", CASES, ids=[c[0] for c in CASES])
def test_nl009_name_matches_round25_pins(label, smiles, expected_name, partial_stereo):
    del label
    mol = Chem.MolFromSmiles(smiles)
    result = derived_name_for_structure(mol)
    assert result.name == expected_name
    assert bool(result.note) is partial_stereo
    if partial_stereo:
        assert "does not express stereochemistry" in (result.note or "")


EXACT_OPSIN_CASES = tuple(row for row in CASES if not row[3])
PARTIAL_STEREO_CASES = tuple(row for row in CASES if row[3])


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected_name,partial_stereo", EXACT_OPSIN_CASES, ids=[c[0] for c in EXACT_OPSIN_CASES])
def test_nl009_opsin_read_back_full_key(label, smiles, expected_name, partial_stereo):
    del label, partial_stereo
    from py2opsin import py2opsin

    mol = Chem.MolFromSmiles(smiles)
    result = derived_name_for_structure(mol)
    assert result.name == expected_name
    want = inchi.MolToInchiKey(mol)
    back = py2opsin(result.name)
    assert back, expected_name
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == want


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected_name,partial_stereo", PARTIAL_STEREO_CASES, ids=[c[0] for c in PARTIAL_STEREO_CASES])
def test_nl009_opsin_parses_but_does_not_pin_pseudoasymmetric_stereo(label, smiles, expected_name, partial_stereo):
    """Tropanes: OPSIN read-back is not the pin oracle when the name omits ``r``/``s`` (round 25)."""
    del label, partial_stereo
    from py2opsin import py2opsin

    mol = Chem.MolFromSmiles(smiles)
    result = derived_name_for_structure(mol)
    assert result.name == expected_name
    back = py2opsin(result.name)
    assert back
    got = inchi.MolToInchiKey(Chem.MolFromSmiles(back))
    want = inchi.MolToInchiKey(mol)
    assert got != want
    assert got[:14] == want[:14]
