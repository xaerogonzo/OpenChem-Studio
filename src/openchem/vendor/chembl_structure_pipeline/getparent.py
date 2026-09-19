#
#  Extracted from the ChEMBL_StructurePipeline project,
#  https://github.com/chembl/ChEMBL_Structure_Pipeline at commit
#  d252cd22d67674da4fa607b761c5b5a144cfdf07 (release 1.2.4 line).
#  Copyright (c) 2019 Greg Landrum; Copyright (c) 2019 The ChEMBL group.
#  MIT licence: see LICENSE.chembl-structure-pipeline beside this file.
#
#  VERBATIM except for three things, each marked "OpenChem:" below: the
#  data directory is this package, `exclude_flag` is inlined from
#  exclude_flag.py rather than imported, and the module docstring. The rule
#  is ChEMBL's, as documented in Bento et al. 2020 (J Cheminform 12:51) and
#  applied to ChEMBL's calculated properties -- "all but FULL_MWT and
#  FULL_MOLFORMULA are calculated on the parent structure" (ChEMBL 37 schema
#  documentation, COMPOUND_PROPERTIES). Re-deriving it would lose the special
#  cases that make it ChEMBL's rule rather than a salt stripper.
#
"""ChEMBL's GetParent: the parent compound of a salt, hydrate or mixture."""

import os

from rdkit import Chem
from rdkit.Chem.MolStandardize import rdMolStandardize

# OpenChem: the two list files are vendored beside this module.
_data_dir = os.path.dirname(os.path.abspath(__file__))
_solvents_file = os.path.join(_data_dir, "solvents.smi")
_salts_file = os.path.join(_data_dir, "salts.smi")

# OpenChem: inlined from chembl_structure_pipeline/exclude_flag.py, verbatim.
# Zn not in the list as we have some Zn containing compounds in ChEMBL
# most of them are simple salts
METAL_LIST = set(
    [
        "Sc",
        "Ti",
        "V",
        "Cr",
        "Mn",
        "Fe",
        "Co",
        "Ni",
        "Cu",
        "Ga",
        "Y",
        "Zr",
        "Nb",
        "Mo",
        "Tc",
        "Ru",
        "Rh",
        "Pd",
        "Cd",
        "In",
        "Sn",
        "La",
        "Hf",
        "Ta",
        "W",
        "Re",
        "Os",
        "Ir",
        "Pt",
        "Au",
        "Hg",
        "Tl",
        "Pb",
        "Bi",
        "Po",
        "Ac",
        "Ce",
        "Pr",
        "Nd",
        "Pm",
        "Sm",
        "Eu",
        "Gd",
        "Tb",
        "Dy",
        "Ho",
        "Er",
        "Tm",
        "Yb",
        "Lu",
        "Th",
        "Pa",
        "U",
        "Np",
        "Pu",
        "Am",
        "Cm",
        "Bk",
        "Cf",
        "Es",
        "Fm",
        "Md",
        "No",
        "Lr",
        "Ge",
        "Sb",
    ]
)


def exclude_flag(mol, includeRDKitSanitization=True):
    """
    Rules to exclude structures.

    - Metallic or non metallic with more than 7 boron atoms will be excluded
      due to problems when depicting borane compounds.
    """
    rdkit_fails = False
    exclude = False
    metallic = False
    boron_count = 0

    if type(mol) == str:
        mol = Chem.MolFromMolBlock(mol, sanitize=False)
        if includeRDKitSanitization:
            try:
                Chem.SanitizeMol(mol)
            except:
                rdkit_fails = True

    for atom in mol.GetAtoms():
        a_type = atom.GetSymbol()
        if a_type in METAL_LIST:
            metallic = True
        if a_type == "B":
            boron_count += 1

    if metallic or (not metallic and boron_count > 7) or rdkit_fails:
        exclude = True
    return exclude


def uncharge_mol(m):
    """

    >>> def uncharge_smiles(smi): return Chem.MolToSmiles(uncharge_mol(Chem.MolFromSmiles(smi)))
    >>> uncharge_smiles('[NH3+]CCC')
    'CCCN'
    >>> uncharge_smiles('[NH3+]CCC[O-]')
    'NCCCO'
    >>> uncharge_smiles('C[N+](C)(C)CCC[O-]')
    'C[N+](C)(C)CCC[O-]'
    >>> uncharge_smiles('CC[NH+](C)C.[Cl-]')
    'CCN(C)C.Cl'
    >>> uncharge_smiles('CC(=O)[O-]')
    'CC(=O)O'
    >>> uncharge_smiles('CC(=O)[O-].[Na+]')
    'CC(=O)[O-].[Na+]'
    >>> uncharge_smiles('[NH3+]CC(=O)[O-].[Na+]')
    'NCC(=O)[O-].[Na+]'
    >>> uncharge_smiles('CC(=O)[O-].C[NH+](C)C')
    'CC(=O)O.CN(C)C'

    Alcohols are protonated before acids:

    >>> uncharge_smiles('[O-]C([N+](C)C)CC(=O)[O-]')
    'C[N+](C)C(O)CC(=O)[O-]'

    And the neutralization is done in a canonical order, so atom ordering of the input
    structure isn't important:

    >>> uncharge_smiles('C[N+](C)(C)CC([O-])CC[O-]')
    'C[N+](C)(C)CC([O-])CCO'
    >>> uncharge_smiles('C[N+](C)(C)CC(CC[O-])[O-]')
    'C[N+](C)(C)CC([O-])CCO'

    """
    uncharger = rdMolStandardize.Uncharger(canonicalOrder=True)
    res = uncharger.uncharge(m)
    res.UpdatePropertyCache(strict=False)
    return res


def get_fragment_parent_mol(m, check_exclusion=False, neutralize=False, verbose=False):
    basepath = os.path.dirname(os.path.abspath(__file__))
    with open(_solvents_file) as inf:
        solvents = []
        for l in inf:
            if not l or l[0] == "#":
                continue
            l = l.strip().split("\t")
            if len(l) != 2:
                continue
            solvents.append((l[0], Chem.MolFromSmarts(l[1])))

    # there are a number of special cases for the ChEMBL salt stripping, so we
    # can't use the salt remover that's built into the RDKit standardizer.
    frags = []
    inputFrags = Chem.GetMolFrags(m, asMols=True, sanitizeFrags=False)
    for frag in inputFrags:
        frag = Chem.RemoveHs(frag, sanitize=False)
        frag.UpdatePropertyCache(strict=False)
        Chem.SetAromaticity(frag)
        frags.append(frag)
    keep = [1] * len(frags)
    for nm, solv in solvents:
        for i, frag in enumerate(frags):
            if (
                keep[i]
                and frag.GetNumAtoms() == solv.GetNumAtoms()
                and frag.GetNumBonds() == solv.GetNumBonds()
                and frag.HasSubstructMatch(solv)
            ):
                keep[i] = 0
                if verbose:
                    print(f"matched solvent {nm}")
        if not max(keep):
            break
    if not max(keep):
        # everything removed, we can just return the input molecule:
        if check_exclusion:
            exclude = exclude_flag(m, includeRDKitSanitization=False)
        else:
            exclude = False
        if neutralize:
            res = uncharge_mol(m)
        else:
            res = Chem.Mol(m)
        return res, exclude

    with open(_salts_file) as inf:
        salts = []
        for l in inf:
            if not l or l[0] == "#":
                continue
            l = l.strip().split("\t")
            if len(l) != 2:
                continue
            salts.append((l[0], Chem.MolFromSmarts(l[1])))

    keepFrags1 = []
    keepFrags2 = []
    for i, v in enumerate(keep):
        if v:
            keepFrags1.append(frags[i])
            keepFrags2.append(inputFrags[i])
    frags = keepFrags1
    inputFrags = keepFrags2
    keep = [1] * len(frags)

    for nm, salt in salts:
        for i, frag in enumerate(frags):
            if (
                keep[i]
                and frag.GetNumAtoms() == salt.GetNumAtoms()
                and frag.GetNumBonds() == salt.GetNumBonds()
                and frag.HasSubstructMatch(salt)
            ):
                if verbose:
                    print(f"matched salt {nm}")
                keep[i] = 0
        if not max(keep):
            break

    if not max(keep):
        # everything removed, keep everything:
        keep = [1] * len(frags)

    keepFrags = []
    seenSmis = set()
    for i, v in enumerate(keep):
        if not v:
            continue
        frag = inputFrags[i]
        if neutralize:
            cfrag = uncharge_mol(frag)
        else:
            cfrag = Chem.Mol(frag)
        keepFrags.append(i)
        # make sure there are no extraneous H atoms in the fragment:
        cfrag = Chem.RemoveHs(cfrag, sanitize=False)
        # need aromaticity perception to get a reasonable SMILES, but don't
        # want to risk a full sanitization:
        cfrag.ClearComputedProps()
        cfrag.UpdatePropertyCache(False)
        Chem.SanitizeMol(
            cfrag,
            sanitizeOps=Chem.SANITIZE_SYMMRINGS
            | Chem.SANITIZE_FINDRADICALS
            | Chem.SANITIZE_SETAROMATICITY
            | Chem.SANITIZE_ADJUSTHS,
        )

        seenSmis.add(Chem.MolToSmiles(cfrag))
    if len(seenSmis) == 1:
        # if we just have one fragment left, this is easy:
        # just copy the fragment
        res = inputFrags[keepFrags[0]]
    else:
        # otherwise we need to create a molecule from the remaining fragments
        res = inputFrags[keepFrags[0]]
        for idx in keepFrags[1:]:
            frag = inputFrags[idx]
            res = Chem.CombineMols(res, frag)

    if check_exclusion:
        exclude = exclude_flag(res, includeRDKitSanitization=False)
    else:
        exclude = False

    # if we still match the exclude flag after stripping salts, go
    # back to the parent species after solvent stripping. These are now
    # in the inputFrags list
    if exclude:
        res = inputFrags[0]
        for frag in inputFrags[1:]:
            res = Chem.CombineMols(res, frag)

    if neutralize:
        res = uncharge_mol(res)
    return res, exclude
