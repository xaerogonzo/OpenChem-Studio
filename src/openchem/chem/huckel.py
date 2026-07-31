"""Hückel molecular orbital analysis of a pi system.

Simple Hückel theory: build the adjacency matrix of the conjugated pi
system and diagonalize it. Orbital energies come out as E = alpha + x*beta,
so the eigenvalues ARE the x coefficients and everything is reported in
units of beta (beta is negative, so a larger x means a lower-energy, more
stable orbital).

Verified live against the closed-form answers before any of this was
written:

    benzene    orbital energies exactly [2, 1, 1, -1, -1, -2] beta
               pi electron density exactly 1.000 on every carbon
               total pi energy exactly 8.0 beta (textbook 6a + 8b)
               HOMO-LUMO gap exactly 2.0 beta
    butadiene  orbital energies exactly [1.618, 0.618, -0.618, -1.618]

One `numpy.linalg.eigh` gives eigenvalues AND eigenvectors, so orbitals,
densities, HOMO/LUMO and localization energies all fall out of the same
call -- switching from `eigvalsh` to `eigh` is the entire extra cost.

Field names are generic (orbital energies, coefficients, occupations)
rather than `huckel_*`, so Extended Hückel, PPP, CNDO or INDO could reuse
the shape. Deliberately NOT introducing a `HamiltonianResult` base class:
that is a hierarchy with exactly one implementation, which this project
has declined three times before.

WHAT THIS IS NOT: simple Hückel treats all pi centres as identical carbons
and all pi bonds as identical. Heteroatoms genuinely need adjusted alpha
and beta parameters, which this does not apply -- so a pyridine is
computed as if it were benzene. That is stated in the result rather than
left for someone to discover from a wrong nitrogen density.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from rdkit import Chem

from openchem.domain.common import CacheState, Provenance
from openchem.domain.scientific_result import AlertResult, PerAtomDataset

# Two electrons per filled orbital.
_ELECTRONS_PER_ORBITAL = 2


@dataclass(frozen=True)
class HuckelResult:
    """Generic molecular-orbital output, named so a different Hamiltonian
    could produce the same shape."""

    atom_indices: list[int]  # pi-system atoms, in matrix order
    orbital_energies: list[float]  # x in E = alpha + x*beta, descending
    orbital_coefficients: list[list[float]]  # per orbital, per atom
    occupations: list[int]
    electron_density: dict[int, float]  # molecule atom index -> pi density
    total_pi_energy: float  # in beta
    homo: float | None
    lumo: float | None

    @property
    def homo_lumo_gap(self) -> float | None:
        if self.homo is None or self.lumo is None:
            return None
        return self.homo - self.lumo


def pi_system_atoms(mol: Chem.Mol) -> list[int]:
    """Atoms contributing a p orbital to a conjugated system: aromatic
    atoms, plus any atom in a double or triple bond."""
    indices: set[int] = set()
    for atom in mol.GetAtoms():
        if atom.GetIsAromatic():
            indices.add(atom.GetIdx())
    for bond in mol.GetBonds():
        if bond.GetBondType() in (Chem.BondType.DOUBLE, Chem.BondType.TRIPLE, Chem.BondType.AROMATIC):
            indices.add(bond.GetBeginAtomIdx())
            indices.add(bond.GetEndAtomIdx())
    return sorted(indices)


def solve_huckel(mol: Chem.Mol, pi_electrons: int | None = None) -> HuckelResult | None:
    """Diagonalize the pi-system adjacency matrix.

    `pi_electrons` defaults to one per pi centre, which is right for a
    neutral hydrocarbon pi system (benzene: 6 atoms, 6 electrons).
    """
    indices = pi_system_atoms(mol)
    if len(indices) < 2:
        return None
    position = {atom_index: slot for slot, atom_index in enumerate(indices)}

    size = len(indices)
    hamiltonian = np.zeros((size, size))
    for bond in mol.GetBonds():
        begin, end = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if begin in position and end in position:
            # Off-diagonal = beta for bonded pi centres, 0 otherwise; the
            # diagonal (alpha) is taken as the zero of energy.
            hamiltonian[position[begin]][position[end]] = 1.0
            hamiltonian[position[end]][position[begin]] = 1.0

    eigenvalues, eigenvectors = np.linalg.eigh(hamiltonian)
    order = np.argsort(eigenvalues)[::-1]  # most stable (largest x) first
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]

    electrons = size if pi_electrons is None else pi_electrons
    occupations: list[int] = []
    remaining = electrons
    for _ in range(size):
        filled = min(_ELECTRONS_PER_ORBITAL, max(remaining, 0))
        occupations.append(filled)
        remaining -= filled

    density = {
        indices[atom_slot]: float(
            sum(
                occupation * eigenvectors[atom_slot, orbital] ** 2
                for orbital, occupation in enumerate(occupations)
            )
        )
        for atom_slot in range(size)
    }
    total_energy = float(
        sum(occupation * eigenvalues[orbital] for orbital, occupation in enumerate(occupations))
    )

    occupied = [i for i, occupation in enumerate(occupations) if occupation > 0]
    empty = [i for i, occupation in enumerate(occupations) if occupation == 0]
    homo = float(eigenvalues[occupied[-1]]) if occupied else None
    lumo = float(eigenvalues[empty[0]]) if empty else None

    return HuckelResult(
        atom_indices=indices,
        orbital_energies=[float(value) for value in eigenvalues],
        orbital_coefficients=[[float(v) for v in eigenvectors[:, i]] for i in range(size)],
        occupations=occupations,
        electron_density=density,
        total_pi_energy=total_energy,
        homo=homo,
        lumo=lumo,
    )


def _heteroatoms_present(mol: Chem.Mol, indices: list[int]) -> bool:
    return any(mol.GetAtomWithIdx(index).GetSymbol() != "C" for index in indices)


_NO_PI_SYSTEM = (
    "This molecule has no conjugated pi system (needs at least two atoms in "
    "double, triple or aromatic bonds)."
)

_HETEROATOM_CAVEAT = (
    "Note: simple Huckel treats every pi centre as an identical carbon. This molecule "
    "contains heteroatoms, whose real alpha/beta parameters differ -- densities on those "
    "atoms are indicative only."
)


def compute_huckel_analysis(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> AlertResult:
    """The "quantum" category's Huckel calculator."""
    result = solve_huckel(mol)
    if result is None:
        return AlertResult(
            alert_id="huckel_analysis",
            name="Huckel Analysis",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="quantum",
            cache_state=CacheState.FAILED,
            error=_NO_PI_SYSTEM,
            provenance=Provenance(created_by="core", method="huckel"),
        )

    lines = [
        f"Pi system: {len(result.atom_indices)} atoms",
        f"Total pi energy: {result.total_pi_energy:.4f} beta",
    ]
    if result.homo is not None:
        lines.append(f"HOMO: {result.homo:+.4f} beta")
    if result.lumo is not None:
        lines.append(f"LUMO: {result.lumo:+.4f} beta")
    if result.homo_lumo_gap is not None:
        lines.append(f"HOMO-LUMO gap: {result.homo_lumo_gap:.4f} beta")
    lines.append(
        "Orbital energies (beta): "
        + ", ".join(f"{value:+.3f}" for value in result.orbital_energies)
    )
    if _heteroatoms_present(mol, result.atom_indices):
        lines.append(_HETEROATOM_CAVEAT)

    return AlertResult(
        alert_id="huckel_analysis",
        name="Huckel Analysis",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="quantum",
        provenance=Provenance(
            created_by="core",
            method="huckel",
            parameters={
                "total_pi_energy_beta": result.total_pi_energy,
                "homo_beta": result.homo,
                "lumo_beta": result.lumo,
            },
        ),
    )


def compute_pi_electron_density(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> PerAtomDataset:
    """Per-atom pi electron density, projected onto the 2D and 3D views."""
    result = solve_huckel(mol)
    if result is None:
        return PerAtomDataset(
            property_id="huckel_pi_density",
            name="Pi Electron Density (Huckel)",
            units="e",
            method="huckel",
            molecule_uuid=molecule_uuid,
            values={},
            cache_state=CacheState.FAILED,
            error=_NO_PI_SYSTEM,
            provenance=Provenance(created_by="core", method="huckel"),
        )
    return PerAtomDataset(
        property_id="huckel_pi_density",
        name="Pi Electron Density (Huckel)",
        units="e",
        method="huckel",
        molecule_uuid=molecule_uuid,
        values=result.electron_density,
        provenance=Provenance(created_by="core", method="huckel"),
    )
