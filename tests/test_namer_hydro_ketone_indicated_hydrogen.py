"""Naming round 31 (D-203): the indicated hydrogen of a hydro-named ring ketone is the planner's, not the retained lookup's placeholder.

The retained lookup writes the parent's DEFAULT indicated hydrogen into its text: for a purine whose C5 and N9 are saturated and whose C6 is a carbonyl it wrote
`5,9-dihydro-2H-purine`, where C2 is sp2 and C6 is the carbonyl. The P-58.2 planner (`indicated_hydrogen_p58.plan_hydrogens`) puts the indicated hydrogen where the
book does, on the carbon that carries the group (`5,9-dihydro-6H-purin-6-one`), but `_resolve` checked the OLD text against its plan, found an atom (the 2) that the plan
did not describe, and declined, so the placeholder reached the name: `8-(methylsulfanyl)-5,9-dihydro-2H-purin-6-one`, which OPSIN reads as ANOTHER molecule (a CH2 at C2).
The check now ignores the old text's indicated-hydrogen labels and keeps the hydro ones, which are read off the structure.

Found in round 30, where a labelled sweep called it a label defect: the UNLABELLED name was already another molecule. Every name pinned here is read back through
OPSIN to its input on canonical SMILES and InChIKey.
"""
from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name): every tautomer of a purin-6-one with a saturated ring atom, which are the shapes that carried the placeholder.
NAMED = [
    ("5,9-dihydro, with a substituent", "N1C(SC)=NC2C(=O)N=CN=C21", "8-(methylsulfanyl)-5,9-dihydro-6H-purin-6-one"),
    ("5,7-dihydro", "O=C1N=CN=C2C1NC=N2", "5,7-dihydro-6H-purin-6-one"),
    ("1,4,5,9-tetrahydro", "O=C1NC=NC2C1N=CN2", "1,4,5,9-tetrahydro-6H-purin-6-one"),
    ("1,4,5,7-tetrahydro", "O=C1C2NC=NC2N=CN1", "1,4,5,7-tetrahydro-6H-purin-6-one"),
    ("3,4,5,7-tetrahydro", "O=C1C2NC=NC2NC=N1", "3,4,5,7-tetrahydro-6H-purin-6-one"),
    ("1,4,5,9-tetrahydro, the other orientation", "O=C1C2N=CNC2N=CN1", "1,4,5,9-tetrahydro-6H-purin-6-one"),
    ("1,4-dihydro", "O=C1C2=NC=NC2N=CN1", "1,4-dihydro-6H-purin-6-one"),
    # the same defect off the purine, found in a population of odd tautomers of census molecules
    ("an isoindolone", "O=C1C2CC=CCC2=C(O)N1c1cccc([N+](=O)[O-])c1", "1-hydroxy-2-(3-nitrophenyl)-2,3a,4,7-tetrahydro-3H-isoindol-3-one"),
]

# What this round leaves alone: the names whose retained text was already right.
UNCHANGED = [
    ("hypoxanthine's 1,7-dihydro tautomer", "O=C1NC=NC2=C1NC=N2", "1,7-dihydro-6H-purin-6-one"),
    ("hypoxanthine's 1,9-dihydro tautomer", "O=C1NC=NC2=C1N=CN2", "1,9-dihydro-6H-purin-6-one"),
    ("a benzopyranone", "O=c1ccc2ccccc2o1", "2H-1-benzopyran-2-one"),
    ("a dihydroquinolinone", "O=C1CCc2ccccc2N1", "3,4-dihydroquinolin-2(1H)-one"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_indicated_hydrogen_is_on_the_group_carbon(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_name_reads_back_to_the_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_a_labelled_hydro_purinone_keeps_its_label_and_the_new_indicated_hydrogen():
    """The round 30 case that exposed this: the deuterium's locant was always right."""
    assert name_smiles("[2H]N1C(SC)=NC2C(=O)N=CN=C21") == "8-(methylsulfanyl)-5,9-dihydro(9-2H)-6H-purin-6-one"
    assert name_smiles("CSC1=NC2C(=O)N=CN=C2[15NH]1") == "8-(methylsulfanyl)-5,9-dihydro(9-15N)-6H-purin-6-one"


def test_the_hydro_positions_of_the_old_text_must_still_agree_with_the_plan(monkeypatch):
    """The relaxed check ignores only the old text's INDICATED hydrogen. A parent whose hydro positions are not the structure's is still declined.

    No real molecule reaches that branch (2178 census and odd-tautomer molecules, none), so the parent is captured from a real run and its text altered.
    """
    import dataclasses

    from openchem.vendor.iupac_namer.ring_naming import indicated_hydrogen_p58 as p58

    captured = []
    real = p58._resolve

    def spy(mol, named_parent, numbering, suffix_groups, free_valence=None):
        if (named_parent.name or "").startswith("5,9-dihydro-2H-purine"):
            captured.append((mol, named_parent, numbering, suffix_groups))
        return real(mol, named_parent, numbering, suffix_groups, free_valence)

    monkeypatch.setattr(p58, "_resolve", spy)
    name_smiles("N1C(SC)=NC2C(=O)N=CN=C21")
    assert captured, "the retained parent was not offered to the planner"
    mol, parent, numbering, groups = captured[0]
    assert real(mol, parent, numbering, groups) is not None
    wrong = dataclasses.replace(parent, name=parent.name.replace("5,9-dihydro", "1,9-dihydro"), stem=parent.stem.replace("5,9-dihydro", "1,9-dihydro"))
    assert real(mol, wrong, numbering, groups) is None
    # a hydro position that names no atom of the ring is declined too, not skipped
    nowhere = dataclasses.replace(parent, name=parent.name.replace("5,9-dihydro", "5,99-dihydro"), stem=parent.stem.replace("5,9-dihydro", "5,99-dihydro"))
    assert real(mol, nowhere, numbering, groups) is None
