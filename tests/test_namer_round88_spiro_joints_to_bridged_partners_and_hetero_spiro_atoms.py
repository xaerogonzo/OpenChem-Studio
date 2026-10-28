"""Naming round 88 (D-381 to D-385): spiro joints to BRIDGED and ortho-fused von Baeyer partners, and a heteroatom as the spiro atom.

Populations (a new shape: a curated ring or a bridged ring spiro-joined to a bridged partner, optionally with one substituent; adamantane, norbornane, bicyclo[2.2.2]octane, tropane, quinuclidine,
bicyclo[3.3.1]nonane, bicyclo[2.1.1]hexane, bicyclo[1.1.1]pentane, noradamantane, norcarane, decalin and two hetero-adamantanes). Of 400 plain molecules 295 read back, 99 were a NAMING ERROR and 6 named a
different thing; of 400 with a substituent 281 read back. After the fixes 400, 400, and 1,800 more over three further seeds. A second population put Si, N+ and P+ on the spiro atom (and B, Si, P, As, Se, Te, Sb in the
other rings, which every earlier generator had excluded): 35 of 200 read back, 1,100 of 1,100 after. Heteroelement RINGS with a carbon spiro atom were clean from the start (300 of 300). The slowest name was 1.2 s.

* D-381 a spiro joint to norcarane or bicyclo[3.1.0]/[3.2.0] had no spiro locant: a partner with no fusion name is typed `fused` but named von Baeyer, and only the `bridged` branch computed the locant.
* D-382 the lowest spiro locant of a tricyclic partner came from numberings that do not satisfy its `0^{3,6}` descriptor (`-2,` for the atom the descriptor numbers 4).
* D-383 two polycyclic partners were skipped by the polycyclic-spiro path, and the von Baeyer descriptor of the whole (`octacyclo[8.8.7.7.7.7.4.3.3]pentadecane`) outranked the spiro name because the articulation-split method had no rank.
* D-385 the E/Z of an exocyclic double bond (an ethylidene) at a PRIMED locant of a spiro name was dropped, so both geometries named one molecule (`6'-ethylidenespiro[...]`); OPSIN reads `(6'Z)-` and `(6'E)-`, so the gate admits a primed numeric locant for a spiro naming method.
* D-384 a silicon, N+ or P+ spiro atom with a polycyclic partner was a NAMING ERROR (161 of 200): Si is cited in both partners, N+ and P+ as `<loc>-azonia` / `<loc>-phosphonia`.
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
    ("D-381 norcarane, on the six-ring", "C1CCC2(CC1)CCCC1CC12", "spiro[cyclohexane-1,2'-bicyclo[4.1.0]heptane]"),
    ("D-381 norcarane, on the cyclopropane", "C1CCC2(CC1)C1CCCCC12", "spiro[cyclohexane-1,7'-bicyclo[4.1.0]heptane]"),
    ("D-381 bicyclo[3.1.0]hexane", "C1CC2C(C1)C21CC1", "spiro[cyclopropane-1,6'-bicyclo[3.1.0]hexane]"),
    ("D-381 bicyclo[3.2.0]heptane", "C1CC2CC3(CCCC3)C2C1", "spiro[cyclopentane-1,6'-bicyclo[3.2.0]heptane]"),
    ("D-381 a hetero partner", "C1CCC2C(C1)C21CCOCC1", "spiro[oxane-4,7'-bicyclo[4.1.0]heptane]"),
    ("D-382 tricyclo[3.2.1.0^{3,6}]octane", "C1CCC2(CC1)C1CC3CC1C2C3", "spiro[tricyclo[3.2.1.0^{3,6}]octane-4,1'-cyclohexane]"),
    ("D-382 the same, on a cyclopropane", "C1C2CC3C1C(C2)C31CC1", "spiro[tricyclo[3.2.1.0^{3,6}]octane-4,1'-cyclopropane]"),
    ("D-382 the one-atom bridge", "C1CCC2(CC1)C1CC3CC(C1)C32", "spiro[tricyclo[3.2.1.0^{3,6}]octane-7,1'-cyclohexane]"),
    ("D-383 indane and bicyclo[2.2.2]octane", "c1ccc2c(c1)CC1(C2)CC2CCC1CC2", "spiro[2,3-dihydro-1H-indene-2,2'-bicyclo[2.2.2]octane]"),
    ("D-383 two bridged", "C1CC2CC1CC21CC2CC1C2", "spiro[bicyclo[2.2.1]heptane-2,2'-bicyclo[2.1.1]hexane]"),
    ("D-383 two adamantanes", "C1C2CC3CC1CC(C2)C31C2CC3CC(C2)CC1C3", "spiro[adamantane-2,2'-adamantane]"),
    ("D-383 the descriptor that used to win", "C1CC2CCCC(C1)C21CCC2CC2C1", "spiro[bicyclo[4.1.0]heptane-3,9'-bicyclo[3.3.1]nonane]"),
    ("D-383 decalin and adamantane", "C1CCC2C(C1)CCCC21C2CC3CC(C2)CC1C3", "spiro[decahydronaphthalene-1,2'-adamantane]"),
    ("D-383 with a hydroxy group", "OC1CC2CCC1C21CC2CC1C2", "spiro[bicyclo[2.2.1]heptane-7,2'-bicyclo[2.1.1]hexane]-5-ol"),
    ("D-384 silicon, in both partners", "C1CC2CC1C[Si]23CCCC3", "spiro[silolane-1,2'-2-silabicyclo[2.2.1]heptane]"),
    ("D-384 silicon, fused partner", "C1CCC[Si]2(CC1)CCC1CCCCC12", "spiro[silepane-1,7'-7-silabicyclo[4.3.0]nonane]"),
    ("D-384 N+, fused partner", "C1CCC2C(C1)CC[N+]21CCC1", "1-azoniaspiro[cyclobutane-1,1'-octahydro-1H-indene]-1-ium"),
    ("D-384 N+, two bridged", "C1CC2CCC1C[N+]21CC2CCC1CC2", "2-azoniaspiro[bicyclo[2.2.2]octane-2,2'-bicyclo[2.2.2]octane]-2-ium"),
    ("D-384 P+", "C1CC[P+]2(C1)CC1CCC2C1", "2-phosphoniaspiro[bicyclo[2.2.1]heptane-2,1'-cyclopentane]-2-ium"),
    ("D-384 N+ beside a ring nitrogen", "C1CC[N+]2(CC1)CC1CCCC2N1", "6-azoniaspiro[8-azabicyclo[3.2.1]octane-6,1'-cyclohexane]-6-ium"),
    ("D-385 Z ethylidene on the primed ring", "C/C=C1/CCCCC12CC3CCC2C3", "(6'Z)-6'-ethylidenespiro[bicyclo[2.2.1]heptane-2,1'-cyclohexane]"),
    ("D-385 E ethylidene on the primed ring", "C/C=C1\\CCCCC12CC3CCC2C3", "(6'E)-6'-ethylidenespiro[bicyclo[2.2.1]heptane-2,1'-cyclohexane]"),
    ("D-385 beside ring centres", "C/C=C1/C[C@H]2CCN1C[C@@]21CCNNC1", "(4R,4'R,6'Z)-6'-ethylidenespiro[[1,2]diazinane-4,3'-1-azabicyclo[2.2.2]octane]"),
    ("D-385 a fused second partner", "C/C=C1/CCC2C(C1)CCCC21CCCC1", "(6'Z)-6'-ethylidenespiro[cyclopentane-1,1'-decahydronaphthalene]"),
    ("D-384 P+ beside a ring nitrogen", "C1CC2CC1C[P+]21CCC2CCC1N2", "2-phosphoniaspiro[8-azabicyclo[3.2.1]octane-2,2'-bicyclo[2.2.1]heptane]-2-ium"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[r[0] for r in NAMED])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


def _key(smiles: str) -> str:
    return inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))


@needs_opsin
@pytest.mark.parametrize("label,smiles", [(r[0], r[1]) for r in NAMED], ids=[r[0] for r in NAMED])
def test_the_name_reads_back_to_the_same_molecule(label, smiles):
    from py2opsin import py2opsin

    name = name_smiles(smiles)
    back = py2opsin(name)
    assert back, name
    assert _key(back) == _key(smiles), (name, back)


def test_a_von_baeyer_name_of_a_spiro_system_does_not_outrank_the_spiro_name():
    """The octacyclo descriptor of bicyclo[4.1.0]heptane joined to bicyclo[3.3.1]nonane existed, was unreadable, and won on rank."""
    assert "octacyclo" not in name_smiles("C1CC2CCCC(C1)C21CCC2CC2C1")
