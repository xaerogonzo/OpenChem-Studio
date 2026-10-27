"""Naming round 89 (D-386): the stereoisomers of a substituted bicyclo[2.2.2]octane or norbornane got ONE name between them.

RDKit's CIP labeller gives R/S to the bridgeheads of 3-methylbicyclo[2.2.2]octan-2-ol, whose other two bridges are equivalent; OPSIN sees no
centre there ("Could not find atom that: 1S") and rejects the whole name, and the validator then stripped EVERY bridged descriptor, the 2 and 3
that OPSIN reads with them. Four isomers, one flat name. Now the descriptors OPSIN names, or (when it only says it could not assign the CIP) the
ring-fusion atoms, are dropped, and a shorter name is kept only if OPSIN reads it back to exactly one embeddable stereoisomer, the input.

Measured on 39 generated substituted bridged bicycles (178 stereoisomers, the molecules' parents norbornane, bicyclo[2.2.2]octane, [3.2.1], [3.3.1],
[2.1.1], tropane, quinuclidine, adamantane and hetero analogues): molecules whose isomers all had distinct names 27 -> 35, names that did not say which
isomer they were 31 -> 12, wrong names 0 -> 0. What stays: OPSIN reads no pseudoasymmetric r/s and cannot anchor R/S at a substituted bridgehead
(`bicyclo[3.3.1]nonan-1-ol`), so those isomers still share a name (KNOWN_LIMITATIONS, round 89).
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi
from rdkit.Chem.EnumerateStereoisomers import EnumerateStereoisomers, StereoEnumerationOptions

from openchem.vendor.iupac_namer import engine, name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

NAMED = [
    ("2-ol 2S,3R", "C[C@@H]1[C@H]2CC[C@H](CC2)[C@@H]1O", "(2S,3R)-3-methylbicyclo[2.2.2]octan-2-ol"),
    ("2-ol 2S,3S", "C[C@H]1[C@H]2CC[C@H](CC2)[C@@H]1O", "(2S,3S)-3-methylbicyclo[2.2.2]octan-2-ol"),
    ("2-ol 2R,3R", "C[C@@H]1[C@H]2CC[C@H](CC2)[C@H]1O", "(2R,3R)-3-methylbicyclo[2.2.2]octan-2-ol"),
    ("2-ol 2R,3S", "C[C@H]1[C@H]2CC[C@H](CC2)[C@H]1O", "(2R,3S)-3-methylbicyclo[2.2.2]octan-2-ol"),
    ("diamine, trans", "N[C@H]1[C@H]2CC[C@H](CC2)[C@@H]1N", "(2S,3S)-bicyclo[2.2.2]octane-2,3-diamine"),
    ("diamine, cis (meso)", "N[C@@H]1[C@H]2CC[C@H](CC2)[C@@H]1N", "(2R,3S)-bicyclo[2.2.2]octane-2,3-diamine"),
    ("norbornane 2S,6S", "C[C@H]1C[C@H]2C[C@H](C)[C@@H]1C2", "(2S,6S)-2,6-dimethylbicyclo[2.2.1]heptane"),
    ("norbornane 2R,6R", "C[C@@H]1C[C@H]2C[C@@H](C)[C@@H]1C2", "(2R,6R)-2,6-dimethylbicyclo[2.2.1]heptane"),
    ("a real bridgehead stays", "C[C@H]1C[C@H]2CC[C@@H]1C[C@H]2O", "(1R,2R,4R,5S)-5-methylbicyclo[2.2.2]octan-2-ol"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[r[0] for r in NAMED])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


def _isomers(flat: str):
    opts = StereoEnumerationOptions(tryEmbedding=True, unique=True, onlyUnassigned=True)
    return [Chem.MolToSmiles(m) for m in EnumerateStereoisomers(Chem.MolFromSmiles(flat), options=opts)]


@pytest.mark.parametrize("flat", ["CC1C2CCC(CC2)C1O", "NC1C2CCC(CC2)C1N", "CC1CC2CC(C)C1C2"], ids=["methyl-ol", "diamine", "dimethylnorbornane"])
def test_the_isomers_have_distinct_names(flat):
    """The molecules above have no r/s centre except the dimethylnorbornane's bridgeheads, which a pair of its isomers share (the limit)."""
    isomers = _isomers(flat)
    names = {name_smiles(s) for s in isomers}
    expected = {"CC1CC2CC(C)C1C2": 3}.get(flat, len(isomers))
    assert len(names) == expected, (flat, sorted(names))


@needs_opsin
@pytest.mark.parametrize("label,smiles", [(r[0], r[1]) for r in NAMED], ids=[r[0] for r in NAMED])
def test_the_name_pins_its_isomer(label, smiles):
    """OPSIN reads the name to ONE embeddable stereoisomer and it is the input."""
    assert engine._name_pins_structure(name_smiles(smiles), Chem.MolFromSmiles(smiles))


@needs_opsin
def test_a_flat_name_does_not_pin_a_chiral_isomer():
    mol = Chem.MolFromSmiles("C[C@@H]1[C@H]2CC[C@H](CC2)[C@@H]1O")
    assert not engine._name_pins_structure("3-methylbicyclo[2.2.2]octan-2-ol", mol)
    assert not engine._name_pins_structure("(2S,3S)-3-methylbicyclo[2.2.2]octan-2-ol", mol)  # the other diastereomer
    assert engine._name_pins_structure("(2S,3R)-3-methylbicyclo[2.2.2]octan-2-ol", mol)


@needs_opsin
def test_the_error_text_names_the_locants_opsin_could_not_anchor():
    parsed, locants = engine._opsin_probe("(1S,2S,3R,4S)-3-methylbicyclo[2.2.2]octan-2-ol")
    assert not parsed and "1" in locants
    assert engine._opsin_probe("(2S,3R)-3-methylbicyclo[2.2.2]octan-2-ol") == (True, [])


@needs_opsin
@pytest.mark.parametrize("flat", ["CC1CC2CC(C1)CC(O)(C2)C", "CC1CC2CC(C)C1C2", "OC12CCCC(CCC1)C2"], ids=["dimethylnonanol", "dimethylnorbornane", "nonan-1-ol"])
def test_a_name_that_cannot_say_everything_never_says_something_else(flat):
    """Where OPSIN cannot take a descriptor the isomers may share a name, but the name must read back to a set that CONTAINS the input."""
    from py2opsin import py2opsin

    for smiles in _isomers(flat):
        back = py2opsin(name_smiles(smiles))
        assert back, (smiles, name_smiles(smiles))
        opts = StereoEnumerationOptions(tryEmbedding=True, unique=True, onlyUnassigned=True, maxIsomers=64)
        keys = {inchi.MolToInchiKey(m) for m in EnumerateStereoisomers(Chem.MolFromSmiles(back), options=opts)}
        assert inchi.MolToInchiKey(Chem.MolFromSmiles(smiles)) in keys, (smiles, name_smiles(smiles))


@pytest.mark.parametrize(
    "smiles",
    ["O[C@]12CCC[C@H](CCC1)[C@@H]2Cl", "O[C@]12CCC[C@@H](CCC1)[C@H]2Cl"],
    ids=["9S-side", "9R-side"],
)
def test_a_shorter_name_that_still_leaves_the_isomer_open_is_not_kept(smiles):
    """OPSIN reads `(9S)-9-chlorobicyclo[3.3.1]nonan-1-ol` (it cannot anchor the 1 and 5), but it names two molecules; the flat name stays."""
    assert name_smiles(smiles) == "9-chlorobicyclo[3.3.1]nonan-1-ol"
