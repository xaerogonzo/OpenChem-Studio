"""Naming round 24 (D-180): the polycycle templates in fusion_general.POLYCYCLES.

`heptalene` was written as a 13-atom [8, 7] skeleton, so it never matched a
real heptalene; fusion naming then fell back to `cyclohepta[7]annulene` as the
parent and named colchicine's benzo[a]heptalene core "benzocyclohepta[7]annulene",
a name OPSIN reads as a different structure (the app withheld it).

The table below is (atom count, ring sizes) read from OPSIN's parse of each
template's own name on 2026-10-05, so a template cannot drift from the
parent it is named for. The check is on the skeleton (all bonds single).
"""
import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.ring_naming import fusion_general as fg

EXPECTED = {
    "naphthalene": (10, (6, 6)),
    "azulene": (10, (5, 7)),
    "indene": (9, (5, 6)),
    "pentalene": (8, (5, 5)),
    "heptalene": (12, (7, 7)),
    "biphenylene": (12, (4, 6, 6)),
    "as-indacene": (12, (5, 5, 6)),
    "s-indacene": (12, (5, 5, 6)),
    "acenaphthylene": (12, (5, 6, 6)),
    "fluorene": (13, (5, 6, 6)),
    "phenalene": (13, (6, 6, 6)),
    "fluoranthene": (16, (5, 6, 6, 6)),
    "triphenylene": (18, (6, 6, 6, 6)),
    "pyrene": (16, (6, 6, 6, 6)),
    "chrysene": (18, (6, 6, 6, 6)),
    "tetracene": (18, (6, 6, 6, 6)),
    "tetraphene": (18, (6, 6, 6, 6)),
    "picene": (22, (6, 6, 6, 6, 6)),
    "pentacene": (22, (6, 6, 6, 6, 6)),
    "perylene": (20, (6, 6, 6, 6, 6)),
    "indole": (9, (5, 6)),
    "isoindole": (9, (5, 6)),
    "indolizine": (9, (5, 6)),
    "indazole": (9, (5, 6)),
    "quinolizine": (10, (6, 6)),
    "quinoline": (10, (6, 6)),
    "isoquinoline": (10, (6, 6)),
    "phthalazine": (10, (6, 6)),
    "quinoxaline": (10, (6, 6)),
    "quinazoline": (10, (6, 6)),
    "cinnoline": (10, (6, 6)),
    "pteridine": (10, (6, 6)),
    "phenanthridine": (14, (6, 6, 6)),
    "perimidine": (13, (6, 6, 6)),
    "phenazine": (14, (6, 6, 6)),
    "phenoxazine": (14, (6, 6, 6)),
    "phenothiazine": (14, (6, 6, 6)),
    "phenoxathiine": (14, (6, 6, 6)),
    "thianthrene": (14, (6, 6, 6)),
    "oxanthrene": (14, (6, 6, 6)),
    "aceanthrylene": (16, (5, 6, 6, 6)),
    "acephenanthrylene": (16, (5, 6, 6, 6)),
    "arsindole": (9, (5, 6)),
    "phosphindole": (9, (5, 6)),
    "isoarsindole": (9, (5, 6)),
    "isophosphindole": (9, (5, 6)),
    "arsindolizine": (9, (5, 6)),
    "phosphindolizine": (9, (5, 6)),
    "arsinoline": (10, (6, 6)),
    "phosphinoline": (10, (6, 6)),
    "isoarsinoline": (10, (6, 6)),
    "isophosphinoline": (10, (6, 6)),
    "arsinolizine": (10, (6, 6)),
    "phosphinolizine": (10, (6, 6)),
    "arsanthridine": (14, (6, 6, 6)),
    "phosphanthridine": (14, (6, 6, 6)),
    "anthracene": (14, (6, 6, 6)),
    "phenanthrene": (14, (6, 6, 6)),
    "acridine": (14, (6, 6, 6)),
    "carbazole": (13, (5, 6, 6)),
    "xanthene": (14, (6, 6, 6)),
    "thioxanthene": (14, (6, 6, 6)),
    "selenoxanthene": (14, (6, 6, 6)),
    "telluroxanthene": (14, (6, 6, 6)),
    "purine": (9, (5, 6)),
    "acridarsine": (14, (6, 6, 6)),
    "acridophosphine": (14, (6, 6, 6)),
}


def test_every_template_has_an_expectation():
    assert set(fg.POLYCYCLES) == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_template_matches_what_its_name_means(name):
    m = Chem.MolFromSmiles(fg.POLYCYCLES[name])
    atoms, sizes = EXPECTED[name]
    assert m.GetNumAtoms() == atoms
    assert tuple(sorted(len(r) for r in m.GetRingInfo().AtomRings())) == sizes


@pytest.mark.parametrize(
    "smiles,expected",
    [
        # colchicine: a benzene fused to heptalene, not "benzocyclohepta[7]annulene"
        ("COc1cc2c(c(OC)c1OC)-c1ccc(OC)c(=O)cc1[C@@H](NC(C)=O)CC2",
         "N-[(7S)-1,2,3,10-tetramethoxy-9-oxo-5,6,7,9-tetrahydrobenzo[a]heptalen-7-yl]acetamide"),
        ("C1=CC=CC2=C1C=CC=C1C=CC=CC=C12", "benzo[a]heptalene"),
    ],
)
def test_benzo_heptalene_is_named_on_heptalene(smiles, expected):
    assert name_smiles(smiles) == expected
