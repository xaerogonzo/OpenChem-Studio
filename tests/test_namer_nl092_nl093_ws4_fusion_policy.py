"""WS4 P3: NL-092 and NL-093 — fusion/multiparent policy pins.

Programme disposition (2026-11-15): **closed** by pinning what the engine does today: multiparent
names where built (round 77), von Baeyer fallbacks when fusion declines, retained parents (including
helicenes and full hydro phenanthrene), and an explicit refusal for three-parent systems still outside
the constructor class.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.ring_naming import fusion_general as fg
from openchem.vendor.iupac_namer.ring_naming.fusion_orientation import Unsupported

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

NAMED = [
    (
        "NL-093 multiparent (P-25.3.4.1.3)",
        "c1cc2cc3cocc3cc2o1",
        "benzo[1,2-b:4,5-c']difuran",
    ),
    (
        "NL-093 two furans on two pyridines",
        "c1cnc2c(c1)oc1cccnc12",
        "furo[3,2-b:4,5-b']dipyridine",
    ),
    (
        "NL-093 hydro phenanthrene via von Baeyer",
        "C1=CC2=CC=CC=C2C3CCCCC13",
        "tricyclo[8.4.0.0^{2,7}]tetradeca-1(14),8,10,12-tetraene",
    ),
    (
        "NL-093 full hydro phenanthrene retained",
        "c1ccc2c(c1)CCC3CCCCC23",
        "1,2,3,4,4a,9,10,10a-octahydrophenanthrene",
    ),
    (
        "NL-092 second-order fusion -> von Baeyer",
        "C1=CC2=c3ccncc3=NC2=C1",
        "7,10-diazatricyclo[6.4.0.0^{2,6}]dodeca-1,3,5,7,9,11-hexaene",
    ),
    (
        "NL-092 interior heteroatom (P-25.3.3.2) -> von Baeyer",
        "C1=CC2=CC=C3C=CCC4=C3N2C(=C1)C=C4",
        "15-azatetracyclo[6.6.2.0^{4,16}.0^{11,15}]hexadeca-1,3,5,8(16),9,11,13-heptaene",
    ),
    (
        "NL-092 peri-fused aza system (D-353)",
        "c1cc2ccc3ncc4ncc5cnc6ccc1c1c2c3c4c5c61",
        "2,5,9-triazaheptacyclo[14.6.2.0^{4,21}.0^{7,20}.0^{10,19}.0^{13,18}.0^{17,22}]tetracosa-1(23),2,4,6,8,10,12,14,16(24),17,19,21-dodecaene",
    ),
    (
        "NL-092 helicene retained parent",
        "c1ccc2c(c1)ccc1ccc3ccc4ccc5ccccc5c4c3c12",
        "hexahelicene",
    ),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[p[0] for p in NAMED])
def test_fusion_policy_engine_name(label, smiles, expected):
    del label
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[p[0] for p in NAMED])
def test_fusion_policy_round_trips(label, smiles, expected):
    del label
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, (smiles, expected)
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == inchi.MolToInchiKey(
        Chem.MolFromSmiles(smiles)
    )


def test_nl092_three_parent_multiparent_still_refused_by_fusion():
    smiles = "c1coc2c1c1ccoc1c1ccoc21"
    mol = Chem.MolFromSmiles(smiles)
    with pytest.raises(Unsupported) as exc:
        fg.name_fusion(mol, mol.GetRingInfo().AtomRings())
    assert exc.value.code == Unsupported.NEEDS_UNBUILT_CONSTRUCTION
    assert name_smiles(smiles).startswith("[NAMING ERROR:")


def test_nl092_fusion_constructor_declines_helicene_parent():
    smiles = "c1ccc2c(c1)ccc1ccc3ccc4ccc5ccccc5c4c3c12"
    mol = Chem.MolFromSmiles(smiles)
    with pytest.raises(Unsupported) as exc:
        fg.name_fusion(mol, mol.GetRingInfo().AtomRings())
    assert exc.value.code == Unsupported.OUTSIDE_CLASS
    assert name_smiles(smiles) == "hexahelicene"