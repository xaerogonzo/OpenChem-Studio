"""Fully specified ionization states for salt composition. No pKa sidecar."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rdkit import Chem

from openchem.chem.salt_components import IdentityRefusal, fragment_key
from openchem.domain.salt_stoichiometry import IonizationRefusal, choose_ionization

REACHED_BY = (
    "tooling: consumed by tests/test_salt_ionization.py; ionization is not "
    "on the window yet"
)


@dataclass(frozen=True)
class SiteTransform:
    atom_index: int
    direction: str


def apply_site_transform(mol: Chem.Mol, transform: SiteTransform) -> Chem.Mol | IdentityRefusal:
    if transform.direction not in {"protonate", "deprotonate"}:
        return IdentityRefusal(code="invalid_site", reason="direction must be protonate or deprotonate.")
    if transform.atom_index < 0 or transform.atom_index >= mol.GetNumAtoms():
        return IdentityRefusal(code="invalid_site", reason="atom index is not in the parent.")
    copy = Chem.Mol(mol)
    atom = copy.GetAtomWithIdx(transform.atom_index)
    if transform.direction == "protonate":
        atom.SetNumExplicitHs(atom.GetTotalNumHs() + 1)
        atom.SetFormalCharge(atom.GetFormalCharge() + 1)
        atom.SetNoImplicit(True)
    else:
        total = atom.GetTotalNumHs()
        if total < 1:
            return IdentityRefusal(code="invalid_site", reason="that atom has no hydrogen to remove.")
        atom.SetNumExplicitHs(total - 1)
        atom.SetFormalCharge(atom.GetFormalCharge() - 1)
        atom.SetNoImplicit(True)
    try:
        Chem.SanitizeMol(copy)
    except (ValueError, RuntimeError):
        return IdentityRefusal(code="unsanitizable", reason="the ionized structure could not be sanitized.")
    return copy


def ionize_at_sites(
    mol: Chem.Mol, transforms: Sequence[SiteTransform]
) -> str | IdentityRefusal | IonizationRefusal:
    current: Chem.Mol | IdentityRefusal = mol
    for transform in transforms:
        if isinstance(current, IdentityRefusal):
            return current
        current = apply_site_transform(current, transform)
    if isinstance(current, IdentityRefusal):
        return current
    key = fragment_key(current)
    if isinstance(key, IdentityRefusal):
        return key
    return choose_ionization([key])
