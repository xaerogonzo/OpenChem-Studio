"""Naming round 33 (D-205): the cation of a fused ring system is named from its neutral twin when the cation itself matches no table.

The fused namers read the ring from the molecule. The cation of a ring system whose neutral parent has ONE indicated hydrogen (`c1c[n+]2c([nH]1)[nH]c1ccccc12`, the cation
of imidazo[1,2-a][1,3]benzimidazole; any protonated pyridine-type nitrogen of a fused heteroaromatic: `[nH+]` beside an `[nH]`) is a molecule no table holds, so
`name_ring_system` returned nothing and the name was `[NAMING ERROR: No valid naming plan found for ...]`: 8 of 300 protonated fused heteroaromatics, and 7 of the census's
2000 rows. A ring system with nothing to offer that carries an aromatic nitrogen cation is tried once more on a neutral copy (`ring_naming._neutral_twin`); the `-ium` is
rendered afterwards from the full molecule, and the atom indices are the same. It only runs where the first pass found nothing, so no name that existed can move.

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
    ("protonated imidazo-benzimidazole", "c1cn2c([nH+]1)[nH]c1ccccc12", "9H-imidazo[1,2-a][1,3]benzimidazol-1-ium"),
    ("its bridgehead cation", "c1c[n+]2c([nH]1)[nH]c1ccccc12", "9H-imidazo[1,2-a][1,3]benzimidazol-4-ium"),
    ("N-methyl", "C[n+]1ccn2c1[nH]c1ccccc12", "1-methyl-1H-imidazo[1,2-a][1,3]benzimidazol-1-ium"),
    ("N-methyl with substituents", "Cc1c(C)[n+](C)c2[nH]c3ccccc3n12", "1,2,3-trimethyl-1H-imidazo[1,2-a][1,3]benzimidazol-1-ium"),
    ("a purinium inside a substituent", "Cn1c(=O)[nH]c(=O)c2c1[nH]c(NCCC[n+]1cc[nH]c1)[n+]2CCO",
     "7-(2-hydroxyethyl)-8-{[3-(1H-imidazol-3-ium-3-yl)propyl]amino}-3-methyl-2,6-dioxo-1H-purin-7-ium"),
    ("a protonated pyrido[3,4-b]indole", "COc1cc2[nH+]c3c(C)[nH]ccc-3c2cc1Br", "6-bromo-7-methoxy-1-methyl-2H-pyrido[3,4-b]indol-9-ium"),
    ("a protonated pyrazolo-triazolo-pyrimidine", "CCc1ccc(-c2nnc3c4cnn(-c5ccc(C)cc5C)c4[nH+]cn23)cc1",
     "7-(2,4-dimethylphenyl)-3-(4-ethylphenyl)-7H-pyrazolo[4,3-e][1,2,4]triazolo[4,3-c]pyrimidin-6-ium"),
    ("a protonated triazino-indole", "COc1ccc(Cl)c2c3[nH]nc(SCC(=O)N4CCOCC4)nc-3[nH+]c12",
     "9-chloro-6-methoxy-3-{[2-(morpholin-4-yl)-2-oxoethyl]sulfanyl}-1H-[1,2,4]triazino[5,6-b]indol-5-ium"),
    ("a protonated imidazo-quinoline", "Cc1cnc2ccc3c([nH+]c(NO)n3C)c2c1", "2-(hydroxyamino)-3,8-dimethyl-3H-imidazo[4,5-f]quinolin-1-ium"),
    ("a protonated pyrido-quinolinone", "CCOC(=O)c1c[nH]c2ccc3c(C)cc(=O)[nH+]c3c2c1C",
     "9-(ethoxycarbonyl)-4,10-dimethyl-2-oxo-2,7-dihydropyrido[2,3-f]quinolin-1-ium"),
    ("a protonated pyrimido-indolone", "O=c1[nH+]c(-c2ccccn2)[nH]c2c1[nH]c1ccccc12", "4-oxo-2-(pyridin-2-yl)-4,5-dihydro-1H-pyrimido[5,4-b]indol-3-ium"),
    ("a protonated pyrimido-indole", "CC1(C)CCCN(c2nc[nH+]c3c2[nH]c2ccc(Cl)cc23)C1", "8-chloro-4-(3,3-dimethylpiperidin-1-yl)-5H-pyrimido[5,4-b]indol-1-ium"),
    ("a protonated pyrido-quinazolinone", "O=C(O)c1cccn2c(=O)c3ccccc3[nH+]c12", "6-carboxy-11-oxo-11H-pyrido[2,1-b]quinazolin-5-ium"),
]

# Cations that already had names keep them: the neutral twin only runs where the first pass found nothing.
UNCHANGED = [
    ("a protonated imidazo[1,2-a]pyridine", "c1cn2cc[nH+]c2cc1", "imidazo[1,2-a]pyridin-1-ium"),
    ("an N-methyl imidazo[1,2-a]pyridinium", "C[n+]1ccn2ccccc12", "1-methylimidazo[1,2-a]pyridin-1-ium"),
    ("pyridinium", "C[n+]1ccccc1", "1-methylpyridin-1-ium"),
    ("the neutral imidazo-benzimidazole", "Cc1cn2c(n1)[nH]c1ccccc12", "2-methyl-9H-imidazo[1,2-a][1,3]benzimidazole"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_cation_is_named(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_name_reads_back_to_the_cation(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_the_neutral_twin_only_neutralises_ring_nitrogen_cations():
    from openchem.vendor.iupac_namer.ring_naming import _neutral_twin

    class Ring:
        def __init__(self, atoms):
            self.atom_indices = frozenset(atoms)

    mol = Chem.MolFromSmiles("c1c[n+]2c([nH]1)[nH]c1ccccc12")
    twin = _neutral_twin(Ring(range(mol.GetNumAtoms())), mol)
    assert twin is not None
    assert all(a.GetFormalCharge() == 0 for a in twin.GetAtoms())
    assert twin.GetNumAtoms() == mol.GetNumAtoms()                       # the same atoms, so the same indices
    assert mol.GetAtomWithIdx(2).GetFormalCharge() == 1                 # the molecule the caller holds is not changed
    neutral = Chem.MolFromSmiles("Cc1cn2c(n1)[nH]c1ccccc12")
    assert _neutral_twin(Ring(range(neutral.GetNumAtoms())), neutral) is None   # nothing to neutralise: no twin


def test_the_twin_is_tried_only_when_the_first_pass_found_nothing(monkeypatch):
    """A cation that already has a name is named from itself: the ring namers run once, not twice."""
    from openchem.vendor.iupac_namer import ring_naming

    calls = []
    real = ring_naming._name_ring_system_on

    def spy(candidate, mol):
        result = real(candidate, mol)
        calls.append((bool(result), any(a.GetFormalCharge() for a in mol.GetAtoms())))      # (named, the molecule it was given still has a charge)
        return result

    monkeypatch.setattr(ring_naming, "_name_ring_system_on", spy)
    assert name_smiles("c1cn2cc[nH+]c2cc1") == "imidazo[1,2-a]pyridin-1-ium"
    assert calls and all(named and charged for named, charged in calls), calls               # every call named it, from the cation itself: no retry on a twin
    calls.clear()
    name_smiles("c1c[n+]2c([nH]1)[nH]c1ccccc12")
    assert calls[0] == (False, True) and calls[-1] == (True, False), calls                 # the cation named nothing; its neutral twin did


def test_a_non_aromatic_cation_is_not_guessed():
    """The twin neutralises AROMATIC ring nitrogens only: a bicyclic amidinium has no neutral aromatic parent to look up, and stays a visible refusal."""
    assert "NAMING ERROR" in name_smiles("C1C[N+]2=C(CCCCC2)NC1")
