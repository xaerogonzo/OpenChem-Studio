"""WS5 P3: NL-032..NL-042 — round-5 `OPEN` defect rows pinned at today's engine names.

Programme disposition (2026-11-16): **closed** without pursuing Blue Book PINs. Each
SMILES still xfails in ``tests/test_namer_known_defects.py`` until the book target is
emitted. NL-042 also guards against the former wrong multiplicative name (see
``test_a_symmetric_carbodiimide_is_no_longer_a_wrong_molecule`` in that file).
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

PINS = [
    (
        "NL-032 D-088b hydrazine ester",
        "CCOC(=O)NN",
        "(ethoxycarbonyl)hydrazine",
    ),
    (
        "NL-033 D-088d hydrazinecarbonyl prefix",
        "O=C(NNC)c1ccc(C(=O)O)cc1",
        "4-[(2-methylhydrazinyl)(oxo)methyl]benzoic acid",
    ),
    (
        "NL-034 D-088f oxybisamine central group",
        "CN(C)ON(C)C",
        "{[(dimethylamino)oxy](methyl)amino}methane",
    ),
    (
        "NL-035 D-088h diphenol linker",
        "Oc1ccc(OCC(C)COc2ccc(O)cc2)cc1",
        "4-[3-(4-hydroxyphenoxy)-2-methylpropoxy]phenol",
    ),
    (
        "NL-036 D-088i tris(silyl)benzene",
        "[SiH3]c1cc([SiH3])cc([SiH3])c1",
        "[3,5-bis(silyl)phenyl]silane",
    ),
    (
        "NL-037 D-088j unsymmetrical tribenzoic",
        "OC(=O)c1ccc(CC(c2ccc(C(O)=O)cc2)c2ccc(C(O)=O)cc2)cc1",
        "4-[1,2-bis(4-carboxyphenyl)ethyl]benzoic acid",
    ),
    (
        "NL-038 D-089s disiloxanediol",
        "C[Si](C)(O)O[Si](C)(C)O",
        "1,3-dihydroxy-1,1,3,3-tetramethyldisiloxane",
    ),
    (
        "NL-039 D-089u disilaazane",
        "[SiH3]N[SiH3]",
        "disilaazane",
    ),
    (
        "NL-040 D-090b trisiloxane skeletal count",
        "C[SiH2]O[SiH2]O[SiH3]",
        "2,4-dioxa-1,3,5-trisilahexane",
    ),
    (
        "NL-041 D-089v phosphoramidocyanidate",
        "CCOP(=O)(C#N)N(C)C",
        "(dimethylamino)(ethoxy)(oxo)phosphanecarbonitrile",
    ),
    (
        "NL-042 D-130 DCC carbodiimide",
        "C(=NC1CCCCC1)=NC1CCCCC1",
        "{[(cyclohexylimino)methylidene]amino}cyclohexane",
    ),
]

D130_WRONG_MOLECULE = "1,1'-[methylenebis(azanediyl)]dicyclohexane"


@pytest.mark.parametrize("label,smiles,expected", PINS, ids=[p[0] for p in PINS])
def test_engine_keeps_documented_name(label, smiles, expected):
    del label
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", PINS, ids=[p[0] for p in PINS])
def test_documented_name_round_trips(label, smiles, expected):
    del label
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, (smiles, expected)
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == inchi.MolToInchiKey(
        Chem.MolFromSmiles(smiles)
    )


def test_nl042_never_emits_wrong_multiplicative_dcc():
    assert name_smiles("C(=NC1CCCCC1)=NC1CCCCC1") != D130_WRONG_MOLECULE