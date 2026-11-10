"""NL-109 remainder (WS1): CIP Validation Suite VS231 cumulene axis.

CIP Validation Suite entry VS231 (`compounds.smi`, rule P-93.5.1.4.2.2, stereo units TH + TH3):
``CC=[C@]=C1CC[C@H](CC1)CC`` with author labels ``2p 4p 7s``.

Round 92 fixed VS207, VS214 and VS279 (legacy RDKit perception). VS231 needed an engine
stamp: RDKit still assigns no chiral tag or CIP code on the cumulene axis after
non-legacy perception, so the namer restores ``p``/``P``/``m``/``M`` from the SMILES
``=[C@]=`` / ``=[C@@]=`` winding (P-93.5.1.4).

Measured 2026-11-10 (RDKit gap) and 2026-11-10 (engine ``p`` and paired ring ``s``).
"""

from __future__ import annotations

import re

from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.perception.atoms import AtomAnalysis
from openchem.vendor.iupac_namer.perception.cumulene import (
    PAIRED_TETRA_PROP,
    smiles_atom_windings,
    stamp_cumulene_helix_from_smiles,
)
from openchem.vendor.iupac_namer.perception.stereo import StereoAnalysis

VS231_SMILES = "CC=[C@]=C1CC[C@H](CC1)CC"


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


def test_nl109_vs231_smiles_winding_lands_on_the_allene_centre():
    mol = Chem.MolFromSmiles(VS231_SMILES)
    windings = smiles_atom_windings(VS231_SMILES)
    assert len(windings) == mol.GetNumAtoms()
    assert windings[2] == "@"
    stamp_cumulene_helix_from_smiles(mol, VS231_SMILES)
    assert mol.GetAtomWithIdx(2).GetProp("_CumuleneHelix") == "p"


def test_nl109_vs231_stereo_analysis_emits_axial_p():
    mol = Chem.MolFromSmiles(VS231_SMILES)
    stamp_cumulene_helix_from_smiles(mol, VS231_SMILES)
    stereo = StereoAnalysis(mol, AtomAnalysis(mol))
    axial = stereo.axial_centers
    assert len(axial) == 1
    assert axial[0].descriptor == "p"
    assert axial[0].atom_idx == 2


def test_nl109_vs231_ring_centre_pairs_s_with_p():
    mol = Chem.MolFromSmiles(VS231_SMILES)
    stamp_cumulene_helix_from_smiles(mol, VS231_SMILES)
    assert mol.GetAtomWithIdx(6).GetProp(PAIRED_TETRA_PROP) == "s"
    stereo = StereoAnalysis(mol, AtomAnalysis(mol))
    tetra = [c for c in stereo.tetrahedral_centers if c.atom_idx == 6]
    assert len(tetra) == 1
    assert tetra[0].descriptor == "s"


def test_nl109_vs231_name_cites_cumulene_p_and_ring_s():
    name = name_smiles(VS231_SMILES)
    assert re.search(r"\d+p", name)
    assert re.search(r"\d+s", name)
    assert name == "(1s)-1-ethyl-4-[(1p)-prop-1-en-1-ylidene]cyclohexane"


def test_nl109_vs231_opposite_winding_cites_m_and_ring_r():
    assert (
        name_smiles("CC=[C@@]=C1CC[C@H](CC1)CC")
        == "(1r)-1-ethyl-4-[(1m)-prop-1-en-1-ylidene]cyclohexane"
    )


def test_nl109_vs231_ring_winding_flips_the_paired_letter():
    assert (
        name_smiles("CC=[C@]=C1CC[C@@H](CC1)CC")
        == "(1r)-1-ethyl-4-[(1p)-prop-1-en-1-ylidene]cyclohexane"
    )


def test_nl109_allene_without_another_centre_is_uppercase_p():
    mol = Chem.MolFromSmiles("CC=[C@]=CC")
    stamp_cumulene_helix_from_smiles(mol, "CC=[C@]=CC")
    assert mol.GetAtomWithIdx(2).GetProp("_CumuleneHelix") == "P"
