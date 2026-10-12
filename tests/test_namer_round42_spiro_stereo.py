"""Naming round 42 (D-225): a spiro parent keeps the stereodescriptors of centres at a PRIMED or LETTERED locant, and cites a fused partner's junction by its letter.

D-225: the spiro numbering rebuilt every locant of a fused partner from its number alone, so a junction atom lost its letter before the prime: the 10b centre of a
pyrazolo[1,5-c][1,3]benzoxazine partner was cited `10'`, and the 3a and 6a centres of a pyrrolo[3,4-c]pyrrole partner `3` and `6` (a name with `3R,3S`, two centres at one
locant, which OPSIN cannot place). On top of that the stereo gate admitted a spiro parent's descriptor at a PLAIN integer locant only, and a spiro system with a bridged or
fused partner is classed "bridged" by perception, so the bridgeheads of a spiro bicyclo[2.2.1]heptane (`1'`, `4'`) were dropped too. Eight census rows named a stereoisomer
that carried none of its centres, or only some; across 79 stereoisomers of the census's spiro structures the stereo-exact count went 35 -> 73, with no wrong stereoisomer.

Every name pinned here is read back through OPSIN to its input on canonical SMILES and InChIKey (stereo included).
"""
from __future__ import annotations

import re
import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
CENSUS_SPIRO = [
    ('camphor-derived spirohydantoin', 'CC1(C)[C@H]2CC[C@]1(C)[C@@]1(C2)NC(=O)NC1=O',
     "(1'S,4R,4'S)-1',7',7'-trimethylspiro[[1,3]diazolidine-4,2'-bicyclo[2.2.1]heptane]-2,5-dione"),
    ('spirooxindole on pyrazolo[1,5-c][1,3]benzoxazine, nitro', 'O=C1Nc2ccccc2[C@]12Oc1ccc([N+](=O)[O-])cc1[C@H]1CC(c3ccc(Cl)cc3)=NN12',
     "(3S,10b'R)-2'-(4-chlorophenyl)-9'-nitrospiro[2,3-dihydro-1H-indole-3,5'-1,10b-dihydro-5H-pyrazolo[1,5-c][1,3]benzoxazine]-2-one"),
    ('spiropiperidine on pyrazolo[1,5-c][1,3]benzoxazine, bromo', 'Clc1ccc2c(c1)[C@@H]1C=C(c3ccc(Br)cc3)NN1C1(CCN(Cc3ccccc3)CC1)O2',
     "(10b'S)-1-benzyl-2'-(4-bromophenyl)-9'-chlorospiro[piperidine-4,5'-3,10b-dihydro-5H-pyrazolo[1,5-c][1,3]benzoxazine]"),
    ('pyrrolo[3,4-c]pyrrole spirooxindole, ammonium', 'COc1ccccc1CN1C(=O)[C@H]2[C@H](Cc3ccc(O)cc3)[NH2+][C@]3(C(=O)Nc4ccccc43)[C@H]2C1=O',
     "(1R,3S,3aR,6aS)-3-[(4-hydroxyphenyl)methyl]-5-[(2-methoxyphenyl)methyl]-2',4,6-trioxospiro[octahydropyrrolo[3,4-c]pyrrole-1,3'-2,3-dihydro-1H-indole]-2-ium"),
    ('pyrrolo[3,4-c]pyrrole spirooxindole, propanoic acid', 'Cc1cc(Cl)c2c(c1)[C@]1(N[C@@H](CCC(=O)O)[C@H]3C(=O)N(Cc4ccccc4)C(=O)[C@H]31)C(=O)N2',
     "3-{(1S,3S,3aS,6aR)-5-benzyl-7'-chloro-5'-methyl-2',4,6-trioxospiro[octahydropyrrolo[3,4-c]pyrrole-1,3'-2,3-dihydro-1H-indole]-3-yl}propanoic acid"),
    ('pyrrolo[3,4-c]pyrrole spirooxindole, acetamide', 'NC(=O)C[C@@H]1N[C@]2(C(=O)Nc3ccc(F)cc32)[C@H]2C(=O)N(Cc3ccc(F)cc3)C(=O)[C@@H]12',
     "2-{(1R,3S,3aR,6aS)-5'-fluoro-5-[(4-fluorophenyl)methyl]-2',4,6-trioxospiro[octahydropyrrolo[3,4-c]pyrrole-1,3'-2,3-dihydro-1H-indole]-3-yl}acetamide"),
    ('diazatricyclo spirooxindole ammonium', 'O=C1[C@H]2[C@@H](C(=O)N1c1cc(C(F)(F)F)ccc1Cl)[C@@]1(C(=O)Nc3ccccc31)[NH+]1CCC[C@@H]21',
     "(1'S,2'S,3R,6'R)-4'-[2-chloro-5-(trifluoromethyl)phenyl]-2,3',5'-trioxospiro[2,3-dihydro-1H-indole-3,7'-4,8-diazatricyclo[6.3.0.0^{2,6}]undecane]-8'-ium"),
    ('spiropiperidine on pyrazolo[1,5-c][1,3]benzoxazine, methoxy', 'COc1ccc(C2=C[C@@H]3c4cc(C)ccc4OC4(CCN(C(C)C)CC4)N3N2)cc1',
     "(10b'R)-2'-(4-methoxyphenyl)-9'-methyl-1-(propan-2-yl)spiro[piperidine-4,5'-3,10b-dihydro-5H-pyrazolo[1,5-c][1,3]benzoxazine]"),
]


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", CENSUS_SPIRO, ids=[row[0] for row in CENSUS_SPIRO])
def test_the_spiro_name_keeps_every_stereocentre(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", CENSUS_SPIRO, ids=[row[0] for row in CENSUS_SPIRO])
def test_the_name_reads_back_to_the_stereoisomer(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_no_two_descriptors_share_a_locant():
    """`3R,3S` named two centres at one locant: a junction atom's letter ("3a") had been dropped from its locant."""
    for _label, _smiles, expected in CENSUS_SPIRO:
        group = re.match(r"\(?\{?([0-9a-z'R,S]+)\)?", expected)
        if not group:
            continue
        locants = re.findall(r"(\d+[a-z]?'*)[RS]", expected.split("spiro", 1)[0] + expected.split("spiro", 1)[1].split("]", 1)[-1])
        assert len(locants) == len(set(locants)), expected


def test_a_junction_locant_keeps_its_letter_before_the_prime():
    assert "10b'" in name_smiles(CENSUS_SPIRO[2][1])
    assert "3aR" in name_smiles(CENSUS_SPIRO[3][1])


def test_a_spiro_cation_whose_nitrogen_is_a_centre_keeps_its_connectivity():
    """An N+ that is itself a stereocentre: OPSIN rejects its descriptors, so they are stripped and the name still names the skeleton (not exact, not wrong)."""
    smiles = "O=C1[C@H]2[C@H]3CCC[N@@H+]3[C@]3(C(=O)Nc4ccccc43)[C@@H]2C(=O)N1c1cc(C(F)(F)F)ccc1Cl"
    name = name_smiles(smiles)
    assert "spiro[2,3-dihydro-1H-indole-3,7'-4,8-diazatricyclo[6.3.0.0^{2,6}]undecane]-8'-ium" in name
