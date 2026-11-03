"""Naming round 85 (D-379): the one defect a SCAN OF SPIRO JOINTS WITH SUBSTITUENTS finds, and the one a ring audit confirmed was alone.

Populations: three curated rings in a chain (400, clean apart from OPSIN's beta-lactam stereo), a spiro joint of two curated rings with one or two substituents (500: 489 read back, 11 did not; after the fix 498).
Eight of the eleven failures had one partner, `7,8,9,10-tetrahydro-6H-6,10-methanoazepino[4,5-g]quinoxaline`, whose curated entry labelled 11 of its 16 atoms (none of 3, 4a, 5a, 10a, 11a) and had the two
nitrogens the wrong way round beside the carbons next to them (N1 is on the C11a side, N4 on the C4a side; one chlorine probe cannot tell, the pair is symmetric). A substituent on an unlabelled atom of a spiro
name was numbered by the generic fallback (`-16-carboxamide`), which OPSIN cannot read; and a molecule with a substituent on each side could be named with the wrong atoms.

* D-379 every atom of the entry is labelled from the adjacency (N1=idx9, C2=idx0, C3=idx1, N4=idx2, C4a=3, C5=4, C5a=5, C6=14 ... C10a=6, C11=7, C11a=8, C12=15), and a spiro name cites the primed locant
  (`-2'-carboxamide`). Round 84's open item (a) (the molecule that used to hang read back unreadably) is the same cause and is closed with it. An audit of the other 370 entries (222 + 253 single-chlorine variants of
  every entry with unlabelled ring atoms: helicenes, tetracene derivatives, steroids, indolizino-, dibenzo-, pyrido[1,2,3-de]- and methano-bridged systems) read back in full.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.data_loader import _RING_CURATED_SMILES

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

PARTNER = "7,8,9,10-tetrahydro-6H-6,10-methanoazepino[4,5-g]quinoxaline"

NAMED = [
    ("an amide on the bridged partner of a spiro", "CON1CCCCC12C1CNCC2c2cc3nc(C(N)=O)cnc3cc21",
     f"1-methoxyspiro[azinane-2,12'-{PARTNER}]-2'-carboxamide"),
    ("an acid and a ketone either side", "CC(=O)C1NC2(CCCCN2)C2CC1c1cc3nccnc3c(C(=O)O)c12",
     f"9'-acetylspiro[piperidine-2,7'-{PARTNER}]-5'-carboxylic acid"),
    ("two chlorines on the ring itself", "Clc1cnc2c(Cl)c3c(cc2n1)C1CNCC3C1", f"2,5-dichloro-{PARTNER}"),
    ("the molecule round 84 hung on", "O=C1CC2(c3ccccc3N1)C1CNCC2c2cc3nccnc3cc21",
     f"spiro[1,2,3,4-tetrahydroquinoline-4,12'-{PARTNER}]-2-one"),
]

ALL = NAMED


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[r[0] for r in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


def _key(smiles: str) -> str:
    return inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))


@needs_opsin
@pytest.mark.parametrize("label,smiles", [(r[0], r[1]) for r in ALL], ids=[r[0] for r in ALL])
def test_the_name_reads_back_to_the_same_molecule(label, smiles):
    from py2opsin import py2opsin

    name = name_smiles(smiles)
    back = py2opsin(name)
    assert back, name
    assert _key(back) == _key(smiles), (name, back)


def test_the_curated_entry_labels_every_atom_and_pairs_its_nitrogens():
    smi = "c1cnc2cc3c(cc2n1)C1CNCC3C1"
    labels = _RING_CURATED_SMILES[smi]["atom_locants"]
    mol = Chem.MolFromSmiles(smi)
    assert sorted(labels) == list(range(mol.GetNumAtoms()))
    by_label = {str(v): k for k, v in labels.items()}
    assert len(by_label) == mol.GetNumAtoms()
    # N1 is bonded to C11a and C2; N4 to C4a and C3; every consecutive pair of the ring numbering is bonded
    for a, b in (("1", "2"), ("2", "3"), ("3", "4"), ("4", "4a"), ("4a", "5"), ("5", "5a"), ("5a", "6"), ("6", "7"), ("7", "8"), ("8", "9"),
                 ("9", "10"), ("10", "10a"), ("10a", "11"), ("11", "11a"), ("11a", "1"), ("6", "12"), ("10", "12"), ("4a", "11a"), ("5a", "10a")):
        assert mol.GetBondBetweenAtoms(by_label[a], by_label[b]) is not None, (a, b)
