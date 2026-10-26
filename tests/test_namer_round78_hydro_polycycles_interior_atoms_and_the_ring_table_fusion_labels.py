"""Naming round 78 (D-355 .. D-360): the defects a HYDRO scan of polycycles and of the ring table finds.

The population is new. 1 to 4 ring double bonds of a polycyclic skeleton (naphthalene to pyrene, indole, carbazole, the azines, imidazo/pyrazolo-fused azines ...) are saturated, with an
optional ring C=O and one or two ring CH replaced by N; the result is named and read back through OPSIN on the standard InChIKey (2,100 molecules, 31 unreadable before). A second scan
saturates every ring double bond of every fully aromatic curated ring in the ring table in turn (505 molecules, 22 wrong or unreadable before): each hydro name cites the fusion atoms,
so a fusion-atom label the table gets wrong shows at once.

* D-355 the fusion constructor numbered an interior atom of a peri-fused system with the book's superscript (`2a1`), which OPSIN cannot read: `1,2,2a,2a1,5,5a-hexahydroacenaphthylene`.
  It writes the CAS letter the ring table already uses for pyrene (`2a,5,5a,8b`), a declared deviation (`known_deviations.toml`).
* D-356 the table labelled imidazo[1,2-b]pyridazine's bridgehead nitrogen `3a`; a fusion heteroatom takes a numeral, and it is `4`.
* D-357 the same for pyrazolo[1,5-a]pyridine, `7a` for `8`.
* D-358 the 4a/8a labels of the isochromenylium family and 1,5-naphthyridine, and the 3a/7a labels of 2,1,3-benzoxadiazole, were swapped: a hydro name cited the wrong atom
  (`1,3a-dihydro-2,1,3-benzoxadiazole` read as another molecule).
* D-359 dibenz[a,h]anthracene's 14a and 7b were swapped (`6a,7b-dihydro...` was another molecule).
* D-360 OPSIN reads `dihydroselenochromenylium` as `dihydroseleno` + `chromenylium`; a hydro prefix before a selenium or tellurium parent takes a hyphen.
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
    ("an interior atom of acenaphthylene, with a ketone", "O=C1CCC2=CC=CC3CCC1C23", "2,2a,4,5,8a,8b-hexahydroacenaphthylen-3(1H)-one"),
    ("...without one", "C1=CC2CC=CC3CCC(=C1)C23", "1,2,2a,5,5a,8b-hexahydroacenaphthylene"),
    ("...a different ketone position", "O=C1CC2CCCC3C=CC=C1C32", "2a,3,4,5,5a,8b-hexahydroacenaphthylen-1(2H)-one"),
    ("an interior atom of a cyclopenta[de]naphthyridine", "O=C1NCC2C=CC3C=CNC1C32", "3a,5a,6,7,8a,8b-hexahydrocyclopenta[de][1,7]naphthyridin-8(1H)-one"),
    ("two interior atoms, which one is b and which c", "O=C1CC2=NC=CC3=CC=C4CCCC1C4C32", "6,8,8a,10,10b,10c-hexahydronaphtho[2,1,8-def]quinolin-9(7H)-one"),
    ("a bridgehead N numbered 4 in imidazo[1,2-b]pyridazine", "O=C1CC=NN2C=CNC12", "1,4,7,8a-tetrahydroimidazo[1,2-b]pyridazin-8-one"),
    ("a bridgehead N numbered 8 in pyrazolo[1,5-a]pyridine", "O=C1CNN2C=CC=CC12", "1,2,3a,8-tetrahydropyrazolo[1,5-a]pyridin-3-one"),
    ("...with the hydrogen on the fusion carbon", "O=C1C=NN2C=CC=CC12", "3a,8-dihydropyrazolo[1,5-a]pyridin-3-one"),
    ("isochromenylium's 4a and 8a", "C1=CCC2C=[O+]C=CC2=C1", "8,8a-dihydroisochromenylium"),
    ("1,5-naphthyridine's 4a and 8a", "C1=CNC2C=CC=NC2=C1", "1,8a-dihydro-1,5-naphthyridine"),
    ("2,1,3-benzoxadiazole's 3a and 7a", "C1=CC2=NONC2C=C1", "1,7a-dihydro-2,1,3-benzoxadiazole"),
    ("dibenz[a,h]anthracene's 14a and 7b", "C1=CC2C=c3c(ccc4ccccc34)=CC2c2ccccc21", "6a,14a-dihydrodibenz[a,h]anthracene"),
    ("a hydro prefix before a selenium parent", "C1=[Se+]c2ccccc2CC1", "3,4-dihydro-selenochromenylium"),
    ("...before a tellurium one", "C1=[Te+]c2ccccc2CC1", "3,4-dihydro-tellurochromenylium"),
    ("...before selenole", "C1=CCC[Se]1", "2,3-dihydro-selenole"),
]

KEPT = [
    ("pyrene keeps its CAS interior letters", "c1cc2ccc3cccc4ccc(c1)c2c34", "pyrene"),
    ("acenaphthylene alone", "C1=Cc2cccc3cccc1c23", "acenaphthylene"),
    ("a sulfur parent needs no hyphen", "C1=[S+]c2ccccc2CC1", "3,4-dihydrothiochromenylium"),
    ("imidazo[1,2-b]pyridazine alone", "c1cnn2ccnc2c1", "imidazo[1,2-b]pyridazine"),
    ("pyrazolo[1,5-a]pyridine alone", "c1ccn2nccc2c1", "pyrazolo[1,5-a]pyridine"),
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


def test_no_name_cites_a_superscript_interior_locant():
    import re

    for smiles in ("C1=CC2CC=CC3CCC(=C1)C23", "O=C1CCC2=CC=CC3CCC1C23"):
        assert not re.search(r"\d+[a-z]\d", name_smiles(smiles))


def test_the_constructor_deviation_is_declared_and_is_what_the_engine_does():
    """The CAS interior letter is a DECLARED deviation, and the book's superscript is still what the engine's own rule computes."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks" / "naming"))
    import known_deviations as kd

    from openchem.vendor.iupac_namer.ring_naming import fusion_general as fg
    from openchem.vendor.iupac_namer.ring_naming.fusion_orientation import _interior_carbon_locant

    declared = kd.load_constructor()
    assert [d["id"] for d in declared] == ["KD-constructor-interior"]
    assert all(declared[0][k].strip() for k in ("engine", "normative", "reason", "oracle_statement"))
    mol = Chem.MolFromSmiles("C1=Cc2cccc3cccc1c23")
    numbering = fg.name_fusion(mol, [tuple(r) for r in mol.GetRingInfo().AtomRings()]).numberings[0].atom_to_locant
    interior = [a.GetIdx() for a in mol.GetAtoms() if mol.GetRingInfo().NumAtomRings(a.GetIdx()) == 3]
    assert [str(numbering[i]) for i in interior] == ["8b"]
    peripheral = {i for i in numbering if i not in interior}
    book = _interior_carbon_locant(mol, interior[0], {i: numbering[i] for i in peripheral}, peripheral)
    assert f"{book._numeric_value}{book.suffix}" == "2a1"
