"""Naming round 91 (D-388): a bridged parent's stereo is dropped by ATOM, fewest first, and a name that no longer says which isomer is never kept.

Found by the first stereo audit (docs/NAMING_LIMITATIONS_PLAN.md, NL-003 and NL-004). When OPSIN rejects a name, the validator dropped the
bridged descriptors whose locant NUMBER OPSIN named, in every component. A norbornyl group lost its three centres because the bicyclo[2.2.2]octane
it hangs on has a 1 and a 4 OPSIN cannot anchor (10 of 10 sampled isomers named flat, although a pinning name exists), and 2,4-difluoroadamantane
lost the centres OPSIN reads along with the two it cannot (2 of 4 isomers flat). Now, when the by-locant strip parses but no longer pins, the
descriptors are dropped one atom at a time, the fewest first, and the first name OPSIN reads to exactly the input is kept.

What stays (validator limits, unchanged): OPSIN reads no pseudoasymmetric r/s and cannot anchor R/S at a substituted bridgehead of
bicyclo[3.3.1]nonane, so those isomers still share a name.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger

from openchem.vendor.iupac_namer import engine, name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

NAMED = [
    ("adamantane 2R,4R", "F[C@@H]1[C@@H]2C[C@H]3C[C@@H](C2)[C@@H](F)[C@@H]1C3", "(1R,2R,4R,5S)-2,4-difluoroadamantane"),
    ("adamantane 2S,4R", "F[C@@H]1[C@H]2C[C@@H]3C[C@H](C2)[C@H](F)[C@H]1C3", "(1R,2S,4R,5S)-2,4-difluoroadamantane"),
    ("adamantane 2R,4S", "F[C@@H]1[C@@H]2C[C@H]3C[C@@H](C2)[C@H](F)[C@@H]1C3", "(1R,2R,4S,5S)-2,4-difluoroadamantane"),
    ("adamantane 2S,4S", "F[C@H]1[C@@H]2C[C@H]3C[C@@H](C2)[C@H](F)[C@@H]1C3", "(1R,2S,4S,5S)-2,4-difluoroadamantane"),
    ("norbornyl on octanol 2R,3R", "O[C@@H]1[C@H]2CC[C@H](CC2)[C@@H]1[C@@H]1C[C@H]2CC[C@@H]1C2",
     "(2R,3R)-3-[(1R,2R)-bicyclo[2.2.1]heptan-2-yl]bicyclo[2.2.2]octan-2-ol"),
    ("norbornyl on octanol 2S,3S", "O[C@H]1[C@H]2CC[C@H](CC2)[C@H]1[C@@H]1C[C@H]2CC[C@@H]1C2",
     "(2S,3S)-3-[(1R,2R)-bicyclo[2.2.1]heptan-2-yl]bicyclo[2.2.2]octan-2-ol"),
    ("norbornyl on octanol 2S,3S'", "O[C@H]1[C@H]2CC[C@H](CC2)[C@H]1[C@H]1C[C@H]2CC[C@@H]1C2",
     "(2S,3S)-3-[(1R,2S)-bicyclo[2.2.1]heptan-2-yl]bicyclo[2.2.2]octan-2-ol"),
    ("norbornyl on octanol 2R,3S", "O[C@@H]1[C@H]2CC[C@H](CC2)[C@H]1[C@H]1C[C@H]2CC[C@@H]1C2",
     "(2R,3S)-3-[(1R,2S)-bicyclo[2.2.1]heptan-2-yl]bicyclo[2.2.2]octan-2-ol"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[r[0] for r in NAMED])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles", [(r[0], r[1]) for r in NAMED], ids=[r[0] for r in NAMED])
def test_the_name_pins_its_isomer(label, smiles):
    """OPSIN reads the name to ONE embeddable stereoisomer and it is the input."""
    assert engine._name_pins_structure(name_smiles(smiles), Chem.MolFromSmiles(smiles))


def test_the_four_adamantane_isomers_have_four_names():
    assert len({name_smiles(r[1]) for r in NAMED[:4]}) == 4


@needs_opsin
def test_the_search_runs_and_finds_nothing_for_a_validator_limit(monkeypatch):
    """The subset search is reached for the nonanol and returns None: no subset of its descriptors pins the isomer."""
    seen = []
    real = engine._pinning_subset_of_descriptors

    def spy(tree, mol):
        seen.append(real(tree, mol))
        return seen[-1]

    monkeypatch.setattr(engine, "_pinning_subset_of_descriptors", spy)
    engine._STEREO_OPSIN_VALIDATION_CACHE.clear()
    name_smiles("O[C@]12CCC[C@H](CCC1)[C@@H]2Cl")
    assert seen and all(s is None for s in seen)


@pytest.mark.parametrize(
    "smiles",
    ["O[C@]12CCC[C@H](CCC1)[C@@H]2Cl", "O[C@]12CCC[C@@H](CCC1)[C@H]2Cl"],
    ids=["9S-side", "9R-side"],
)
def test_a_validator_limit_still_leaves_the_flat_name(smiles):
    """Unchanged by this round: OPSIN cannot anchor the bridgeheads, no subset of descriptors pins the isomer, the flat name stays."""
    assert name_smiles(smiles) == "9-chlorobicyclo[3.3.1]nonan-1-ol"
