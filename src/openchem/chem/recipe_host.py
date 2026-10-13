"""What a recipe needs from the chemistry layer: is this stored input still this molecule.

The pure model (`domain/recipe_run.py`, `domain/lewis_binder.py`) compares strings it is handed and does no
chemistry. These are the strings, and the one yes/no, it is handed.

**TWO QUESTIONS, ASKED DIFFERENTLY ON PURPOSE.**

* `constitution_key(mol)` is a KEY: a deterministic string for the drawing today, recorded in a run and compared
  later. Its stereo is exactly what the drawing specifies, so adding a wedge to an unspecified centre changes the key
  and a run recorded before it reads as stale. That errs toward asking again, which costs a rerun, and not toward
  presenting a number for a molecule the person has since made more specific.
* `run_describes(molblock, mol)` is a COMPARISON of a run's stored 3D input with the drawing. It cannot use a key,
  because a 3D conformer of a molecule whose centre the drawing leaves unspecified will have some stereo perceived
  from its coordinates, and a key comparison would call that an edit. So: the same constitution, charge and isotopes
  (stereo removed from both), and then any stereochemistry the DRAWING specifies must be matched by the run.

Hydrogens are removed on both sides first: a conformer carries explicit ones and a drawing usually does not, and
neither difference is a different molecule.
"""

from __future__ import annotations

from typing import Any

from rdkit import Chem


def _heavy(mol: Any) -> Any | None:
    """A copy of `mol` without removable hydrogens, or None when RDKit cannot sanitise it."""
    try:
        return Chem.RemoveHs(Chem.Mol(mol))
    except Exception:  # noqa: BLE001 - an unreadable structure is "cannot tell", never a crash
        return None


def constitution_key(mol: Any) -> str | None:
    """The drawing's identity as the stereochemistry it SPECIFIES, charge and isotopes included; None if unreadable."""
    heavy = _heavy(mol)
    if heavy is None:
        return None
    return Chem.MolToSmiles(heavy, isomericSmiles=True)


def formal_charge(mol: Any) -> int:
    return int(Chem.GetFormalCharge(mol))


def _without_stereo(mol: Any) -> str:
    plain = Chem.Mol(mol)
    Chem.RemoveStereochemistry(plain)
    return Chem.MolToSmiles(plain, isomericSmiles=True)


def run_describes(run_molblock: str, drawing: Any) -> bool | None:
    """Whether the structure a run was given is still `drawing`.

    True or False when that can be told; None when it cannot (no stored input, or one that will not parse), which a
    caller must treat as unverifiable and never as a yes.
    """
    if not run_molblock or not run_molblock.strip():
        return None
    run_mol = Chem.MolFromMolBlock(run_molblock, removeHs=False)
    if run_mol is None:
        return None
    run_heavy, drawing_heavy = _heavy(run_mol), _heavy(drawing)
    if run_heavy is None or drawing_heavy is None:
        return None
    if _without_stereo(run_heavy) != _without_stereo(drawing_heavy):
        return False
    return bool(run_heavy.HasSubstructMatch(drawing_heavy, useChirality=True))
