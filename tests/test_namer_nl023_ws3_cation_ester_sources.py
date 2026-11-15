"""NL-023 (WS3): Blue Book sources for cation parent over ester parent (round 80 / D-365).

Engine pins live in ``tests/test_namer_round80_ring_as_substituent_oxo_forms_cation_esters_and_a_fusion_label.py``.
Page numbers are from **Blue Book V3** (``benchmarks/naming/BLUEBOOK_V3.md``); adjudication still pins V2.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (rule, V3 pdf page, note) — pages ascending (V3 PDF)
NL_023_SOURCES = (
    (
        "P-66 (contrast)",
        709,
        "Ester nomenclature on neutral alcohol parents; contrast case kept in round 80 KEPT row `oxan-4-yl acetate`.",
    ),
    (
        "P-73 (chromenylium)",
        820,
        "Retained chromenylium parent; substituent at position 2 is cited as a prefix on the cation, not `chromen-2-yl acetate`.",
    ),
    (
        "P-73.7",
        826,
        "Choice of parent structure for ions: a retained cation parent outranks an ester name built on the neutral ring.",
    ),
)

ENGINE_PINS = (
    (
        "chromenylium acetate (D-365)",
        "CC(=O)Oc1ccc2ccccc2[o+]1",
        "2-(acetyloxy)chromenylium",
        "Cation parent with acyloxy prefix, not chromen-2-yl acetate.",
    ),
    (
        "pyrylium acetate",
        "CC(=O)Oc1cc[o+]cc1",
        "4-(acetyloxy)pyrylium",
        "Same seniority pattern on a six-membered O cation.",
    ),
    (
        "neutral ring ester (contrast)",
        "CC(=O)OC1CCOCC1",
        "oxan-4-yl acetate",
        "No cation: ester substituent style remains correct.",
    ),
)


def test_nl023_three_book_passages_are_recorded():
    assert len(NL_023_SOURCES) == 3
    pages = [row[1] for row in NL_023_SOURCES]
    assert pages == sorted(pages)


def test_nl023_engine_pins_are_documented():
    assert len(ENGINE_PINS) == 3


@pytest.mark.parametrize("label,smiles,expected,_note", ENGINE_PINS, ids=[r[0] for r in ENGINE_PINS])
def test_nl023_engine_spelling_pins(label, smiles, expected, _note):
    del label, _note
    assert name_smiles(smiles) == expected


def _inchikey(smiles: str) -> str:
    return inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected,_note", ENGINE_PINS, ids=[r[0] for r in ENGINE_PINS])
def test_nl023_engine_pins_read_back(label, smiles, expected, _note):
    from py2opsin import py2opsin

    del label, _note
    assert name_smiles(smiles) == expected
    back = py2opsin(expected)
    assert back
    assert _inchikey(back) == _inchikey(smiles)