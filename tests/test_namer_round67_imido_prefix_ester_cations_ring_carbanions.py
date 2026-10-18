"""Naming round 67 (D-309 .. D-313): the open items of rounds 60 to 66 that had a cause.

* D-309 an N-substituted imidic / imidothioic acid that is not the senior group (`CCSC(S)=NC`) was an ErrorTree INSIDE a name (`({[NAMING ERROR: ...]}sulfanyl)ethane`): the demoted
  `=NH` was cited as `imino` and the N-methyl of `=N-CH3` was claimed by nothing. It is cited with its substituents, `(methylimino)`, and the name reads back.
* D-310 two cations in an ESTER (`X-yl Y-oate` with a protonated ether, ketone or amide on each side) were refused: the ester word pair needs the acid half to be a cation parent beside an alkyl
  word, which the guard refuses. Such an ester is named by the substitutive route (an acyloxy / oxo-alkoxy prefix). A carbamate keeps its ester word.
* D-311 `...azaniumyl}ethan-1-ol` for an ammonium beside a NITRO group: the nitro's O- counted as an anion that made the zwitterion rule skip the `-aminium` suffix, and the salt's anion
  word then read as an ester of the alcohol (`...ethan-1-ol acetate`). The cation is the parent: `2-hydroxy-N-...ethan-1-aminium acetate`.
* D-312 a ring CARBANION beside another anion (a phenolate, a carboxylate, a thiolate, an azolide) was dropped from the name and the guard refused it; it takes the `-id-` infix an azolide
  already took (`...-4,5-dioxoazolidin-3-id-2-yl]benzen-1-olate`).
* D-314 a zwitterion with a carved alkoxide beside `[Na+].[Cl-]` took the STANDALONE form in the salt path and its carbamate was written `[...-9-yl]methanecarbamate`; the salt path
  promotes it to the anion form as the top-level promotion does (`_carved_acid_anion_sites`).
* D-313 the guard did not read `-2'-id-` (a primed locant) as an anion word, so a spiro azolide beside a carboxylate was refused although the name carried both charges.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import naming_ion_populations as pop  # noqa: E402

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

NAMED = [
    ("an S-alkyl N-methyl dithiocarbonimidate", "CCSC(S)=NC", "{[(methylimino)(sulfanyl)methyl]sulfanyl}ethane"),
    ("an O-alkyl one", "CCOC(S)=NC", "[(methylimino)(sulfanyl)methoxy]ethane"),
    ("the same group beside a protonated ether", "C[OH+]c1ccc(CSC(S)=Nc2ccc(F)cc2F)cc1",
     "[4-({[(2,4-difluorophenylimino)(sulfanyl)methyl]sulfanyl}methyl)phenyl](methyl)oxidanium"),
    ("an amine with the group on its nitrogen", "CCN(C)C(S)=NC", "N-methyl-N-[(methylimino)(sulfanyl)methyl]ethanamine"),
    ("two protonated sites across an ester", "Cc1ccc([OH+]CC(=O)OCC(=[OH+])Nc2cc(Cl)ccc2Cl)cc1",
     "2,5-dichloro-N-(2-{2-[(4-methylphenyl)oxidaniumyl]-1-oxoethoxy}-1-oxidaniumylideneethyl)aniline"),
    ("a protonated ketone and ether across an ester", "CCCCC(=[OH+])c1ccc(OC(=O)/C=C/c2ccc([OH+]C)cc2)cc1",
     "methyl(4-{(1E)-3-[4-(1-oxidaniumylidenepentyl)phenoxy]-3-oxoprop-1-en-1-yl}phenyl)oxidanium"),
    ("an ammonium beside a nitro group is the aminium parent", "COc1ccc([N+](=O)[O-])cc1C[NH2+]CCO",
     "2-hydroxy-N-[(2-methoxy-5-nitrophenyl)methyl]ethan-1-aminium"),
    ("and its acetate", "COc1ccc([N+](=O)[O-])cc1C[NH2+]CCO.CC(=O)[O-]", "2-hydroxy-N-[(2-methoxy-5-nitrophenyl)methyl]ethan-1-aminium acetate"),
    ("a ring carbanion beside a phenolate", "CCOc1cc([C@@H]2[C-](C(=O)c3ccc(OC)cc3)C(=O)C(=O)N2CCOC)ccc1[O-]",
     "2-ethoxy-4-[(2S)-3-(4-methoxybenzoyl)-1-(2-methoxyethyl)-4,5-dioxoazolidin-3-id-2-yl]benzen-1-olate"),
    ("an aromatic carbanion beside a thiolate", "CCCC[c-]1c(=O)nc([S-])n(C)c1=O", "5-butyl-1-methyl-4,6-dioxo-1,3-diazin-5-id-2-thiolate"),
    ("a spiro azolide beside a carboxylate", "N#CC1=C(N)Oc2n[n-]c(-c3ccc(Cl)cc3)c2[C@@]12C(=O)N(CC(=O)[O-])c1ccccc12",
     "{(3S)-6'-amino-3'-(4-chlorophenyl)-5'-cyano-2-oxospiro[2,3-dihydro-1H-indole-3,4'-2,4-dihydropyrano[2,3-c]pyrazole]-2'-id-1-yl}acetate"),
]

NAMED += [
    ("a zwitterion with an alkoxide and a carbamate in a salt", "C[NH2+]C1Cn2c3c(c(COC(N)=O)c2C1[O-])C(=O)C(OC)=C(C)C3=O.[Na+].[Cl-]",
     "sodium chloride 9-[(carbamoyloxy)methyl]-7-methoxy-6-methyl-2-(methylazaniumyl)-5,8-dioxo-2,3,5,8-tetrahydro-1H-pyrrolo[1,2-a]indol-1-olate"),
]

KEPT = [
    ("an unsubstituted imidothioic acid keeps its suffix", "CCSC(S)=N", "(ethylsulfanyl)methanimidothioic acid"),
    ("a lone ring carbanion keeps the -ide parent", "CCOc1cc([C@@H]2[C-](C(=O)c3ccc(OC)cc3)C(=O)C(=O)N2CCOC)ccc1O",
     "(2S)-2-(3-ethoxy-4-hydroxyphenyl)-3-(4-methoxybenzoyl)-1-(2-methoxyethyl)-4,5-dioxopyrrolidin-3-ide"),
    ("a carbamate keeps its ester word beside two cations", "C[OH+]C1=C(C)C(=O)c2c(c(COC(N)=O)c3n2CC(N)C3[OH2+])C1=O",
     "[2-amino-6-methyl-7-(methyloxidaniumyl)-1-oxidaniumyl-5,8-dioxo-2,3,5,8-tetrahydro-1H-pyrrolo[1,2-a]indol-9-yl]methyl carbamate"),
]

ALL = NAMED + KEPT


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


def test_no_name_in_the_set_contains_an_error():
    assert all("NAMING ERROR" not in name_smiles(smiles) for _l, smiles, _e in ALL)


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected

    def organic(smi):
        frags = [Chem.MolFromSmiles(f) for f in smi.split(".")]
        return max(frags, key=lambda m: m.GetNumHeavyAtoms())

    assert Chem.GetFormalCharge(organic(back)) == Chem.GetFormalCharge(organic(smiles)), (expected, back)
    assert pop._inchikey(organic(back)) == pop._inchikey(organic(smiles)), (expected, back)
