"""Naming round 94 (NL-011 bucket A): multicomponent dispiro locants on von-Baeyer partners.

Seed 8901 chains #10, #16 and #17 nested because ``_spiro_locants_for_component`` had no
locants when the component's ``NamedParent`` carried empty ``numbering_options`` on a
bridged von-Baeyer partner. Fix: ``compute_vb_numberings`` in the multicomponent fallback
(same pin as D-381/D-382 in the articulation-split path).
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

PINNED = [
    (
        "NL-011 seed8901 #10 three bicyclic joints",
        "C1C2CC1C1(C2)CC2CC1C1(C2)C2CC1C2",
        "dispiro[bicyclo[2.1.1]hexane-2,6'-bicyclo[2.2.1]heptane-2',2''-bicyclo[1.1.1]pentane]",
    ),
    (
        "NL-011 seed8901 #16 adamantane middle",
        "C1CC2CCC1CC21C2CC3CC(C2)C2(CC4CC2C4)C1C3",
        "dispiro[bicyclo[2.1.1]hexane-2,4'-adamantane-2',2''-bicyclo[2.2.2]octane]",
    ),
    (
        "NL-011 seed8901 #17 azatricyclo terminus",
        "C1CC2C3(CC1CC21C2CC4CC(C2)C41)C1CNC2CC(C1)CC3C2",
        "dispiro[tricyclo[3.2.1.0^{3,6}]octane-7,2'-bicyclo[2.2.2]octane-6',7''-4-azatricyclo[4.3.1.1^{3,8}]undecane]",
    ),
]


@pytest.mark.parametrize("label,smiles,expected", PINNED, ids=[r[0] for r in PINNED])
def test_flat_dispiro_name(label, smiles, expected):
    got = name_smiles(smiles)
    assert got == expected
    assert "spiro[spiro" not in got


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", PINNED, ids=[r[0] for r in PINNED])
def test_opsin_read_back(label, smiles, expected):
    from py2opsin import py2opsin

    assert name_smiles(smiles) == expected
    back = py2opsin(expected)
    assert back, expected
    want = inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == want
