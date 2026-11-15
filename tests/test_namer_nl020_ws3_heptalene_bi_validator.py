"""NL-020 (WS3): validator limit for ``5,1'-biheptalene`` (round 82 / R82a).

OPSIN cannot read the assembly name in any spelling tried; the row stays a permanent
validator limit (not an engine defect). Measured 2026-11-15 on the heptalene dimer
built at locants 5 and 1 (``data_loader`` atom_locants).
"""

from __future__ import annotations

import shutil

import pytest

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN)")

# Locant 5 (idx 8) to locant 1' (idx 4 of the second copy); round 82 assembly scan.
HEPTALENE_BI_SMILES = "C1=CC=C2C=CC=CC(C3=CC=CC=C4C=CC=CC=C43)=C2C=C1"
ENGINE_PIN = "5,1'-biheptalene"

# (rule, V3 pdf page, note)
NL_020_SOURCES = (
    (
        "P-25.1.1 / Table 28.1",
        256,
        "``heptalene`` retained parent (7,7-fused polyalene); bi-assemblies cite locants on each component.",
    ),
    (
        "P-28.2.1",
        290,
        "Two identical ring systems joined by one bond: ``1,1'-binaphthalene`` style; primed locants on the second component.",
    ),
)


def test_nl020_sources_are_recorded():
    assert [p for _, p, _ in NL_020_SOURCES] == sorted(p for _, p, _ in NL_020_SOURCES)


def test_nl020_engine_emits_biheptalene():
    assert name_smiles(HEPTALENE_BI_SMILES) == ENGINE_PIN


@needs_opsin
@pytest.mark.parametrize(
    "candidate",
    (
        ENGINE_PIN,
        "(5,1'-biheptalene)",
        "5,1'-bi(heptalene)",
        "1,1'-biheptalene",
        "2,3'-biheptalene",
        "heptalen-5-yl heptalene",
    ),
)
def test_nl020_opsin_reads_no_biheptalene_spelling(candidate):
    from py2opsin import py2opsin

    assert not py2opsin(candidate)