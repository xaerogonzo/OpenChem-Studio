"""The arithmetic of the bond-dissociation benchmark (`docs/BDE_DESIGN.md`): DH298(R-H) from the thermochemistry of three species, the hydrogen atom's enthalpy, and how a radical's start is made from its parent.

Pure functions with no engine and no file read, tested in `tests/test_bde_benchmark.py`.

THE HYDROGEN ATOM IS COMPUTED, NOT TABULATED: its enthalpy at 298.15 K is its electronic energy at the same method and basis plus (5/2) kT (three translational degrees of freedom and the pV term), the same translation-only term the proton has in `benchmarks/proton_affinity/pa_core.py`.
THE QUANTITY IS AN ENTHALPY: `DH298 = H(R.) + H(H.) - H(RH)`, each H a total enthalpy of ORCA's output (298.15 K, 1 atm; electronic energy, ZPE, thermal terms and kT). Never an electronic-energy difference and never D0 (they differ by about 1.5 kcal/mol for an R-H bond; Blanksby and Ellison).
No symmetry number enters, because an enthalpy has none.
"""
from __future__ import annotations

import numpy as np

K_B = 1.380649e-23  # J/K
N_A = 6.02214076e23
HARTREE_J = 4.3597447222071e-18
#: The temperature of the benchmark and of every reference value in it.
T_STANDARD = 298.15
HARTREE_TO_KCAL = HARTREE_J * N_A / 4184.0
#: <S**2> of a clean doublet; a radical whose value exceeds it by more than the next constant is reported as spin-contaminated (a flag in the report, in no rule).
S2_DOUBLET = 0.75
#: How far above 0.75 an unrestricted doublet's <S**2> may be before the report flags it.
S2_FLAG_EXCESS = 0.05


def hydrogen_atom_enthalpy(electronic_energy: float, temperature: float = T_STANDARD) -> float:
    """H(H.) in Hartree: the atom's electronic energy plus (5/2) kT (translation and pV; an atom has no rotation or vibration)."""
    return electronic_energy + 2.5 * K_B * temperature / HARTREE_J


def bond_dissociation_enthalpy(h_parent: float, h_radical: float, h_hydrogen: float) -> float:
    """DH298(R-H) = H(R.) + H(H.) - H(RH), in Hartree, from the three total enthalpies."""
    return h_radical + h_hydrogen - h_parent


def spin_contaminated(s2: float) -> bool:
    """Whether an unrestricted doublet's <S**2> is more than `S2_FLAG_EXCESS` above the clean 0.75 (reported, never a rule)."""
    return s2 - S2_DOUBLET > S2_FLAG_EXCESS


def radical_start(symbols: list[str], coordinates: np.ndarray, heavy_atom: int, neighbors: list[int]) -> tuple[list[str], np.ndarray]:
    """A radical's starting geometry: the parent's atoms with ONE hydrogen of `heavy_atom` deleted (the lowest-numbered hydrogen among `neighbors`, the atom's bonded atoms).

    Every remaining atom keeps its place, so the optimizer starts from the parent's conformer and not from a fresh embedding of a radical. Raises ValueError if the atom carries no hydrogen."""
    hydrogens = [i for i in neighbors if symbols[i] == "H"]
    if not hydrogens:
        raise ValueError(f"atom {heavy_atom} carries no hydrogen")
    drop = min(hydrogens)
    keep = [i for i in range(len(symbols)) if i != drop]
    return [symbols[i] for i in keep], np.asarray(coordinates, dtype=float)[keep]
