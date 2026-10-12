"""Naming round 44 (D-229 .. D-232): the anion is the parent, a protonated acylhydrazone keeps its charge, E/Z survives a methyl branch, and an ammonium keeps its carbons' stereo.

D-229: a thiolate or phenolate beside a nitrile, an aldehyde, an amide or a ketone is named for what it is under P-41 (anions outrank every neutral class that is not an acid... and the
acids too): the PARENT. `4-cyanobenzene-1-thiolate`, `4-cyanobenzen-1-olate`, `9-(2-cyanoethyl)-9H-purine-6-thiolate`. Round 43 cited the anion as an `oxido` / `sulfido` prefix
(`4-oxidobenzene-1-carbonitrile`), which keeps the charge but not the order. The carved-anion route also moved the charge to the WRONG group beside a neutral acid: `OC(=O)c1ccc([O-])cc1`
was `4-oxidobenzoate`, a carboxylate with a hydroxy; it is `4-carboxybenzen-1-olate`.

D-230: `C=[NH+]NC(=O)c1ccccc1`, a protonated acylhydrazone, was `N'-methylidenebenzohydrazide`: the `hydrazide` group matched a charged N' and wrote the compound neutral. It is a cation
(`benzamido(methylidene)azanium`).

D-231: `N-(2-methylbut-2-en-1-yl)acetamide` named both stereoisomers. A substituent is carved with the cut side replaced by H, so a bond that stopped being stereogenic there (two methyls on one
end) has no flag of its own, only the descriptor it inherits from the parent, and the collector looked the bond up by the flag.

D-232: a spiro ammonium with a stereocentre at a protonated N (`[N@H+]`) was named with NO descriptors: the nitrogen's descriptor (it has no configuration to cite) could not be placed by
OPSIN and the validation pass stripped every other descriptor of the parent with it. 73 -> 79 of 79 stereoisomers of the census's spiro structures read back exactly.

The octahydropyridazino[1,2-a][1,2]diazepine now has atom locants (the numbering `fusion_orientation.preferred_numberings` derives): 28 of 34 sweep cases were wrong, now 0.
Corrin has them too, from the numbering the Blue Book DRAWS (pdf p. 1158: C1-C19 with no 20, N21-N24, the NH on N24), checked against OPSIN's `k-chlorocorrin` at all 13 positions that carry a hydrogen:
10 of 33 sweep cases were wrong, now 0.

Every name pinned here is read back through OPSIN to its input on canonical SMILES and InChIKey (stereo included).
"""
from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
ANION_PARENT = [
    ('thiolate beside a nitrile', 'N#Cc1ccc([S-])cc1', '4-cyanobenzene-1-thiolate'),
    ('the sodium salt of a thiolate beside a nitrile', 'N#Cc1ccc([S-])cc1.[Na+]', 'sodium 4-cyanobenzene-1-thiolate'),
    ('phenolate beside a nitrile', 'N#Cc1ccc([O-])cc1', '4-cyanobenzen-1-olate'),
    ('thiolate on a purine with a nitrile chain', 'N#CCCn1cnc2c([S-])ncnc21', '9-(2-cyanoethyl)-9H-purine-6-thiolate'),
    ('thiolate beside an aldehyde', 'O=Cc1ccc([S-])cc1', '4-formylbenzene-1-thiolate'),
    ('thiolate beside an amide', 'NC(=O)c1ccc([S-])cc1', '4-carbamoylbenzene-1-thiolate'),
    ('alkyl thiolate beside a nitrile', 'N#CCC[S-]', '2-cyanoethane-1-thiolate'),
    ('two phenolates beside a nitrile', 'N#Cc1ccc([O-])c([O-])c1', '4-cyanobenzene-1,2-diolate'),
    ('thiolate beside a thioether and a nitrile', 'CSc1ccc(C#N)cc1[S-]', '5-cyano-2-(methylsulfanyl)benzene-1-thiolate'),
    ('phenolate beside a ketone', 'CC(=O)c1ccc([O-])cc1', '4-acetylbenzen-1-olate'),
    ('phenolate beside an ester', 'COC(=O)c1ccc([O-])cc1', '4-(methoxycarbonyl)benzen-1-olate'),
    ('phenolate beside a real OH', 'N#Cc1ccc([O-])cc1O', '4-cyano-3-hydroxybenzen-1-olate'),
    ('phenolate beside a neutral carboxylic acid (the charge was on the wrong group)', 'OC(=O)c1ccc([O-])cc1', '4-carboxybenzen-1-olate'),
    ('alkyl thiolate beside a neutral carboxylic acid', 'OC(=O)CC[S-]', '2-carboxyethane-1-thiolate'),
    ('phenolate beside a sulfonic acid', 'OS(=O)(=O)c1ccc([O-])cc1', '4-sulfobenzen-1-olate'),
    ('phenolate beside an amine', 'Nc1ccc([O-])cc1', '4-aminobenzen-1-olate'),
]

HYDRAZONE_CATION = [
    ('N-methylidene benzohydrazide', 'C=[NH+]NC(=O)c1ccccc1', 'benzamido(methylidene)azanium'),
    ('N-benzylidene acetohydrazide', 'c1ccc(cc1)C=[NH+]NC(=O)C', 'acetamido(benzylidene)azanium'),
    ('an anisylidene', 'COc1ccc(C=[NH+]NC(=O)c2ccccc2)cc1', 'benzamido[(4-methoxyphenyl)methylidene]azanium'),
    ('an acetone hydrazone', 'CC(=[NH+]NC(=O)C)C', 'acetamido(propan-2-ylidene)azanium'),
    ('a ketone hydrazone of isoniazid', 'CC(=[NH+]NC(=O)c1ccncc1)c1ccccc1', '(1-phenylethan-1-ylidene)(pyridine-4-carboxamido)azanium'),
    ('a N-methyl acylhydrazone', 'C=[NH+]N(C)C(=O)C', '[acetyl(methyl)amino](methylidene)azanium'),
    ('a thiohydrazone', 'C=[NH+]NC(=S)c1ccccc1', '(benzenecarbothioylamino)(methylidene)azanium'),
    ('a benzimidazole carbohydrazide (the census row)', 'COc1ccc(C=[NH+]NC(=O)c2ccc3nc[nH]c3c2)c(OC)c1OC', '(1H-benzimidazole-6-carboxamido)[(2,3,4-trimethoxyphenyl)methylidene]azanium'),
    ('the neutral hydrazone is unchanged', 'CC=NNC(=O)C', "N'-ethylideneacetohydrazide"),
]

ALKENYL_EZ = [
    ('2-methylbut-2-en-1-yl, E', 'C/C=C(C)/CNC(=O)C', 'N-[(2E)-2-methylbut-2-en-1-yl]acetamide'),
    ('2-methylbut-2-en-1-yl, Z', 'C/C=C(/C)CNC(=O)C', 'N-[(2Z)-2-methylbut-2-en-1-yl]acetamide'),
    ('2-methylbut-2-en-1-ylidene, E', 'C/C=C(C)/C=NNC(=O)C', "N'-[(2E)-2-methylbut-2-en-1-ylidene]acetohydrazide"),
    ('2-methylbut-2-en-1-ylidene, Z', 'C/C(C=NNC(=O)C)=C/C', "N'-[(2Z)-2-methylbut-2-en-1-ylidene]acetohydrazide"),
    ('2-methyl-3-phenylprop-2-en-1-ylidene, Z (the census row)', 'C/C(C=NNC(=O)C)=C/c1ccccc1', "N'-[(2Z)-2-methyl-3-phenylprop-2-en-1-ylidene]acetohydrazide"),
    ('2-methyl-3-phenylprop-2-en-1-ylidene, E', 'C/C(C=NNC(=O)C)=C\\c1ccccc1', "N'-[(2E)-2-methyl-3-phenylprop-2-en-1-ylidene]acetohydrazide"),
    ('an ester alcohol part', 'C/C=C(C)/COC(=O)C', '(2E)-2-methylbut-2-en-1-yl acetate'),
    ('a chlorine on the double bond is unchanged', 'C/C=C(Cl)/CNC(=O)C', 'N-[(2Z)-2-chlorobut-2-en-1-yl]acetamide'),
]

PYRIDAZINO = [
    ('acetamido at 8', 'CC(=O)NC1CCN2CCCCN2CC1', 'N-(octahydropyridazino[1,2-a][1,2]diazepin-8-yl)acetamide'),
    ('acetamido at 7', 'CC(=O)NC1CCCN2CCCCN2C1', 'N-(octahydropyridazino[1,2-a][1,2]diazepin-7-yl)acetamide'),
    ('acetamido at 6', 'CC(=O)NC1CCCCN2CCCCN12', 'N-(octahydropyridazino[1,2-a][1,2]diazepin-6-yl)acetamide'),
    ('acetamido at 1', 'CC(=O)NC1CCCN2CCCCCN12', 'N-(octahydropyridazino[1,2-a][1,2]diazepin-1-yl)acetamide'),
    ('acetamido at 2', 'CC(=O)NC1CCN2CCCCCN2C1', 'N-(octahydropyridazino[1,2-a][1,2]diazepin-2-yl)acetamide'),
]

SPIRO_AMMONIUM = [
    ('a spiro ammonium with a stereocentre at N+, isomer 1', 'O=C1[C@@H]2[C@@H](C(=O)N1c1cc(C(F)(F)F)ccc1Cl)[C@]1(C(=O)Nc3ccccc31)[N@H+]1CCC[C@@H]21', "(1'S,2'R,3S,6'R)-4'-[2-chloro-5-(trifluoromethyl)phenyl]-2,3',5'-trioxospiro[2,3-dihydro-1H-indole-3,7'-4,8-diazatricyclo[6.3.0.0^{2,6}]undecane]-8'-ium"),
    ('a spiro ammonium with a stereocentre at N+, isomer 2', 'O=C1[C@@H]2[C@@H]3CCC[N@H+]3[C@@]3(C(=O)Nc4ccccc43)[C@H]2C(=O)N1c1cc(C(F)(F)F)ccc1Cl', "(1'S,2'S,3S,6'S)-4'-[2-chloro-5-(trifluoromethyl)phenyl]-2,3',5'-trioxospiro[2,3-dihydro-1H-indole-3,7'-4,8-diazatricyclo[6.3.0.0^{2,6}]undecane]-8'-ium"),
    ('a spiro ammonium with a stereocentre at N+, isomer 3', 'O=C1[C@H]2[C@@H]3CCC[N@@H+]3[C@]3(C(=O)Nc4ccccc43)[C@H]2C(=O)N1c1cc(C(F)(F)F)ccc1Cl', "(1'S,2'R,3R,6'S)-4'-[2-chloro-5-(trifluoromethyl)phenyl]-2,3',5'-trioxospiro[2,3-dihydro-1H-indole-3,7'-4,8-diazatricyclo[6.3.0.0^{2,6}]undecane]-8'-ium"),
    ('a spiro ammonium with a stereocentre at N+, isomer 4', 'O=C1[C@H]2[C@@H]3CCC[N@H+]3[C@]3(C(=O)Nc4ccccc43)[C@H]2C(=O)N1c1cc(C(F)(F)F)ccc1Cl', "(1'S,2'R,3R,6'S)-4'-[2-chloro-5-(trifluoromethyl)phenyl]-2,3',5'-trioxospiro[2,3-dihydro-1H-indole-3,7'-4,8-diazatricyclo[6.3.0.0^{2,6}]undecane]-8'-ium"),
]

CORRIN = [
    ('acetamido on corrin C1', 'CC(=O)NC12CCC(=N1)C=C1CCC(=N1)C=C1CCC(=N1)C=C1CCC2N1', 'N-(corrin-1-yl)acetamide'),
    ('acetamido on corrin C2', 'CC(=O)NC1CC2=NC1C1CCC(=CC3=NC(=CC4=NC(=C2)CC4)CC3)N1', 'N-(corrin-2-yl)acetamide'),
    ('acetamido on corrin C5', 'CC(=O)NC1=C2CCC(=N2)C=C2CCC(=N2)C=C2CCC(N2)C2CCC1=N2', 'N-(corrin-5-yl)acetamide'),
    ('acetamido on corrin C7', 'CC(=O)NC1CC2=NC1=CC1=NC(CC1)C1CCC(=CC3=NC(=C2)CC3)N1', 'N-(corrin-7-yl)acetamide'),
    ('acetamido on corrin C10', 'CC(=O)NC1=C2CCC(=N2)C=C2CCC(N2)C2CCC(=N2)C=C2CCC1=N2', 'N-(corrin-10-yl)acetamide'),
    ('acetamido on corrin C17', 'CC(=O)NC1CC2NC1=CC1=NC(=CC3=NC(=CC4=NC2CC4)CC3)CC1', 'N-(corrin-17-yl)acetamide'),
]

ALL = ANION_PARENT + HYDRAZONE_CATION + ALKENYL_EZ + PYRIDAZINO + SPIRO_AMMONIUM + CORRIN


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


def test_an_anion_beside_a_senior_group_is_the_parent():
    """The invariant behind D-229: the name ENDS in the anion (`olate`, `thiolate`, `diolate`), the senior group is a prefix."""
    for label, smiles, expected in ANION_PARENT:
        assert expected.endswith(("olate", "thiolate", "diolate")), (label, expected)
        assert "oxido" not in expected and "sulfido" not in expected, expected


def test_the_two_stereoisomers_of_a_branched_alkenyl_have_two_names():
    pairs = [("C/C=C(C)/CNC(=O)C", "C/C=C(/C)CNC(=O)C"), ("C/C=C(C)/C=NNC(=O)C", "C/C(C=NNC(=O)C)=C/C")]
    for e_smiles, z_smiles in pairs:
        assert name_smiles(e_smiles) != name_smiles(z_smiles)
        assert "(2E)" in name_smiles(e_smiles) and "(2Z)" in name_smiles(z_smiles)


def test_a_protonated_acylhydrazone_has_a_cation_word():
    for _label, _smiles, expected in HYDRAZONE_CATION[:-1]:
        assert expected.endswith("azanium"), expected


def test_the_dropped_anion_net_still_repairs_or_refuses():
    """The engine-level net (`_restore_dropped_chalcogen_anion`) is no longer reached by any route above; it is what makes a FUTURE route that drops the charge fail loudly."""
    from openchem.vendor.iupac_namer.engine import _restore_dropped_chalcogen_anion

    nitrile = Chem.MolFromSmiles("N#Cc1ccc([S-])cc1")
    assert _restore_dropped_chalcogen_anion(nitrile, "4-sulfanylbenzene-1-carbonitrile") == "4-sulfidobenzene-1-carbonitrile"
    assert _restore_dropped_chalcogen_anion(nitrile, "4-cyanobenzene-1-thiolate") == "4-cyanobenzene-1-thiolate"
    with pytest.raises(ValueError):
        _restore_dropped_chalcogen_anion(Chem.MolFromSmiles("N#Cc1ccc([O-])cc1O"), "2,4-dihydroxybenzene-1-carbonitrile")
    assert _restore_dropped_chalcogen_anion(Chem.MolFromSmiles("N#C[S-]"), "thiocyanate") == "thiocyanate"
