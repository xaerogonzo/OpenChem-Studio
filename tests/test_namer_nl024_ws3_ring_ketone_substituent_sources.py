"""NL-024 (WS3): Blue Book sources for ring-ketone substituent hydrogen spelling (round 80 / D-364).

Some curated diketone rings cited as ``-yl`` substituents use full ``…-dihydro-…H-`` blocks (D-364);
quinazoline-2,4-dione keeps inline ``1H,3H`` added-hydrogen locants (round 80 KEPT row). Both match P-58.2
patterns the book gives for parent PINs vs detachable hydro spelling on substituent prefixes.

Engine pins: ``tests/test_namer_round80_ring_as_substituent_oxo_forms_cation_esters_and_a_fusion_label.py``.
Page numbers: Blue Book **V3** (``benchmarks/naming/BLUEBOOK_V3.md``).
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (rule, V3 pdf page, note) — pages ascending
NL_024_SOURCES = (
    (
        "P-58.2.2.2",
        472,
        "Diazine diones such as `pyrimidine-4,6(1H,5H)-dione (PIN)`; quinazoline-2,4-dione substituents "
        "mirror this `1H,3H` added-hydrogen spelling in the engine.",
    ),
    (
        "P-58.2.4",
        477,
        "Substituent prefixes after indicated/added hydrogen: e.g. `1,3-dioxo-1,3-dihydro-2H-isoindole-2,5-diyl` "
        "(dioxo with explicit dihydro positions on the prefix).",
    ),
    (
        "P-58.2.5",
        478,
        "Detachable `dihydro` / `dioxo-…-dihydro` prefixes are the alternative to parenthetical added hydrogen; "
        "benzoxazinedione substituents use this when oxo prefixes must not follow a misplaced `2H-` (D-364).",
    ),
    (
        "P-64.2.2.2.2",
        557,
        "Cyclic ketone PINs admit `2,3-dihydro-1H-inden-1-one` beside `indan-1-one (PIN)`; substituent spelling "
        "follows the same P-58.2 choice for the prefix, not the parent suffix form.",
    ),
)

ENGINE_PINS = (
    (
        "3,1-benzoxazinedione substituent (D-364)",
        "O=C(O)Cc1ccc2[nH]c(=O)oc(=O)c2c1",
        "(2,4-dioxo-1,4-dihydro-2H-3,1-benzoxazin-6-yl)acetic acid",
        "Hydro-block prefix; pre-D-364 `2H-2,4-dioxo-1H-…` was unreadable by OPSIN.",
    ),
    (
        "quinazoline-2,4-dione substituent (KEPT)",
        "O=C(O)Cc1ccc2[nH]c(=O)[nH]c(=O)c2c1",
        "(2,4-dioxo-1H,3H-quinazolin-6-yl)acetic acid",
        "Added-hydrogen inline style; OPSIN read-back matches (round 80).",
    ),
    (
        "pyranoquinolinedione substituent (D-364)",
        "O=C(O)Cc1cc(=O)c2cc3c(=O)cc[nH]c3cc2o1",
        "(4,6-dioxo-4,6-dihydro-9H-pyrano[3,2-g]quinolin-2-yl)acetic acid",
        "Same hydro-block pattern as benzoxazine on a fused parent.",
    ),
)

PARENT_CONTRAST = (
    (
        "benzoxazinedione as parent suffix",
        "Cc1ccc2[nH]c(=O)oc(=O)c2c1",
        "6-methyl-2H-3,1-benzoxazine-2,4(1H)-dione",
        "Parent keeps parenthetical `(1H)` on the suffix; substituent uses dihydro (P-58.2.4/5).",
    ),
)


def test_nl024_four_book_passages_are_recorded():
    assert len(NL_024_SOURCES) == 4
    pages = [row[1] for row in NL_024_SOURCES]
    assert pages == sorted(pages)


def test_nl024_three_substituent_pins_are_documented():
    assert len(ENGINE_PINS) == 3


@pytest.mark.parametrize("label,smiles,expected,_note", ENGINE_PINS, ids=[r[0] for r in ENGINE_PINS])
def test_nl024_substituent_spelling_pins(label, smiles, expected, _note):
    del label, _note
    assert name_smiles(smiles) == expected


@pytest.mark.parametrize("label,smiles,expected,_note", PARENT_CONTRAST, ids=[r[0] for r in PARENT_CONTRAST])
def test_nl024_parent_suffix_contrast(label, smiles, expected, _note):
    del label, _note
    assert name_smiles(smiles) == expected


def _inchikey(smiles: str) -> str:
    return inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected,_note", ENGINE_PINS, ids=[r[0] for r in ENGINE_PINS])
def test_nl024_substituent_pins_read_back(label, smiles, expected, _note):
    from py2opsin import py2opsin

    del label, _note
    assert name_smiles(smiles) == expected
    back = py2opsin(expected)
    assert back
    assert _inchikey(back) == _inchikey(smiles)