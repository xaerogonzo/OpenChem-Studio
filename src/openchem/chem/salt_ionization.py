"""Fully specified ionization states for salt composition. No pKa sidecar."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rdkit import Chem

from openchem.chem.salt_components import (
    IdentityRefusal,
    fragment_formal_charge,
    fragment_key,
)
from openchem.domain.salt_stoichiometry import IonizationRefusal, choose_ionization

REACHED_BY = (
    "tooling: consumed by tests/test_salt_ionization.py; ionization is not "
    "on the window yet"
)


@dataclass(frozen=True)
class SiteTransform:
    atom_index: int
    direction: str


def _bonded_hydrogen_indexes(atom: Chem.Atom) -> list[int]:
    """Hydrogen *atoms* bonded to ``atom``. ``GetTotalNumHs()`` does not count these."""
    return [neighbor.GetIdx() for neighbor in atom.GetNeighbors() if neighbor.GetAtomicNum() == 1]


def apply_site_transform(mol: Chem.Mol, transform: SiteTransform) -> Chem.Mol | IdentityRefusal:
    if transform.direction not in {"protonate", "deprotonate"}:
        return IdentityRefusal(code="invalid_site", reason="direction must be protonate or deprotonate.")
    if transform.atom_index < 0 or transform.atom_index >= mol.GetNumAtoms():
        return IdentityRefusal(code="invalid_site", reason="atom index is not in the parent.")
    editable = Chem.RWMol(mol)
    atom = editable.GetAtomWithIdx(transform.atom_index)
    bonded = _bonded_hydrogen_indexes(atom)
    if transform.direction == "protonate":
        # A bonded hydrogen is invisible to GetTotalNumHs(). Setting an
        # explicit-H property on top of it would count that hydrogen twice.
        if bonded:
            hydrogen = Chem.Atom(1)
            hydrogen_index = editable.AddAtom(hydrogen)
            editable.AddBond(transform.atom_index, hydrogen_index, Chem.BondType.SINGLE)
            atom.SetFormalCharge(atom.GetFormalCharge() + 1)
            atom.SetNoImplicit(True)
        else:
            atom.SetNumExplicitHs(atom.GetTotalNumHs() + 1)
            atom.SetFormalCharge(atom.GetFormalCharge() + 1)
            atom.SetNoImplicit(True)
    elif bonded:
        # Delete one real hydrogen. An index above it moves down.
        hydrogen_index = max(bonded)
        editable.RemoveAtom(hydrogen_index)
        site_index = transform.atom_index - (1 if hydrogen_index < transform.atom_index else 0)
        site = editable.GetAtomWithIdx(site_index)
        site.SetFormalCharge(site.GetFormalCharge() - 1)
        site.SetNoImplicit(True)
    else:
        total = atom.GetTotalNumHs()
        if total < 1:
            return IdentityRefusal(code="invalid_site", reason="that atom has no hydrogen to remove.")
        atom.SetNumExplicitHs(total - 1)
        atom.SetFormalCharge(atom.GetFormalCharge() - 1)
        atom.SetNoImplicit(True)
    copy = editable.GetMol()
    try:
        Chem.SanitizeMol(copy)
        # Spectator hydrogen atoms would keep an AddHs parent from sharing
        # the implicit-H fragment key (acetate is CC(=O)[O-]).
        copy = Chem.RemoveHs(copy)
    except (ValueError, RuntimeError):
        return IdentityRefusal(code="unsanitizable", reason="the ionized structure could not be sanitized.")
    return copy


def ionize_at_sites(
    mol: Chem.Mol, transforms: Sequence[SiteTransform]
) -> str | IdentityRefusal | IonizationRefusal:
    """Apply each transform to the molecule the previous one returned.

    Atom indexes are positions on that updated molecule. Deprotonation deletes
    a bonded hydrogen when one is present, and the result then drops remaining
    explicit hydrogen atoms, so every later index has to be read from the
    updated mol. An index taken from the parent is only still valid when no
    earlier transform removed an atom below it.
    """
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


# Neutral C–H and neutral oxygen both sanitize in this RDKit pin (acetic acid
# gives ``[CH2-]C(=O)O``, ``CC(O)=[OH+]`` and ``CC(=O)[OH2+]``). Those are not
# v1 microspecies: a named atom can still be transformed, but net-charge
# enumeration only offers heteroatom acids and N/P bases, plus a proton on an
# existing anion or off an existing cation. No ranking and no tautomer pass.
_ACID_ELEMENTS = frozenset({7, 8, 15, 16})  # N, O, P, S
_BASE_ELEMENTS = frozenset({7, 15})  # N, P


def _enumeration_directions(atom: Chem.Atom) -> tuple[str, ...]:
    charge = atom.GetFormalCharge()
    number = atom.GetAtomicNum()
    directions: list[str] = []
    if number in _BASE_ELEMENTS or charge < 0:
        directions.append("protonate")
    # includeNeighbors counts a real hydrogen atom. GetTotalNumHs() alone
    # reports 0 after AddHs, so an explicit-H acid would never be offered.
    if atom.GetTotalNumHs(includeNeighbors=True) >= 1 and (number in _ACID_ELEMENTS or charge > 0):
        directions.append("deprotonate")
    return tuple(directions)


def structures_at_net_charge(mol: Chem.Mol, target_charge: int) -> tuple[str, ...]:
    """Distinct fragment_key values from one protonate or deprotonate that match target_charge.

    Order is atom index, then protonate before deprotonate. Identity refusals
    are skipped. Keys are not ranked and are not tautomer-canonicalized:
    ``choose_ionization`` decides whether one graph is unique.

    Listing tries N, O, P and S only, so a carbon deprotonation of acetic acid
    is not a competing microspecies.
    """
    keys: list[str] = []
    seen: set[str] = set()
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() <= 1:
            continue
        for direction in _enumeration_directions(atom):
            result = apply_site_transform(mol, SiteTransform(atom.GetIdx(), direction))
            if isinstance(result, IdentityRefusal):
                continue
            if fragment_formal_charge(result) != target_charge:
                continue
            key = fragment_key(result)
            if isinstance(key, IdentityRefusal) or key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return tuple(keys)


def select_by_net_charge(
    mol: Chem.Mol, target_charge: int
) -> str | IonizationRefusal | IdentityRefusal:
    return choose_ionization(structures_at_net_charge(mol, target_charge))
