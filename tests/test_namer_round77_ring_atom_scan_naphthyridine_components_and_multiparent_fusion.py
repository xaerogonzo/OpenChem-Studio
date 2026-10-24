"""Naming round 77 (D-351 .. D-354): the defects a RING-ATOM SCAN finds.

The population is new. Every CH of a polycyclic skeleton (naphthalene, anthracene, phenanthrene, pyrene, chrysene, coronene, carbazole, dibenzofuran, dibenzothiophene ...) is replaced by N, up to
three at a time, and the five-membered ring's heteroatom is varied (916 + 1,443 systems); the result is named and read back through OPSIN on the standard InChIKey. On the census molecules the
same scan (one ring atom, 2,200 molecules) is clean to a fraction of a percent; on the bare ring systems 150 of 916 failed:

* D-351 a fused system with a naphthyridine inside it (`pyrido[2,3-b][1,6]naphthyridine`) had NO name, because the six naphthyridines were not components of the fusion constructor: the
  three pyridine rings were three equal parents, "a multiparent system". They are components now (`[1,6]naphthyridine`); a naphthyridine on its own keeps `1,6-naphthyridine`.
* D-352 two occurrences of the parent component joined by one other component (aza analogues of carbazole, dibenzofuran and dibenzothiophene) had no name: `furo[2,3-b:5,4-c']dipyridine`.
* D-353 a ring system the fusion constructor declined and the von Baeyer route named had its aromatic bonds DROPPED: an aza-coronene was `2,5-diazaheptacyclo[...]tetracosane`, a saturated
  cage, another molecule. The aromatic bonds are cited as enes (`...tetracosa-1,3,5,...-dodecaene`).
* D-354 a peri descriptor that cites one label twice (`pyreno[3a,3,5,4,3a-aklmn]phenanthridine`), a name OPSIN cannot read, is not emitted.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

NAMED = [
    ("a pyridine fused to a naphthyridine", "c1cnc2nc3ccncc3cc2c1", "pyrido[2,3-b][1,6]naphthyridine"),
    ("...the other way round", "c1cc2nc3ccncc3cc2cn1", "pyrido[4,3-b][1,6]naphthyridine"),
    ("a pyrrole on the [1,8] one", "c1cc2cc3cc[nH]c3nc2nc1", "1H-pyrrolo[2,3-b][1,8]naphthyridine"),
    ("a benzene between two furans, the book's own example", "c1cc2cc3cocc3cc2o1", "benzo[1,2-b:4,5-c']difuran"),
    ("two pyridines on a furan", "c1cnc2c(c1)oc1cccnc12", "furo[3,2-b:4,5-b']dipyridine"),
    ("...on a different side", "c1cnc2oc3cnccc3c2c1", "furo[2,3-b:5,4-c']dipyridine"),
    ("two pyridines on a thiophene", "c1cnc2sc3cnccc3c2c1", "thieno[2,3-b:5,4-c']dipyridine"),
    ("...and on a pyrrole", "c1cnc2[nH]c3cnccc3c2c1", "9H-pyrrolo[2,3-b:5,4-c']dipyridine"),
    ("an aza-coronene is no saturated cage", "c1cc2ccc3ncc4ccc5ccc6ccc1c1c2c3c4c5c61", None),
]

KEPT = [
    ("a naphthyridine alone keeps its retained name", "c1cnc2ncccc2c1", "1,8-naphthyridine"),
    ("...and its substituent", "Cc1ccc2cccnc2n1", "2-methyl-1,8-naphthyridine"),
    ("a benzo-fused naphthyridine is named on the senior parent (two rings, two nitrogens), no longer as a pyridoquinoline", "c1ccc2nc3ccncc3cc2c1", "benzo[b][1,6]naphthyridine"),
    ("coronene", "c1cc2ccc3ccc4ccc5ccc6ccc1c1c2c3c4c5c61", "coronene"),
]

ALL = NAMED + KEPT


@pytest.mark.parametrize("label,smiles,expected", [r for r in ALL if r[2] is not None], ids=[r[0] for r in ALL if r[2] is not None])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


def _key(smiles: str) -> str:
    return inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))


def test_an_aza_coronene_is_not_a_saturated_cage():
    name = name_smiles("c1cc2ccc3ncc4ccc5ccc6ccc1c1c2c3c4c5c61")
    assert "NAMING ERROR" not in name
    assert name.endswith("ene"), name
    assert "ene" in name.split("]")[-1] and not name.endswith("tetracosane"), name


def test_no_name_cites_one_locant_twice():
    name = name_smiles("c1cc2ccc3ccc4ncc5ccc6ccc1c1c2c3c4c5c61")
    assert "3a,3,5,4,3a" not in name


@needs_opsin
@pytest.mark.parametrize("label,smiles", [(r[0], r[1]) for r in ALL], ids=[r[0] for r in ALL])
def test_the_name_reads_back_to_the_same_molecule(label, smiles):
    from py2opsin import py2opsin

    name = name_smiles(smiles)
    back = py2opsin(name)
    assert back, name
    assert _key(back) == _key(smiles), (name, back)
