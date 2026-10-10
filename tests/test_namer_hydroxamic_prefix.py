"""Naming round 38 (D-211): a hydroxamic acid that is not the principal group no longer gains a carbon or loses its N-substituent.

`C(=O)N(R)OH` under a carboxylic acid or an ester was written with the prefix "hydroxycarbamoyl", which INCLUDES the carbonyl carbon, while the chain already named it:
`OC(=O)CC(=O)NO` (three carbons) came out as `3-(hydroxycarbamoyl)propanoic acid` (four), and with an N-substituent (`OC(=O)CC(=O)N(C)O`) the same name, the methyl gone: a
different molecule, whatever the reader makes of it. Hydrazides, thioamides, imidic acids and amides each had this repaired in an earlier round (`_DEMOTED_AMIDE_TYPES_PREPROC`);
the hydroxamic acid had never been added. 292 of 336 hydroxamic acids under an acid, an ester or a ring (13 seeds, one substituent on each free carbon) named another molecule;
now none does, and none that was right changed.

Three places needed the same type: the split into oxo + amino when the carbon is in the chain, the flood-fill of the N-substituent (the N-OH oxygen is a declared context atom, so it
arrives as "hydroxy" on the nitrogen exactly as an N-methoxy does), and the prefix of a group off the chain (`[hydroxy(methyl)carbamoyl]`). A substituent chain also keeps the carbon
of an N-substituted hydroxamic acid, because "hydroxycarbamoyl" has no place for the N-substituent.

Every name pinned here is read back through OPSIN to its input on canonical SMILES and InChIKey.
"""
from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name): the hydroxamic acid is NOT the principal group.
NAMED = [
    ("malonic acid, hydroxamic", "OC(=O)CC(=O)NO", "3-(hydroxyamino)-3-oxopropanoic acid"),
    ("glutaric acid, hydroxamic", "OC(=O)CCCC(=O)NO", "5-(hydroxyamino)-5-oxopentanoic acid"),
    ("an N-methyl hydroxamic acid", "OC(=O)CC(=O)N(C)O", "3-[hydroxy(methyl)amino]-3-oxopropanoic acid"),
    ("an N-phenyl hydroxamic acid", "OC(=O)CC(=O)N(O)c1ccccc1", "3-[hydroxy(phenyl)amino]-3-oxopropanoic acid"),
    ("a branched chain", "OC(=O)C(C)C(=O)N(C)O", "3-[hydroxy(methyl)amino]-2-methyl-3-oxopropanoic acid"),
    ("an ester on the acid side", "COC(=O)CC(=O)N(C)O", "methyl 3-[hydroxy(methyl)amino]-3-oxopropanoate"),
    ("an N-ethyl one", "CCOC(=O)CCC(=O)N(O)CC", "ethyl 4-[ethyl(hydroxy)amino]-4-oxobutanoate"),
    ("on the alcohol side of an ester", "CC(=O)OCC(=O)N(C)O", "2-[hydroxy(methyl)amino]-2-oxoethyl acetate"),
    ("the alcohol side, one carbon further", "CC(=O)OCCC(=O)N(C)O", "3-[hydroxy(methyl)amino]-3-oxopropyl acetate"),
    ("the alcohol side of a benzoate", "c1ccccc1C(=O)OCC(=O)N(C)O", "2-[hydroxy(methyl)amino]-2-oxoethyl benzoate"),
    ("the alcohol side of a carbonate", "CCOC(=O)OCC(=O)N(C)O", "ethyl {2-[hydroxy(methyl)amino]-2-oxoethyl} carbonate"),
    (
        "the census row (322625)",
        "CC(=O)OC(C(=O)N(O)c1ccccc1OCc1ccccc1)c1ccccc1",
        "2-{hydroxy[2-(phenylmethoxy)phenyl]amino}-2-oxo-1-phenylethyl acetate",
    ),
    ("off a benzene ring", "OC(=O)c1ccccc1C(=O)N(C)O", "2-[hydroxy(methyl)carbamoyl]benzoic acid"),
    ("off a benzene ring, N-phenyl", "OC(=O)c1ccccc1C(=O)N(O)c1ccccc1", "2-[hydroxy(phenyl)carbamoyl]benzoic acid"),
    ("off a cyclohexane ring", "OC(=O)C1CCCCC1C(=O)N(C)O", "2-[hydroxy(methyl)carbamoyl]cyclohexane-1-carboxylic acid"),
    ("off a ring, under an ester", "COC(=O)c1ccccc1C(=O)N(C)O", "methyl 2-[hydroxy(methyl)carbamoyl]benzoate"),
]

# Names that did not change: the unsubstituted (NH) hydroxamic acid as a prefix was already right, and the principal group is named as an N-hydroxy amide.
UNCHANGED = [
    ("NH hydroxamic acid off a ring", "OC(=O)c1ccccc1C(=O)NO", "2-(hydroxycarbamoyl)benzoic acid"),
    ("NH hydroxamic acid on the alcohol side", "CC(=O)OCC(=O)NO", "(hydroxycarbamoyl)methyl acetate"),
    ("the principal group", "CC(=O)NO", "N-hydroxyacetamide"),
    ("the principal group, N-methyl", "CC(=O)N(C)O", "N-hydroxy-N-methylacetamide"),
    ("benzohydroxamic acid", "O=C(NO)c1ccccc1", "N-hydroxybenzamide"),
    ("N-methylbenzohydroxamic acid", "CN(O)C(=O)c1ccccc1", "N-hydroxy-N-methylbenzamide"),
    ("vorinostat's skeleton", "ONC(=O)CCCCCCC(=O)Nc1ccccc1", "N1-hydroxy-N8-phenyloctanediamide"),
    ("under a substituent that is not a group", "COCC(=O)N(O)C", "N-hydroxy-2-methoxy-N-methylacetamide"),
    ("an N-methoxy amide under an acid", "OC(=O)CC(=O)N(OC)C", "3-[methoxy(methyl)amino]-3-oxopropanoic acid"),
    ("a hydrazide under an acid", "OC(=O)CC(=O)NN", "3-hydrazinyl-3-oxopropanoic acid"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_hydroxamic_acid_is_named(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_name_reads_back_to_the_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_an_n_substituted_hydroxamic_acid_never_loses_its_substituent_to_the_bare_prefix():
    """`hydroxycarbamoyl` means -C(=O)NHOH. It must appear only for an NH hydroxamic acid."""
    for _label, smiles, expected in NAMED:
        mol = Chem.MolFromSmiles(smiles)
        substituted = mol.HasSubstructMatch(Chem.MolFromSmarts("C(=O)N([#6])[OX2H]"))
        if substituted:
            assert "hydroxycarbamoyl" not in expected, (smiles, expected)
            assert "hydroxycarbamoyl" not in name_smiles(smiles), smiles
