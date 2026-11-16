"""WS4 P3: NL-030 and NL-031 — fusion PINs not built; von Baeyer fallbacks read back.

Book targets (D-086b/c): `cyclopenta[4,5]pyrrolo[2,3-c]pyridine` (p. 239) and
`6H-quinolizino[3,4,5,6-ija]quinoline` (p. 223). Programme disposition (2026-11-15):
**closed** on the emitted von Baeyer names, not on fusion construction.
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
        "NL-030 second-order fusion (D-086b)",
        "C1=CC2=c3ccncc3=NC2=C1",
        "7,10-diazatricyclo[6.4.0.0^{2,6}]dodeca-1,3,5,7,9,11-hexaene",
    ),
    (
        "NL-031 interior heteroatom (D-086c)",
        "C1=CC2=CC=C3C=CCC4=C3N2C(=C1)C=C4",
        "15-azatetracyclo[6.6.2.0^{4,16}.0^{11,15}]hexadeca-1,3,5,8(16),9,11,13-heptaene",
    ),
]


@pytest.mark.parametrize("label,smiles,expected", PINS, ids=[p[0] for p in PINS])
def test_engine_emits_documented_vonbaeyer_name(label, smiles, expected):
    del label
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", PINS, ids=[p[0] for p in PINS])
def test_vonbaeyer_name_round_trips(label, smiles, expected):
    del label
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, (smiles, expected)
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == inchi.MolToInchiKey(
        Chem.MolFromSmiles(smiles)
    )