"""Naming round 49 (D-241 .. D-245): the ions rounds 44 to 48 left refused or unreadable.

D-241: a protonated imidate, thioimidate, isourea or amidoxime (`NC(=[NH2+])OC`, `CC(=[NH2+])S`, `NC(=[NH+]O)C(Cl)(Cl)Cl`) was refused by round 46's charge guard, because no classifier claimed
it and the plan search neutralised it (`1-iminoethane-1-thiol`). The cation is the parent: `(1-sulfanylethylidene)azanium`, the form the engine already wrote for `COC(=[NH2+])CC`.
D-242: the anion of an N-acyl carbamate or an ester-bearing imide was a `NAMING ERROR`, and saccharin's anion was refused: an ester carbon is `alkoxycarbonyl` (`acetyl(methoxycarbonyl)azanide`),
and the added hydrogen `2(3H)` goes before the ring `-ide` (`1,1,3-trioxo-1,2-benzothiazol-2-ide`).
D-243: the thiolate of a thioamide or isothiourea carried `sulfanide` as a prefix (`{[amino(sulfanide)methylidene]carbamoyl}benzene`, unreadable) and `aminoimino` (OPSIN reads an N-N bond).
The prefix for S- is `sulfido`, and `amino` + `imino` / `hydroxy` + `imino` are bracketed so they stay two groups.
D-244: a sulfamide is the amide of sulfuric acid, so a carboxylic or sulfonic acid, an ester or an acid halide outranks it (P-41): `2-[(dimethylaminosulfonyl)amino]benzoic acid`, not
`N-(2-carboxyphenyl)-N',N'-dimethylsulfamide`.
D-245: an amidinium zwitterion with both acids on one quaternary carbon was refused: the masked ester can sit at the chain end with another prefix between its `methoxy` and `oxo`.

Every name pinned here is read back through OPSIN to its input, charge included (the `-sulfonamidate` row excepted: OPSIN reads it neutral).
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
IMINIUM = [
    ("a thioimidate cation", "CC(=[NH2+])S", "(1-sulfanylethylidene)azanium"),
    ("an isothiourea cation", "NC(S)=[NH2+]", "[amino(sulfanyl)methylidene]azanium"),
    ("an isourea cation", "NC(=[NH2+])OC", "[amino(methoxy)methylidene]azanium"),
    ("an acyl imidate cation", "CC(=[NH2+])OC(C)=O", "[1-(acetyloxy)ethylidene]azanium"),
    ("an amidoxime cation", "CC(N)=[NH+]O", "(1-aminoethylidene)(hydroxy)azanium"),
    ("the census amidoxime cation", "NC(=[NH+]O)C(Cl)(Cl)Cl", "(1-amino-2,2,2-trichloroethylidene)(hydroxy)azanium"),
    ("an N-methyl isothiourea cation", "C[NH+]=C(S)N", "[amino(sulfanyl)methylidene](methyl)azanium"),
    ("unchanged: an imidate cation", "COC(=[NH2+])CC", "(1-methoxypropylidene)azanium"),
]

CARBAMATE_AND_SACCHARIN = [
    ("an N-acyl carbamate", "CC(=O)[N-]C(=O)OC", "acetyl(methoxycarbonyl)azanide"),
    ("an N-methyl carbamate", "C[N-]C(=O)OC", "(methoxycarbonyl)(methyl)azanide"),
    ("an N-aryl carbamate", "c1ccccc1[N-]C(=O)OCC", "(ethoxycarbonyl)(phenyl)azanide"),
    ("a bis(carbamate)", "[N-](C(=O)OC)C(=O)OC", "bis(methoxycarbonyl)azanide"),
    ("a carbamate with a compound alkoxy", "O=C(OCCCl)[N-]C", "[(2-chloroethoxy)carbonyl](methyl)azanide"),
    ("an ureidocarbamate", "O=C(OC)[N-]C(=O)N", "carbamoyl(methoxycarbonyl)azanide"),
    ("saccharin's anion", "O=C1[N-]S(=O)(=O)c2ccccc12", "1,1,3-trioxo-1,2-benzothiazol-2-ide"),
    ("a chlorosaccharin anion", "O=C1[N-]S(=O)(=O)c2cc(Cl)ccc12", "6-chloro-1,1,3-trioxo-1,2-benzothiazol-2-ide"),
    ("unchanged: phthalimide's anion", "O=C1[N-]C(=O)c2ccccc12", "1,3-dioxo-1,3-dihydro-2H-isoindol-2-ide"),
]

THIOLATES = [
    ("a thiolate beside an N-substituted imine", "NC([S-])=NC", "amino(methylimino)methanethiolate"),
    ("an isothiourea thiolate, unsubstituted", "[S-]C(=N)N", "amino(imino)methanethiolate"),
]

SULFAMIDE_BESIDE_ACID = [
    ("a benzoic acid", "OC(=O)c1ccccc1NS(=O)(=O)N(C)C", "2-[(dimethylaminosulfonyl)amino]benzoic acid"),
    ("a propanoic acid", "OC(=O)CCNS(=O)(=O)N(C)C", "3-[(dimethylaminosulfonyl)amino]propanoic acid"),
    ("an unsubstituted sulfamide", "OC(=O)c1ccccc1NS(=O)(=O)N", "2-[(aminosulfonyl)amino]benzoic acid"),
    ("an ester", "COC(=O)c1ccccc1NS(=O)(=O)N(C)C", "methyl 2-[(dimethylaminosulfonyl)amino]benzoate"),
    ("an acid chloride", "O=C(Cl)c1ccccc1NS(=O)(=O)N(C)C", "2-[(dimethylaminosulfonyl)amino]benzoyl chloride"),
    ("a sulfonic acid", "OS(=O)(=O)c1ccccc1NS(=O)(=O)N(C)C", "2-[(dimethylaminosulfonyl)amino]benzene-1-sulfonic acid"),
    ("unchanged: a nitrile", "N#Cc1ccccc1NS(=O)(=O)N(C)C", "N-(2-cyanophenyl)-N',N'-dimethylsulfamide"),
    ("unchanged: an alcohol", "Oc1ccccc1NS(=O)(=O)N(C)C", "N-(2-hydroxyphenyl)-N',N'-dimethylsulfamide"),
    ("unchanged: the bare sulfamide", "CNS(=O)(=O)NC", "N,N'-dimethylsulfamide"),
]

ZWITTERION = [
    ("both acids on a quaternary carbon", "NC(=[NH2+])C(C)(C(=O)[O-])C(=O)O", "2-carboxylato-3-hydroxy-2-methyl-3-oxopropanamidinium"),
    ("the carboxylate and the acid swapped", "NC(=[NH2+])C(C)(C(=O)O)C(=O)[O-]", "2-carboxylato-3-hydroxy-2-methyl-3-oxopropanamidinium"),
    ("a chlorine on the quaternary carbon", "NC(=[NH2+])C(Cl)(C(=O)[O-])C(=O)O", "2-carboxylato-2-chloro-3-hydroxy-3-oxopropanamidinium"),
    ("both acids on a ring carbon", "NC(=[NH2+])C1(C(=O)[O-])CCC1C(=O)O", "1-carboxylato-2-carboxycyclobutan-1-amidinium"),
    ("unchanged: one carbon between", "NC(=[NH2+])CC(C(=O)[O-])C(=O)O", "3-carboxylato-4-hydroxy-4-oxobutanamidinium"),
]

ALL = IMINIUM + CARBAMATE_AND_SACCHARIN + THIOLATES + SULFAMIDE_BESIDE_ACID + ZWITTERION


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


#: The N-acyl isothiourea thiolate. Its ANION-mode plan with the parent `methane` claims the carbonyl oxygen twice, which the suite's STRICT ownership mode raises and the default mode
#: turns into a rejected plan (the next plan names the molecule). That is a latent plan-generation flaw, recorded in KNOWN_LIMITATIONS, so this molecule is checked in the default mode.
ACYL_THIOLATE = ("NC([S-])=NC(=O)c1ccccc1", "amino(benzoylimino)methanethiolate")  # naming round 54 (D-263) took out the double claim of the carbonyl oxygen: the same name in both ownership modes


def test_the_s_minus_prefix_is_sulfido_not_the_parent_hydride_anion(monkeypatch):
    monkeypatch.setenv("OPENCHEM_NAMER_OWNERSHIP", "enforce")
    name = name_smiles(ACYL_THIOLATE[0])
    assert name == ACYL_THIOLATE[1]
    assert "sulfanide" not in name


@needs_opsin
def test_the_acyl_thiolate_name_reads_back(monkeypatch):
    from py2opsin import py2opsin

    monkeypatch.setenv("OPENCHEM_NAMER_OWNERSHIP", "enforce")
    back = py2opsin(name_smiles(ACYL_THIOLATE[0]))
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(ACYL_THIOLATE[0]))


def test_amino_and_imino_stay_two_groups():
    """`aminoimino` is read by OPSIN as an N-N bond; `hydroxyimino` is the group =N-OH."""
    assert "amino(imino)" in name_smiles("[S-]C(=N)N")
    assert name_smiles("NC(S)=N") == "aminomethanimidothioic acid"  # a suffix, no adjacent prefixes: untouched


def test_an_ordinary_amidinium_is_still_the_amidinium():
    """The imidate / thioimidate classifier must not take a carbon-bearing amidinium from its own."""
    assert name_smiles("CC(N)=[NH2+]").endswith("amidinium")
