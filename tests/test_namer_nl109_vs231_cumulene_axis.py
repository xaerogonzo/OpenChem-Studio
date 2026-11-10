"""NL-109 remainder (WS1, fork): CIP Validation Suite VS231 cumulene axis.

CIP Validation Suite entry VS231 (`compounds.smi`, rule P-93.5.1.4.2.2, stereo units TH + TH3):
``CC=[C@]=C1CC[C@H](CC1)CC`` with author labels ``2p 4p 7s``.

Round 92 fixed VS207, VS214 and VS279 (legacy RDKit perception). VS231 is still open: RDKit
assigns no chiral tag or CIP code on the cumulene axis after non-legacy perception, so the engine
emits a flat ylidene name. OPSIN parses that name but it does not pin the input stereochemistry.

Measured 2026-11-10 on this branch (see also ``docs/NAMING_LIMITATIONS_PLAN.md``, NL-109).
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

VS231_SMILES = "CC=[C@]=C1CC[C@H](CC1)CC"
VS231_SUITE_LABELS = "2p 4p 7s"
# Connectivity-correct name the engine emits today (no p / s / E descriptors).
VS231_FLAT_NAME = "1-ethyl-4-(prop-1-en-1-ylidene)cyclohexane"


def test_nl109_vs231_rdkit_does_not_tag_the_cumulene_axis():
    Chem.SetUseLegacyStereoPerception(False)
    mol = Chem.MolFromSmiles(VS231_SMILES)
    assert mol is not None
    Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
    try:
        from rdkit.Chem import rdCIPLabeler

        rdCIPLabeler.AssignCIPLabels(mol)
    except Exception:
        pass
    cip_on_atoms = {
        atom.GetIdx(): atom.GetPropsAsDict().get("_CIPCode")
        for atom in mol.GetAtoms()
        if atom.GetPropsAsDict().get("_CIPCode")
    }
    assert cip_on_atoms == {}
    # Suite label 7s is the cyclohexyl [C@H]; it may appear as unassigned ('?') and is still omitted from the name.
    centers = Chem.FindMolChiralCenters(mol, includeUnassigned=True)
    assert centers == [(6, "?")]


def test_nl109_vs231_name_is_flat_pending_fork_work():
    assert name_smiles(VS231_SMILES) == VS231_FLAT_NAME


@pytest.mark.xfail(
    reason="NL-109 / fork: cumulene axial p descriptors (CIP TH3) are not perceived or named yet",
    strict=True,
)
def test_nl109_vs231_will_carry_cumulene_axis_descriptors_when_implemented():
    import re

    name = name_smiles(VS231_SMILES)
    # CIP extended-tetrahedral p (not the substring of ``prop``).
    assert re.search(r"\d+p", name)
