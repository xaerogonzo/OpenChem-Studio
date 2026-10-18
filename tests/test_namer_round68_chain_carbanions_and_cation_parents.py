"""Naming round 68 (D-315, D-316): a chain carbanion beside another anion, and the cation as the parent.

* D-315 round 67 gave a RING carbanion the `-id-` infix beside another anion's suffix. A CHAIN carbanion (`CC(=O)[CH-]C(=O)C(=O)[O-]`, the enolate of a 2,4-dioxo acid) was refused with
  the carbanion in no word of the name; it takes the infix too (`1-oxido-1-oxopentan-3-id-2,4-dione`, which OPSIN reads).
* D-316 a cation is senior to an alcohol, an acid or an amide (P-41, Table 4.1), but only a ring cation and an `-aminium` suffix had the rule. An ACYCLIC onium centre that is no part of
  the suffix group (an iminium, a hydrazinium, a nitrilium, a phosphonium ring) was a PREFIX, and the name ended in `-ol` (`2-[(phenylazaniumylidene)methyl]phenol`): beside a counter-ion, OPSIN
  reads `...phenol perchlorate` as the perchlorate ESTER of the phenol (27 salts in the round-66 population). The cation is the parent: `[(2-hydroxyphenyl)methylidene](phenyl)azanium`.
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
    ("a chain carbanion beside a carboxylate", "CC(=O)[CH-]C(=O)C(=O)[O-]", "1-oxido-1-oxopentan-3-id-2,4-dione"),
    ("the aryl one", "c1ccccc1C(=O)[CH-]C(=O)C(=O)[O-]", "4-oxido-4-oxo-1-phenylbutan-2-id-1,3-dione"),
    ("a carboxylate one carbon further", "CC(=O)[CH-]C(=O)CC(=O)[O-]", "6-oxido-6-oxohexan-3-id-2,4-dione"),
    ("an iminium beside a phenol", "Oc1ccccc1C=[NH+]c1ccccc1", "[(2-hydroxyphenyl)methylidene](phenyl)azanium"),
    ("the same with a perchlorate", "CCCCCCc1ccc(O)c(C=[NH+]c2ccccc2O)c1.[O-][Cl](=O)(=O)=O",
     "[(5-hexyl-2-hydroxyphenyl)methylidene](2-hydroxyphenyl)azanium perchlorate"),
    ("a hydrazinium acylated", "[NH3+]NC(=O)C(O)C(Cl)(Cl)Cl", "(3,3,3-trichloro-2-hydroxypropanamido)azanium"),
    ("an N-aminoazolium-like ammonium on a ring N", "[NH3+]n1cnnc1SCCO", "{3-[(2-hydroxyethyl)sulfanyl]-4H-1,2,4-triazol-4-yl}azanium"),
    ("a nitrilium beside phenols", "C[N+]#CC(=Cc1ccc(O)cc1)c1ccc(O)cc1", "[2,3-bis(4-hydroxyphenyl)prop-2-en-1-ylidyne](methyl)azanium"),
    ("a phosphonium ring with an alcohol", "OCCO[PH+]1OCCO1", "2-(2-hydroxyethoxy)-1,3,2-dioxaphospholan-2-ium"),
    ("a guanidinium beside a protonated amide", "NC(N)=[NH+]CCCC(=[OH+])N", "(4-amino-4-oxidaniumylidenebutyl)(diaminomethylidene)azanium"),
]

NAMED += [
    ("a phosphonium ring salt", "OCCO[PH+]1OCCO1.CS(=O)(=O)[O-]", "2-(2-hydroxyethoxy)-1,3,2-dioxaphospholan-2-ium methanesulfonate"),
]

KEPT = [
    ("an anion outranks the cation: an iminium acetate stays the anion's", "Oc1ccccc1C=[NH+]CC(=O)[O-]", "{[(2-hydroxyphenyl)methylidene]azaniumyl}acetate"),
    ("an ammonium keeps the aminium suffix", "OCC[NH3+]", "2-hydroxyethan-1-aminium"),
    ("an amino acid cation", "OC(=O)CC[NH3+]", "2-carboxyethan-1-aminium"),
    ("a quaternary ammonium", "OCC[N+](C)(C)C", "2-hydroxy-N,N,N-trimethylethan-1-aminium"),
    ("a sulfonium with an alcohol", "OCC[S+](C)C", "(2-hydroxyethyl)di(methyl)sulfanium"),
    ("a lone diketone carbanion", "CC(=O)[CH-]C(C)=O", "2,4-dioxopentan-3-ide"),
]

ALL = NAMED + KEPT


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


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
