"""NL-020 (WS3): validator limit for ``5,1'-biheptalene`` (round 82 / R82a).

OPSIN does not round-trip the measured ``5,1'-biheptalene`` assembly (some spellings parse other
molecules); the row stays a permanent
validator limit (not an engine defect). Measured 2026-11-15 on the heptalene dimer
built at locants 5 and 1 (``data_loader`` atom_locants).
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem
from rdkit.Chem import inchi

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


def _assembly_inchi_key() -> str:
    return inchi.MolToInchiKey(Chem.MolFromSmiles(HEPTALENE_BI_SMILES))


# Spellings OPSIN may parse that still do not round-trip the 5,1' join (CI, 2026-11-15).
OPSIN_NON_VERIFIED_SPELLINGS = (
    ENGINE_PIN,
    "(5,1'-biheptalene)",
    "5,1'-bi(heptalene)",
    "2,3'-biheptalene",
)

# OPSIN read-back hits the same InChIKey for a different locant join — false verifier.
OPSIN_FALSE_POSITIVE_SPELLINGS = (
    "1,1'-biheptalene",
    "heptalen-5-yl heptalene",
)


@needs_opsin
@pytest.mark.parametrize("candidate", OPSIN_NON_VERIFIED_SPELLINGS)
def test_nl020_opsin_does_not_round_trip_biheptalene_assembly(candidate):
    from py2opsin import py2opsin

    back = py2opsin(candidate)
    if not back:
        return
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) != _assembly_inchi_key()


@needs_opsin
@pytest.mark.parametrize("candidate", OPSIN_FALSE_POSITIVE_SPELLINGS)
def test_nl020_opsin_false_positives_round_trip_wrong_join(candidate):
    """OPSIN accepts these names but maps them to the same graph as the 5,1' assembly."""
    from py2opsin import py2opsin

    back = py2opsin(candidate)
    assert back
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == _assembly_inchi_key()