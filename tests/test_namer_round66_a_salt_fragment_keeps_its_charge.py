"""Naming round 66 (D-306): a charged organic fragment of a salt must say its charge.

`NC(S)=[NH+]C(=NOCc1ccccc1)c1ccccc1.[Cl-]` was `N-[amino(sulfanyl)methylidene]-N'-(phenylmethoxy)benzenecarboximidamide chloride` and `CCCCCCCCCCCCCCCCOC(=O)c1ccc(C#[NH+])cc1.[Cl-]`
`hexadecyl 4-(azanylidynemethyl)benzoate chloride`: the NEUTRAL compound and a chloride, which is a different substance. The same cation drawn alone was named correctly. Two things let it
through: the charge guard judges a single fragment and leaves a salt alone, and the salt path asks a fragment for the cation form only where a suffix can carry the charge (an amidine's
or nitrile's protonated N is neither), so the fragment fell to the neutral STANDALONE form and the counter-ion's word hid the lost charge. Each charged fragment is now checked by the same
guard and, when it fails, named the way it is named alone, which raises if that cannot keep the charge either. Found by the round-66 population: census ions paired with a counter-ion.

The same population refused 135 anilides (`Cc1cccc([N-]CC(=O)C)c1` with any counter-ion, and alone): `_render_amine_anion` could not give the anion the `-aminide` suffix because a ketone, an
amide or a ring amine is senior to the amine, and the refusal ("render_failed") closed the road to the plan search, which names that anion as the `azanidyl` prefix and reads back.

A fragment of NET charge zero (a zwitterion drawn beside `[Na+].[Cl-]`) is judged too, by polarity: `sodium chloride 6-azanidyl-7-...-7H-purine` had lost its cation. And the guard counted `oxalate`
as one anion for two carboxylates, so the fragment check would have refused `disodium oxalate`, which named before; the word now counts for two (the dianion alone was refused too).
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
    ("a protonated amidine beside chloride", "NC(S)=[NH+]C(=NOCc1ccccc1)c1ccccc1.[Cl-]",
     "[amino(sulfanyl)methylidene][phenyl(phenylmethoxyimino)methyl]azanium chloride"),
    ("a protonated nitrile beside chloride", "CCCCCCCCCCCCCCCCOC(=O)c1ccc(C#[NH+])cc1.[Cl-]",
     "{{4-[(hexadecyloxy)carbonyl]phenyl}methylidyne}azanium chloride"),
]

NAMED += [
    ("an anilide beside a ketone is the azanidyl prefix", "Cc1cccc([N-]CC(=O)C)c1", "1-[(3-methylphenyl)azanidyl]propan-2-one"),
    ("an anilide beside a ring amine", "Cc1cccc([N-]CCN2CCCC2)c1", "1-{2-[(3-methylphenyl)azanidyl]ethyl}pyrrolidine"),
    ("the same anilide as a sodium salt", "Cc1cccc([N-]CC(=O)C)c1.[Na+]", "sodium 1-[(3-methylphenyl)azanidyl]propan-2-one"),
]

NAMED += [
    ("a zwitterion beside sodium chloride keeps its cation", "CC(C)=CCn1c[nH+]c2ncnc([NH-])c21.[Na+].[Cl-]",
     "sodium chloride 6-azanidyl-7-(3-methylbut-2-en-1-yl)-7H-purin-9-ium"),
    ("a phenolate-ammonium zwitterion in a salt", "[O-]c1ccccc1C(CC[NH+]1CCOCC1)c1ccccc1.[Na+].[Cl-]",
     "sodium chloride 4-[3-(2-oxidophenyl)-3-phenylpropyl]morpholin-4-ium"),
    ("oxalate is two charges in one word", "[O-]C(=O)C(=O)[O-]", "oxalate"),
    ("an oxalate salt is not judged short of an anion", "[Na+].[Na+].[O-]C(=O)C(=O)[O-]", "disodium oxalate"),
    ("a dication beside oxalate", "[NH3+]CC[NH3+].[O-]C(=O)C(=O)[O-]", "ethane-1,2-bis(aminium) oxalate"),
]

KEPT = [
    ("an anilide that is the senior group keeps aminide", "c1ccccc1[NH-]", "benzenaminide"),
    ("an ammonium salt", "CC[NH3+].[Cl-]", "ethanaminium chloride"),
    ("a sodium carboxylate", "[Na+].CC(=O)[O-]", "sodium acetate"),
    ("a pyridinium salt", "c1cc[nH+]cc1.[Cl-]", "pyridin-1-ium chloride"),
]

ALL = NAMED + KEPT


def test_a_bare_ion_is_not_judged():
    # a hydron has no heavy atom and a name with no cation word (`hydron chloride`); the fragment check leaves a one-atom ion to the retained-name leaf
    assert name_smiles("[H+].[Cl-]") == "hydron chloride"


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_salt(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected

    def organic(smi):
        frags = [Chem.MolFromSmiles(f) for f in smi.split(".")]
        return max(frags, key=lambda m: m.GetNumHeavyAtoms())

    assert Chem.GetFormalCharge(organic(back)) == Chem.GetFormalCharge(organic(smiles)), (expected, back)
    assert pop._inchikey(organic(back)) == pop._inchikey(organic(smiles)), (expected, back)
