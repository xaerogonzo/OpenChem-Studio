"""NL-050 (WS3): cyclopentadienyl radical anion naming (observed).

No OPSIN parse was found for a name that keeps the unpaired electron on the drawn
``[C-]`` centre; the engine emits ``cyclopenta-2,4-dien-1-ide``.
"""

from __future__ import annotations

import shutil

import pytest

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN)")

RADICAL_ANION = "[C-]1C=CC=C1"
ENGINE_PIN = "cyclopenta-2,4-dien-1-ide"


def test_nl050_engine_drops_explicit_radical_on_drawn_centre():
    assert name_smiles(RADICAL_ANION) == ENGINE_PIN


@needs_opsin
def test_nl050_no_radical_anion_opsin_target_found():
    """Round 5 sweep: nothing parseable that restored the radical anion drawing."""
    from py2opsin import py2opsin

    assert py2opsin(ENGINE_PIN)  # ordinary carbanion name parses