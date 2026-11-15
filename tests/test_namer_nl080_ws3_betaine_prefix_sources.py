"""NL-080 (WS3): Blue Book betaine zwitterion prefix (round 7 row 870 / D-055h).

The book's PIN for trimethylglycine is ``(N,N-dimethylmethanaminiumyl)acetate`` (V3);
the engine emits ``(trimethylazaniumyl)acetate``, which OPSIN round-trips. Both forms
appear in the book for related ions; the acetate PIN uses the methanaminiumyl spelling.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

BETAINE = "C[N+](C)(C)CC(=O)[O-]"
ENGINE_PIN = "(trimethylazaniumyl)acetate"
BOOK_PIN = "(N,N-dimethylmethanaminiumyl)acetate"

NL_080_SOURCES = (
    (
        "P-74.2.1.2 (betaine anion)",
        429,
        "``(trimethylazaniumyl)oxidanide`` and ``(N,N-dimethylmethanaminiumyl)oxidanide`` — both cation spellings for related zwitterions.",
    ),
    (
        "acetate PIN",
        357,
        "``(N,N-dimethylmethanaminiumyl)acetate (PIN)`` for the trimethylglycine shape.",
    ),
    (
        "acetate PIN (duplicate example)",
        830,
        "``(N,N-dimethylmethanaminiumyl)acetate (PIN)`` beside non-preferred ``(trimethylammoniumyl)acetate``.",
    ),
)


def test_nl080_book_pins_are_documented():
    assert len(NL_080_SOURCES) == 3


def test_nl080_engine_keeps_trimethylazaniumyl_acetate():
    assert name_smiles(BETAINE) == ENGINE_PIN


@needs_opsin
def test_nl080_engine_name_round_trips():
    from py2opsin import py2opsin

    back = py2opsin(ENGINE_PIN)
    assert back
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == inchi.MolToInchiKey(
        Chem.MolFromSmiles(BETAINE)
    )


@needs_opsin
def test_nl080_book_pin_also_parses_same_structure():
    """Measured 2026-11-15: OPSIN accepts the book PIN for the same betaine."""
    from py2opsin import py2opsin

    back = py2opsin(BOOK_PIN)
    assert back
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == inchi.MolToInchiKey(
        Chem.MolFromSmiles(BETAINE)
    )