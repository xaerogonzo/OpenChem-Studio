"""WS4 P3: NL-030 and NL-031 — fusion PINs not built; von Baeyer fallbacks read back.

Book targets (D-086b/c): `cyclopenta[4,5]pyrrolo[2,3-c]pyridine` (p. 239) and
`6H-quinolizino[3,4,5,6-ija]quinoline` (p. 223). Programme disposition (2026-11-15):
**closed** on the emitted von Baeyer names, not on fusion construction.

The same two defects stay in ``OPEN`` as ``xfail(strict=True)`` until the book
PIN is emitted; the fourth field of each row is the pinned von Baeyer fallback.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

BOOK_FUSION = [
    (
        "D-086b cyclopenta pyrrolopyridine",
        "C1=CC2=c3ccncc3=NC2=C1",
        "cyclopenta[4,5]pyrrolo[2,3-c]pyridine",
    ),
    (
        "D-086c quinolizino quinoline",
        "C1=CC2=CC=C3C=CCC4=C3N2C(=C1)C=C4",
        "6H-quinolizino[3,4,5,6-ija]quinoline",
    ),
]

PINS = [
    (
        "NL-030 second-order fusion (D-086b)",
        BOOK_FUSION[0][1],
        "7,10-diazatricyclo[6.4.0.0^{2,6}]dodeca-1,3,5,7,9,11-hexaene",
    ),
    (
        "NL-031 interior heteroatom (D-086c)",
        BOOK_FUSION[1][1],
        "15-azatetracyclo[6.6.2.0^{4,16}.0^{11,15}]hexadeca-1,3,5,8(16),9,11,13-heptaene",
    ),
]


@pytest.mark.parametrize("label,smiles,expected", PINS, ids=[p[0] for p in PINS])
def test_engine_emits_documented_vonbaeyer_name(label, smiles, expected):
    del label
    assert name_smiles(smiles) == expected


@pytest.mark.parametrize("label,smiles,book_pin", BOOK_FUSION, ids=[p[0] for p in BOOK_FUSION])
def test_open_row_book_fusion_pin_not_emitted(label, smiles, book_pin):
    """OPEN xfails stay until this assertion would pass (``test_open_defect_still_open``)."""
    del label
    assert name_smiles(smiles) != book_pin


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