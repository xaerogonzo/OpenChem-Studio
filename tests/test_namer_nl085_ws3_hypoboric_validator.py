"""NL-085 (WS3): ``hypoboric acid`` vs book ``hypodiboric acid`` (round 5 row 944).

OPSIN cannot parse the book's preselected name; the engine keeps ``hypoboric acid``.
"""

from __future__ import annotations

import shutil

import pytest

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN)")

HYPODIBORIC = "OB(O)B(O)O"
ENGINE_PIN = "hypoboric acid"
BOOK_PIN = "hypodiboric acid"

NL_085_SOURCES = (
    ("P-68.1.1.2.2", 714, "``hypodiboric acid (preselected name)`` in the boron oxoacid table."),
)


def test_nl085_source_recorded():
    assert NL_085_SOURCES[0][1] == 714


def test_nl085_engine_emits_hypoboric():
    assert name_smiles(HYPODIBORIC) == ENGINE_PIN


@needs_opsin
def test_nl085_opsin_accepts_engine_spelling_not_book_pin():
    from py2opsin import py2opsin

    assert py2opsin(ENGINE_PIN)
    assert not py2opsin(BOOK_PIN)