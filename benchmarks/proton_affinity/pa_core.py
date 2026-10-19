"""The arithmetic of the proton-affinity benchmark (`PREREGISTRATION.md`): the proton's terms, PA and GB from the thermochemistry of the two species, the external rotational symmetry number, and the correction ORCA's symmetry number needs.

Pure functions with no engine and no file read, tested in `tests/test_proton_affinity_core.py`.

THE PROTON HAS NO ELECTRONS, so its only terms are translational (ideal gas, 298.15 K, 1 atm = 101325 Pa): `H(H+) = (5/2) kT`, `S(H+)` from the Sackur-Tetrode equation for a particle of the proton's mass, and `G(H+) = H - T S`.
These come out as 1.4812 kcal/mol, 26.012 cal/(mol K) and -6.274 kcal/mol; Moser, Range and York (2010) print 1.48, 26.02 and -6.28 for the same standard state.

THE SYMMETRY NUMBER IS NOT LEFT TO ORCA. ORCA 6.1.1 perceives the point group with a tolerance and gave H3O+ (which is C3v within 0.001 Angstrom) "Cs, Symmetry Number: 1" in the smoke run of the preregistration, which is a Gibbs energy 0.65 kcal/mol (RT ln 3)
too low for the ion and so a gas basicity about that much too high. The ENTHALPY is unaffected. `rotational_symmetry_number` counts the proper rotations that map the molecule onto itself, found from the graph automorphisms and checked against the geometry, and `symmetry_correction_eh` is what to add to
ORCA's Gibbs energy: G(sigma) = G(1) + RT ln(sigma), so the correction is RT ln(sigma_true / sigma_orca).
"""
from __future__ import annotations

import math

import numpy as np

#: CODATA 2018 (exact SI definitions where defined).
K_B = 1.380649e-23  # J/K
H_PLANCK = 6.62607015e-34  # J s
N_A = 6.02214076e23
HARTREE_J = 4.3597447222071e-18
M_PROTON = 1.67262192369e-27  # kg
ATM_PA = 101325.0
KCAL_J = 4184.0
#: The temperature of the benchmark and of every NIST value in it.
T_STANDARD = 298.15

HARTREE_TO_KCAL = HARTREE_J * N_A / KCAL_J  # 627.5095 kcal/mol per Eh (J/mol -> kcal/mol)
KCAL_TO_KJ = 4.184


def proton_terms(temperature: float = T_STANDARD, pressure: float = ATM_PA) -> tuple[float, float, float]:
    """(H, S, G) of the gas-phase proton: Hartree, Hartree per kelvin and Hartree, at `temperature` and `pressure` (Sackur-Tetrode, translation only)."""
    kt = K_B * temperature
    wavelength = H_PLANCK / math.sqrt(2.0 * math.pi * M_PROTON * kt)
    s_per_particle = K_B * (math.log(kt / (pressure * wavelength**3)) + 2.5)  # J/K
    h = 2.5 * kt / HARTREE_J
    s = s_per_particle / HARTREE_J
    return h, s, h - temperature * s


def proton_affinity(h_base: float, h_acid: float, temperature: float = T_STANDARD) -> float:
    """PA(B) = H(B) + H(H+) - H(BH+), in Hartree, from the total enthalpies of the base and its conjugate acid (each electronic energy plus thermal enthalpy correction)."""
    return h_base + proton_terms(temperature)[0] - h_acid


def gas_basicity(g_base: float, g_acid: float, temperature: float = T_STANDARD) -> float:
    """GB(B) = G(B) + G(H+) - G(BH+), in Hartree, from the Gibbs energies of the base and its conjugate acid."""
    return g_base + proton_terms(temperature)[2] - g_acid


def symmetry_correction_eh(sigma_true: int, sigma_orca: int, temperature: float = T_STANDARD) -> float:
    """What to ADD to ORCA's Gibbs energy (Hartree) when its symmetry number is `sigma_orca` and the molecule's is `sigma_true`: RT ln(sigma_true / sigma_orca)."""
    if sigma_true < 1 or sigma_orca < 1:
        raise ValueError("a symmetry number is at least 1")
    return K_B * temperature / HARTREE_J * math.log(sigma_true / sigma_orca)


def _best_rotation_rmsd(a: np.ndarray, b: np.ndarray) -> float:
    """The RMSD of `a` onto `b` over all atoms after the best PROPER rotation (a mirror image does not count), both centred."""
    a = a - a.mean(axis=0)
    b = b - b.mean(axis=0)
    u, _s, vt = np.linalg.svd(a.T @ b)
    d = np.sign(np.linalg.det(u @ vt))
    rotation = u @ np.diag([1.0, 1.0, d]) @ vt
    return float(np.sqrt(((a @ rotation - b) ** 2).sum() / len(a)))


def rotational_symmetry_number(mol, coordinates: np.ndarray, tolerance: float = 0.05) -> int:
    """The external rotational symmetry number: how many proper rotations (the identity included) map the molecule onto itself within `tolerance` Angstrom.

    `mol` is an RDKit molecule with explicit hydrogens whose atom order matches `coordinates` (N x 3, Angstrom). Every graph automorphism is a candidate permutation of the atoms; one is a symmetry operation if the permuted structure
    coincides with the original after a proper rotation (a reflection is not a rotation, so an automorphism that needs one is not counted). Internal rotors (a methyl group) are not counted: turning only the methyl does not map the
    whole molecule onto itself, which is why methanol is 1 and not 3.
    """
    coordinates = np.asarray(coordinates, dtype=float)
    if len(coordinates) != mol.GetNumAtoms():
        raise ValueError("the coordinates do not match the molecule's atoms")
    matches = mol.GetSubstructMatches(mol, uniquify=False, maxMatches=200000, useChirality=False)
    count = 0
    seen: set[tuple[int, ...]] = set()
    for match in matches:
        if match in seen:
            continue
        seen.add(match)
        permuted = coordinates[list(match)]
        if _best_rotation_rmsd(coordinates, permuted) <= tolerance:
            count += 1
    return max(count, 1)
