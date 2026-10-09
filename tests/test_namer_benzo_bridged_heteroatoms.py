"""Naming round 32 (D-204): a benzo-fused bridged ring system with a ring heteroatom is not a carbocycle's name.

`ring_naming.benzo_fused_bridged` names `<hydro>-<bridge>-methano-benzocyclo[N]ene`, a CARBOCYCLE, and never looked at an atom's element: a ring oxygen, nitrogen or sulfur in
the macrocycle was dropped without a word. The Biginelli-type adducts `CC(=O)C1C(=O)NC2(C)CC1c1cc([N+](=O)[O-])ccc1O2` (a 2,6-methano-1,3-benzoxazocine) came out as
`6-acetyl-9-methyl-3-nitro-5,6,7,8,9,10-hexahydro-5,9-methanobenzocycloocten-7-one`, which OPSIN reads as a carbocycle with no oxygen and no nitrogen: a different molecule, and
both census rows of this shape were wrong. The module now declines a system whose non-benzene atoms are not all carbon, and the generic bridged path names it, with its replacement
prefixes (`8-oxa-10-azatricyclo[7.3.1.0^{2,7}]trideca-2,4,6-trien-11-one`).

The preferred name is the fusion-bridged one (`2,6-methano-1,3-benzoxazocine`, P-25.4); that is not built, so these are valid, non-preferred names.
Every name pinned here is read back through OPSIN to its input on canonical SMILES and InChIKey.
"""
from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
NAMED = [
    ("a Biginelli-type benzoxazocine lactam", "CC(=O)[C@@H]1C(=O)N[C@@]2(C)C[C@@H]1c1cc([N+](=O)[O-])ccc1O2",
     "(1S,9R,12R)-12-acetyl-9-methyl-4-nitro-8-oxa-10-azatricyclo[7.3.1.0^{2,7}]trideca-2,4,6-trien-11-one"),
    ("its thiourea analogue", "CCOC(=O)[C@@H]1[C@H]2NC(=S)N[C@]1(C)Oc1ccc(Br)cc12",
     "ethyl (1R,9R,13R)-4-bromo-9-methyl-11-thioxo-8-oxa-10,12-diazatricyclo[7.3.1.0^{2,7}]trideca-2,4,6-triene-13-carboxylate"),
    ("a lactam without substituents", "O=C1CC2CC(N1)c1ccccc1O2", "8-oxa-12-azatricyclo[7.3.1.0^{2,7}]trideca-2,4,6-trien-11-one"),
    ("a ring oxygen alone", "CC12CC(C(=O)CC1)c1ccccc1O2", "9-methyl-8-oxatricyclo[7.3.1.0^{2,7}]trideca-2,4,6-trien-12-one"),
    ("oxygen in a five-atom bridge path", "c1ccc2c(c1)C1COCC2C1", "10-oxatricyclo[6.3.1.0^{2,7}]dodeca-2,4,6-triene"),
    ("sulfur", "c1ccc2c(c1)C1CCSCC2C1", "10-thiatricyclo[6.4.1.0^{2,7}]trideca-2,4,6-triene"),
    ("nitrogen", "c1ccc2c(c1)C1CCNC2CC1", "9-azatricyclo[6.3.2.0^{2,7}]trideca-2,4,6-triene"),
    ("nitrogen in the three-atom path", "c1ccc2c(c1)C1CNCC2C1", "10-azatricyclo[6.3.1.0^{2,7}]dodeca-2,4,6-triene"),
    ("a bridgehead nitrogen", "c1ccc2c(c1)C1CCCCN2CC1", "1-azatricyclo[6.4.2.0^{2,7}]tetradeca-2,4,6-triene"),
    ("oxygen on the bridge", "c1ccc2c(c1)CC1CCCC2O1", "13-oxatricyclo[7.3.1.0^{2,7}]trideca-2,4,6-triene"),
    ("a larger ring, oxygen", "c1ccc2c(c1)CC1CCOCC2C1", "12-oxatricyclo[7.4.1.0^{2,7}]tetradeca-2,4,6-triene"),
]

# The carbocycles the module was written for keep their names.
UNCHANGED = [
    ("a bridged benzocycloheptenone", "O=C1CC2CC(C1)c1ccccc12", "5,6,7,8,9-pentahydro-5,9-methanobenzocyclohepten-7-one"),
    ("a bridged benzocyclooctenone", "O=C1CC2Cc3ccccc3C(C1)C2", "5,6,7,8,9,10-hexahydro-5,9-methanobenzocycloocten-7-one"),
    ("a bridged benzocyclononenone", "O=C1CCCC2CC1Cc1ccccc12", "5,6,7,8,9,10,11-heptahydro-5,10-methanobenzocyclononen-9-one"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_name_keeps_its_heteroatoms(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_name_reads_back_to_the_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[row[0] for row in NAMED])
def test_no_heteroatom_is_lost(label, smiles, expected):
    """The defect itself, said without a name: every ring O, N and S of the molecule is in its name as a replacement prefix."""
    mol = Chem.MolFromSmiles(smiles)
    ring_hetero = {a.GetSymbol() for a in mol.GetAtoms() if a.IsInRing() and a.GetSymbol() in ("O", "N", "S")}
    name = name_smiles(smiles)
    for symbol, prefix in (("O", "oxa"), ("N", "aza"), ("S", "thia")):
        if symbol in ring_hetero:
            assert prefix in name, (symbol, name)
