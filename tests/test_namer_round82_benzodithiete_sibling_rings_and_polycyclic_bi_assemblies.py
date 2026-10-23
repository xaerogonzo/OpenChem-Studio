"""Naming round 82 (D-371 .. D-374): the defects a SCAN OF POLYSUBSTITUTED RINGS AND RING ASSEMBLIES finds.

Two new populations. Every curated ring with three or four mixed substituents at random positions (16 groups; 1,427 and 4,725 molecules), and every small curated ring joined to one or two copies
of itself with an optional substituent (1,246 and 1,880), named and read back through OPSIN on the standard InChIKey. The first is clean apart from OPSIN's stereo defaults and the one ring below;
the second found three more:

* D-371 the curated 1,2-benzodithiete had a broken atom-locant table (`{4: 2, 5: 1, 0: 5, 7: 6}`: no 3, 4, 2a or 6a), so a substituted one was a NAMING ERROR or a wrong molecule.
* D-372 two copies of one curated ring joined by a bond, the strict (hydrogen-pinned) query matching only the SIBLING ring: the parent was numbered by the generic fallback
  (`2-(2H-benzotriazol-5-yl)-2H-benzotriazole-5-carboxylic acid` for a 4-acid; the same for two beta-carbolines and two 3,1-benzoxazinediones). The loose matches are tried inside the ring system.
* D-373 a ring assembly of a component OPSIN cannot read behind `bi` was unreadable or another molecule: a tricyclic one (`3,4'-bidibenzothiophene`), a hydro or von Baeyer one
  (`1,1'-bioctahydropentalene`), and xanthene, thioxanthene, phenothiazine and phenoxazine, which need their indicated hydrogen once they are a component (`3,1'-bi(9H-xanthene)`).
* D-374 an assembly bond at a fusion atom took locant 1: the substituent name `hexahydropentalen-3a(1H)-yl` was not parsed for its locant (`3a,3a'-bi(octahydropentalene)`).
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

NAMED = [
    ("a substituted benzodithiete", "CC(=O)c1c(C(N)=O)c(Cl)cc2ssc12", "3-acetyl-5-chloro-1,2-benzodithiete-4-carboxamide"),
    ("...with a nitrile", "COc1c(C)c(C#N)c(Cl)c2ssc12", "3-chloro-6-methoxy-5-methyl-1,2-benzodithiete-4-carbonitrile"),
    ("two benzotriazoles, acid at 4", "O=C(O)c1cccc2nn(-c3ccc4n[nH]nc4c3)nc12", "2-(2H-benzotriazol-5-yl)-2H-benzotriazole-4-carboxylic acid"),
    ("...acid at 5", "O=C(O)c1ccc2nn(-c3ccc4n[nH]nc4c3)nc2c1", "2-(2H-benzotriazol-5-yl)-2H-benzotriazole-5-carboxylic acid"),
    ("two beta-carbolines", "O=C(O)c1nccc2c3ccccc3n(-c3ccc4c(c3)[nH]c3cnccc34)c12", "9-(9H-beta-carbolin-7-yl)-9H-beta-carboline-1-carboxylic acid"),
    ("two xanthenes", "c1ccc2c(c1)Cc1ccc(-c3cccc4c3Cc3ccccc3O4)cc1O2", "3,1'-bi(9H-xanthene)"),
    ("two thioxanthenes", "c1ccc2c(c1)Cc1cc(-c3cccc4c3Cc3ccccc3S4)ccc1S2", "2,1'-bi(9H-thioxanthene)"),
    ("two phenothiazines", "c1ccc2c(c1)Nc1c(cccc1-c1cccc3c1Sc1ccccc1N3)S2", "1,4'-bi(10H-phenothiazine)"),
    ("two phenoxazines", "c1ccc2c(c1)Oc1cc(-c3cccc4c3Nc3ccccc3O4)ccc1N2", "3,1'-bi(10H-phenoxazine)"),
    ("two dibenzothiophenes", "c1ccc2c(c1)sc1cc(-c3cccc4c3sc3ccccc34)ccc12", "3,4'-bi(dibenzothiophene)"),
    ("two bicyclo-dienes", "C1=CCC2C(=C1)CC2C1=CC=C2CCC2C1", "8,3'-bi(bicyclo[4.2.0]octa-3,5-diene)"),
    ("two octahydropentalenes at 3a", "C1CC2CCCC2(C23CCCC2CCC3)C1", "3a,3a'-bi(octahydropentalene)"),
    ("...at 1 and 2", "C1CC2CCCC2C1C1CC2CCCC2C1", "1,2'-bi(octahydropentalene)"),
]

KEPT = [
    ("a benzotriazole with a methyl", "Cc1cccc2nn(C)nc12", "2,4-dimethyl-2H-benzotriazole"),
    ("two indoles", "c1ccc2[nH]ccc2c1-c1cccc2[nH]ccc12", "4,4'-bi1H-indole"),
    ("two naphthalenes", "c1ccc2ccccc2c1-c1cccc2ccccc12", "1,1'-binaphthalene"),
    ("two dibenzazepines", "C1=Cc2ccc(-c3cccc4c3C=Cc3ccccc3N4)cc2Nc2ccccc21", "3,1'-bi(5H-dibenz[b,f]azepine)"),
]

ALL = NAMED + KEPT


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
