"""An O- or S-bonded cyano group is cyanato / thiocyanato, and NOT a nitrile.

Found by the functional-groups v3 cross-check (naming round 6): the engine's
nitrile pattern is blind to what the cyano carbon is bonded to, so it and the
prefix-only `cyanato` / `thiocyanato` groups overlapped on the C#N atoms. The
engine logged "Unknown FG overlap ... Treating as ambiguity" and the nitrile
won, so methyl thiocyanate was PERCEIVED as a nitrile of methane. The
subsumption entries in `perception/fg_detection.py` are what these tests pin;
they are observable in perception even where the names do not change.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.structure_annotation import perceive


def _types(smiles: str) -> set[str]:
    annotation = perceive(Chem.MolFromSmiles(smiles))
    return {g.type for g in list(annotation.groups) + list(annotation.features)}


@pytest.mark.parametrize("smiles,expected", [
    ("COC#N", "cyanato"),
    ("c1ccccc1OC#N", "cyanato"),
    ("CSC#N", "thiocyanato"),
    ("CC(C)SC#N", "thiocyanato"),
])
def test_a_cyanic_ester_is_its_own_group_and_not_a_nitrile(smiles, expected):
    types = _types(smiles)
    assert expected in types, f"{smiles}: perceived {sorted(types)}"
    assert "nitrile" not in types, f"{smiles}: the nitrile pattern claimed the cyano group"


@pytest.mark.parametrize("smiles", ["CC#N", "c1ccccc1C#N", "N#CCC(=O)O"])
def test_a_true_nitrile_is_still_a_nitrile(smiles):
    """The converse: subsumption is keyed on the cyanic groups, so a cyano
    group on carbon is untouched."""
    types = _types(smiles)
    assert "nitrile" in types and not types & {"cyanato", "thiocyanato"}
