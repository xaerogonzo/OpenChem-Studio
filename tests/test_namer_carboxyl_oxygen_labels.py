"""Naming round 30: the two oxygens of a carboxyl group are different atoms, and a suffix cites only the atoms it names.

Round 29 (phase 2) left three things in its sweep of 400 labelled census molecules, all of them a label cited in the wrong place or twice:

* **D-197**: the carbonyl oxygen and the hydroxyl oxygen of an acid, which is also the alkoxy oxygen of the ester the acid component is carved from, were both
  `(1-18O)`: `CC(=[18O])OC` and `CC(=O)[18O]C` were both `methyl (1-18O)acetate`, two molecules under one name that OPSIN reads as neither. OPSIN reads the
  carbonyl oxygen as `(18O)acetate` / `-1-(18O)oate` and the hydroxyl or alkoxy oxygen, cited with the element as its locant, as `(O-18O)acetate` / `-1-(O-18O)oate`;
* **D-200**: a ketone's group lists its two NEIGHBOURS among its atoms and only its oxygen is named by `-one`, so the nitrogen of `CC(=O)N1CCCCC1` was cited by its ring
  AND by the ketone, `1-[(1-15N)piperidin-1-yl]ethan-1-(15N)one`: two 15N for one, a wrong molecule. The aryl carbon an acetyl hangs on was cited the same way;
* **D-201**: a nuclide between the locant and the suffix word hid the vowel from the elision, `prop-2-ene-1-(18O)amide` where the book's unlabelled
  `prop-2-enamide` and `prop-2-en-1-ol` lose the infix's e.

* **D-202**: a nuclide in a FUSED ring system defeated every ring namer that read the ring from the molecule rather than through `extract_ring_mol`: `[1,2,4]triazolo[4,3-b]pyridazine`
  with a labelled bridgehead nitrogen was `[NAMING ERROR ...]`, as were eleven of 300 census molecules with one ring nitrogen labelled. `ring_naming.name_ring_system` now looks the
  ring up without its nuclides, for every kind of ring at once; the label is placed afterwards from the full molecule.

Every name pinned here is read back through OPSIN to its input on canonical SMILES and InChIKey.
"""
from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
NAMED = [
    # an ester's acid component: the carbonyl oxygen, the alkoxy oxygen, and both
    ("ester carbonyl oxygen, retained acetate", "CC(=[18O])OC", "methyl (18O)acetate"),
    ("ester alkoxy oxygen, retained acetate", "CC(=O)[18O]C", "methyl (O-18O)acetate"),
    ("both ester oxygens", "CC(=[18O])[18O]C", "methyl (18O,O-18O)acetate"),
    ("ester carbonyl oxygen, systematic acid", "C=CC(=[18O])OC", "methyl prop-2-en-1-(18O)oate"),
    ("ester alkoxy oxygen, systematic acid", "C=CC(=O)[18O]C", "methyl prop-2-en-1-(O-18O)oate"),
    ("ester alkoxy oxygen, butanoate", "CCCC(=O)[18O]CC", "ethyl butan-1-(O-18O)oate"),
    ("ester alkoxy oxygen, benzoate", "O=C([18O]C)c1ccccc1", "methyl (O-18O)benzoate"),
    ("an aryl ester's alkoxy oxygen", "Cc1cccc(-c2ccc([18O]C(=O)c3ccccc3Br)c(C)c2)c1", "2-methyl-4-(3-methylphenyl)phenyl 2-bromobenzene-1-(O-18O)carboxylate"),
    ("a diester, one alkoxy oxygen", "O=C(OCC)CC(=O)[18O]C", "3-ethyl 1-methyl (O-18O)propanedioate"),
    # the free acid
    ("acid carbonyl oxygen, retained", "CC(=[18O])O", "(18O)acetic acid"),
    ("acid hydroxyl oxygen, retained", "CC(=O)[18OH]", "(O-18O)acetic acid"),
    ("acid hydroxyl oxygen, systematic", "CCC(=O)[18OH]", "propan-1-(O-18O)oic acid"),
    ("acid carbonyl oxygen, systematic", "C=CC(=[18O])O", "prop-2-en-1-(18O)oic acid"),
    ("benzoic acid hydroxyl oxygen", "O=C([18OH])c1ccccc1", "(O-18O)benzoic acid"),
    ("benzoic acid carbonyl oxygen", "OC(=[18O])c1ccccc1", "(18O)benzoic acid"),
    ("acid deuterium keeps its element locant", "CC(=O)O[2H]", "(O-2H)acetic acid"),
    ("a carboxylate is named from its acid", "CC(=O)[18O-]", "(O-18O)acetate"),
    ("a carboxylate salt", "[Na+].CC(=O)[18O-]", "sodium (O-18O)acetate"),
    # D-200: a ketone names only its oxygen
    ("an N-acylpiperidine's nitrogen is cited once", "CC(=O)[15N]1CCCCC1", "1-[(1-15N)piperidin-1-yl]ethan-1-one"),
    ("an aryl ketone's ring carbon is cited once", "CC(=O)c1ccc(Cc2cc[13c](C(C)=O)cc2)cc1", "1-{4-[(4-acetylphenyl)methyl](1-13C)phenyl}ethan-1-one"),
    ("the ketone's own oxygen is still cited", "[18O]=C(C)c1ccccc1", "1-phenylethan-1-(18O)one"),
    ("an aliphatic ketone's oxygen", "CC(=[18O])CCC", "pentan-2-(18O)one"),
    # D-201: the infix's e before the vowel, the bracket between
    ("an amide of an unsaturated acid", "C=CC(=[18O])N", "prop-2-en-1-(18O)amide"),
    ("an unsaturated alcohol", "C=CC[18OH]", "prop-2-en-1-(18O)ol"),
    ("a yne amide", "CC#CC(=[18O])N", "but-2-yn-1-(18O)amide"),
    # D-202: a nuclide in a fused ring system
    ("a labelled bridgehead nitrogen", "c1ccc2nnc[15n]2n1", "(4-15N)[1,2,4]triazolo[4,3-b]pyridazine"),
    ("a labelled bridgehead nitrogen with substituents", "CN1CCN(c2ccc3nnc(Cl)[15n]3n2)CC1", "3-chloro-6-(4-methylpiperazin-1-yl)(4-15N)[1,2,4]triazolo[4,3-b]pyridazine"),
    ("a labelled nitrogen of a tricycle", "Cc1cnc2ccc3c(nc(NO)[15n]3C)c2c1", "2-(hydroxyamino)-3,8-dimethyl(3-15N)-3H-imidazo[4,5-f]quinoline"),
    ("a labelled thiazole nitrogen of a benzo-fused ring", "COc1ccc(C(=O)Nc2[15n]c3ccc4ccccc4c3s2)c(OC)c1", "2,4-dimethoxy-N-[(3-15N)naphtho[2,1-d][1,3]thiazol-2-yl]benzamide"),
    ("a labelled nitrogen of a pyrazolopyrimidine", "CC(C)NC(=O)c1nc2ncc(C=O)c[15n]2n1", "6-formyl-N-(propan-2-yl)(8-15N)[1,2,4]triazolo[1,5-a]pyrimidine-2-carboxamide"),
    # a labelled ring is still the ring it is, as a substituent
    ("a labelled pyridin-3-yl", "O=C(NCc1cc[13cH]nc1)[C@H]1C[C@@H]1c1ccccc1", "(1S,2S)-2-phenyl-N-{[(6-13C)pyridin-3-yl]methyl}cyclopropane-1-carboxamide"),
    ("a labelled pyridin-2-yl", "Cc1ccc2c(c1)[nH]c1c(N3CCN(c4c[13cH]ccn4)CC3)ncnc12", "7-methyl-4-{4-[(4-13C)pyridin-2-yl]piperazin-1-yl}-5H-pyrimido[5,4-b]indole"),
]

# Unlabelled molecules keep their names: nothing here may move.
UNCHANGED = [
    ("methyl acetate", "CC(=O)OC", "methyl acetate"),
    ("acetic acid", "CC(=O)O", "acetic acid"),
    ("methyl benzoate", "COC(=O)c1ccccc1", "methyl benzoate"),
    ("prop-2-enamide", "C=CC(=O)N", "prop-2-enamide"),
    ("prop-2-en-1-ol", "C=CCO", "prop-2-en-1-ol"),
    ("an N-acylpiperidine", "CC(=O)N1CCCCC1", "1-(piperidin-1-yl)ethan-1-one"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[row[0] for row in NAMED])
def test_the_label_is_cited_once_and_where_opsin_reads_it(label, smiles, expected):
    assert name_smiles(smiles) == expected


@pytest.mark.parametrize("label,smiles,expected", UNCHANGED, ids=[row[0] for row in UNCHANGED])
def test_an_unlabelled_molecule_keeps_its_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[row[0] for row in NAMED])
def test_the_name_reads_back_to_the_labelled_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_the_two_oxygens_of_an_ester_are_two_names():
    """D-197 itself: two molecules, one name, was the defect."""
    assert name_smiles("CC(=[18O])OC") != name_smiles("CC(=O)[18O]C")
    assert name_smiles("CC(=[18O])O") != name_smiles("CC(=O)[18OH]")


def test_a_nuclide_is_cited_as_often_as_the_molecule_has_it():
    """D-200: the count of a nuclide in the name is the count in the molecule, whatever group names which atom."""
    for smiles, nuclide, count in [
        ("CC(=O)[15N]1CCCCC1", "15N", 1),
        ("CC(=[18O])[18O]C", "18O", 2),
        ("CC(=O)c1ccc(Cc2cc[13c](C(C)=O)cc2)cc1", "13C", 1),
    ]:
        assert name_smiles(smiles).count(nuclide) == count, smiles
