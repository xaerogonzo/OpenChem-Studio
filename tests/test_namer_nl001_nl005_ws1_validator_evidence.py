"""WS1 evidence pins for NL-001, NL-002 and NL-005 (validator limits, not engine defects).

Re-measures the representative constructions from naming rounds 89–91 and records
that they remain open as validator limits with the evidence chain cited in
``docs/NAMING_LIMITATIONS_PLAN.md``. Does not close those rows — only guards regression.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem
from rdkit.Chem.EnumerateStereoisomers import EnumerateStereoisomers, StereoEnumerationOptions

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN)")

# NL-001: pseudoasymmetric bridgeheads on dimethylnorbornane — 4 embeddable isomers, 3 names (CI / Java).
DIMETHYLNORBORNANE = "CC1CC2CC(C)C1C2"
NL001_THREE_NAMES = frozenset(
    {
        "(2R,6R)-2,6-dimethylbicyclo[2.2.1]heptane",
        "(2R,6S)-2,6-dimethylbicyclo[2.2.1]heptane",
        "(2S,6S)-2,6-dimethylbicyclo[2.2.1]heptane",
    }
)

# NL-002: substituted bridgehead 9-chloro bicyclo[3.3.1]nonan-1-ol — flat name (round 89).
NL002_CASES = (
    ("9S-side", "O[C@]12CCC[C@H](CCC1)[C@@H]2Cl"),
    ("9R-side", "O[C@]12CCC[C@@H](CCC1)[C@H]2Cl"),
)
NL002_FLAT = "9-chlorobicyclo[3.3.1]nonan-1-ol"

# NL-005: adamantane spiro methyl (round 88 variant pass); measured 2026-11-10.
NL005_SPIRO_METHYL = "C1C2CC3CC1CC(C2)C31CCCCC1C"
NL005_FLAT = "6'-methylspiro[tricyclo[3.3.1.1^{3,7}]decane-2,1'-cyclohexane]"


def _embeddable_isomers(smiles: str) -> list[str]:
    opts = StereoEnumerationOptions(tryEmbedding=True, unique=True, onlyUnassigned=True, maxIsomers=32)
    mol = Chem.MolFromSmiles(smiles)
    return [Chem.MolToSmiles(m) for m in EnumerateStereoisomers(mol, options=opts)]


def test_nl005_adamantane_spiro_methyl_still_names_all_embeddable_isomers_flat():
    """RDKit embeds two stereoisomers here; both name flat (validator limit; round 88 reported four)."""
    names = {name_smiles(s) for s in _embeddable_isomers(NL005_SPIRO_METHYL)}
    assert names == {NL005_FLAT}
    assert len(_embeddable_isomers(NL005_SPIRO_METHYL)) >= 2


@needs_opsin
def test_nl001_dimethylnorbornane_still_collapses_pseudoasymmetric_isomers():
    """Four isomers still share three names (validator limit on unreadable r/s); measured on Windows CI 2026-11-10."""
    isomers = _embeddable_isomers(DIMETHYLNORBORNANE)
    names = {name_smiles(s) for s in isomers}
    assert len(isomers) == 4
    assert names == NL001_THREE_NAMES


@pytest.mark.parametrize("label,smiles", NL002_CASES, ids=[c[0] for c in NL002_CASES])
def test_nl002_substituted_bridgehead_stays_flat(label, smiles):
    del label
    assert name_smiles(smiles) == NL002_FLAT


@needs_opsin
@pytest.mark.parametrize("label,smiles", NL002_CASES, ids=[c[0] for c in NL002_CASES])
def test_nl002_opsin_accepts_partial_descriptor_names_but_does_not_pin_isomer(label, smiles):
    """OPSIN parses `(9S)-…` but names two molecules — the reason the flat name is kept."""
    from openchem.vendor.iupac_namer import engine

    del label
    assert not engine._name_pins_structure(NL002_FLAT, Chem.MolFromSmiles(smiles))
