"""NL-022 (WS3): Blue Book sources for ring-assembly spelling (round 81–82 / D-369, D-373).

Engine pins with OPSIN read-back live in ``tests/test_namer_round81_ring_pairs_n_linked_purines_added_hydrogen_and_bi_assemblies.py``
(KEPT rows) and ``tests/test_namer_round82_benzodithiete_sibling_rings_and_polycyclic_bi_assemblies.py``.
This module records which IUPAC sections apply and whether the engine form is the book PIN
or an OPSIN-driven enclosure rule.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (rule, pdf page, note)
NL_022_SOURCES = (
    (
        "P-28.2.1",
        293,
        "Two identical systems joined by one bond: locants like `1,1'-binaphthalene` (PIN); "
        "no parentheses around two-ring components.",
    ),
    (
        "P-28.2.3",
        294,
        "Indicated hydrogen on components: book cites at the front of the assembly, e.g. "
        "`2′H-1,2′-biindole` (PIN); multi-H spelling `1H,1′H-…-biindole` appears for larger assemblies (p. 338).",
    ),
    (
        "P-28.3 / engine D-373",
        295,
        "Components with three or more rings, or hydro / von Baeyer names with unsaturation, are enclosed: "
        "`bi(anthracene)` — an OPSIN parse requirement, documented in round 82, not a separate book PIN.",
    ),
)

# Engine pins vs book PIN (round 81–82); names re-measured 2026-11-10.
ENGINE_PINS = (
    (
        "two indoles (OPSIN reads)",
        "c1ccc2[nH]ccc2c1-c1cccc2[nH]ccc12",
        "4,4'-bi1H-indole",
        "Book PIN along the lines of `2′H-1,2′-biindole` or `1H,1′H-…-biindole`; engine keeps `bi1H-indole` because OPSIN accepts it.",
    ),
    (
        "two naphthalenes",
        "c1ccc2ccccc2c1-c1cccc2ccccc12",
        "1,1'-binaphthalene",
        "Matches P-28.2.1 example `1,2′-binaphthalene` locant style (primed junction).",
    ),
    (
        "two anthracenes (enclosed)",
        "c1ccc2cc3ccccc3cc2c1-c1ccc2cc3ccccc3cc2c1",
        "1,2'-bi(anthracene)",
        "Enclosure for a three-ring component (D-373); OPSIN need, not asserted as book PIN.",
    ),
)


def test_nl022_three_book_passages_are_recorded():
    assert len(NL_022_SOURCES) == 3
    pages = [row[1] for row in NL_022_SOURCES]
    assert pages == sorted(pages)


def test_nl022_three_engine_pins_are_documented():
    assert len(ENGINE_PINS) == 3


@pytest.mark.parametrize("label,smiles,expected,_note", ENGINE_PINS, ids=[r[0] for r in ENGINE_PINS])
def test_nl022_engine_spelling_pins(label, smiles, expected, _note):
    del label, _note
    assert name_smiles(smiles) == expected


def _inchikey(smiles: str) -> str:
    return inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected,_note", ENGINE_PINS, ids=[r[0] for r in ENGINE_PINS])
def test_nl022_engine_pins_read_back(label, smiles, expected, _note):
    from py2opsin import py2opsin

    del label, _note
    assert name_smiles(smiles) == expected
    back = py2opsin(expected)
    assert back
    assert _inchikey(back) == _inchikey(smiles)
