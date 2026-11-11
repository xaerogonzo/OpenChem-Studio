"""Fragments of a drawing, identified by graph, for salt Mode B.

Does not call chem.substance._components: that key is (formula, charge).
"""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem


@dataclass(frozen=True)
class IdentityRefusal:
    code: str
    reason: str


def fragment_formal_charge(mol: Chem.Mol) -> int:
    return sum(atom.GetFormalCharge() for atom in mol.GetAtoms())


def fragment_key(mol: Chem.Mol) -> str | IdentityRefusal:
    copy = Chem.Mol(mol)
    for atom in copy.GetAtoms():
        atom.SetAtomMapNum(0)
    try:
        Chem.SanitizeMol(copy)
    except (ValueError, RuntimeError):
        return IdentityRefusal(
            code="unsanitizable",
            reason="The fragment could not be sanitized, so it has no identity key.",
        )
    smiles = Chem.MolToSmiles(copy, isomericSmiles=True)
    charge = fragment_formal_charge(copy)
    parsed = Chem.MolFromSmiles(smiles)
    if parsed is None:
        return IdentityRefusal(
            code="unsanitizable",
            reason="The canonical SMILES of the fragment could not be read back.",
        )
    if fragment_formal_charge(parsed) != charge:
        return IdentityRefusal(
            code="charge_mismatch",
            reason=(
                f"The graph key {smiles!r} has charge "
                f"{fragment_formal_charge(parsed):+d}, not {charge:+d}."
            ),
        )
    return smiles
