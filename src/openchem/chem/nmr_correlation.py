from __future__ import annotations

from rdkit import Chem

from openchem.domain.scientific_result import CrossPeak


def compute_hsqc_pairs(mol: Chem.Mol, shifts: dict[int, float]) -> list[CrossPeak]:
    """One-bond H-C correlations -- each H atom's single directly-bonded
    carbon, when both have a shift. Trivial from the bond graph alone, no
    distance-matrix computation needed. `mol` must already have explicit
    hydrogens (`Chem.AddHs`) -- an implicit-H mol has no H atom indices to
    correlate at all.
    """
    pairs: list[CrossPeak] = []
    for atom in mol.GetAtoms():
        if atom.GetSymbol() != "H" or atom.GetIdx() not in shifts:
            continue
        for neighbor in atom.GetNeighbors():
            if neighbor.GetSymbol() == "C" and neighbor.GetIdx() in shifts:
                pairs.append(CrossPeak(atom_a=atom.GetIdx(), atom_b=neighbor.GetIdx()))
    return pairs


def _bond_distance_pairs(
    mol: Chem.Mol, shifts: dict[int, float], symbol_a: str, symbol_b: str, min_bonds: int, max_bonds: int
) -> list[CrossPeak]:
    distance_matrix = Chem.GetDistanceMatrix(mol)
    atoms_a = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == symbol_a and a.GetIdx() in shifts]
    atoms_b = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == symbol_b and a.GetIdx() in shifts]
    seen: set[tuple[int, int]] = set()
    pairs: list[CrossPeak] = []
    for i in atoms_a:
        for j in atoms_b:
            if i == j:
                continue
            key = (min(i, j), max(i, j))
            if key in seen:
                continue
            bonds = int(round(distance_matrix[i][j]))
            if min_bonds <= bonds <= max_bonds:
                pairs.append(CrossPeak(atom_a=i, atom_b=j))
                seen.add(key)
    return pairs


def compute_hmbc_pairs(mol: Chem.Mol, shifts: dict[int, float]) -> list[CrossPeak]:
    """H-C correlations 2-3 bonds apart -- the conventional HMBC window
    (excludes the 1-bond pairs HSQC already covers)."""
    return _bond_distance_pairs(mol, shifts, "H", "C", min_bonds=2, max_bonds=3)


def compute_cosy_pairs(mol: Chem.Mol, shifts: dict[int, float]) -> list[CrossPeak]:
    """H-H correlations 2 (geminal, e.g. a CH2's two protons) or 3
    (vicinal, e.g. adjacent CH-CH protons) bonds apart."""
    return _bond_distance_pairs(mol, shifts, "H", "H", min_bonds=2, max_bonds=3)
