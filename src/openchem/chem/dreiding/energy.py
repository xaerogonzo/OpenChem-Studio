"""The DREIDING energy expression, term by term.

Equation numbers refer to Mayo, Olafson & Goddard 1990. The whole force
field is `E = E_valence + E_nonbonded`, and every term below is the
paper's default option rather than one of the variants it also offers --
see `parameters` for which those are and why the choice matters.

Charges and hydrogen bonds are NOT included. That is the paper's own
default for the results it reports ("charges are not included", Table VIII
footnote), and it is what the rotational barriers of Table XI were
computed with, so it is the configuration this can be validated against.
Both are named in `unsupported_terms` rather than silently absent.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import numpy as np
from rdkit import Chem

from openchem.chem.dreiding.parameters import (
    ANGLE_FORCE_CONSTANT,
    BOND_RADIUS_CORRECTION,
    OXYGEN_COLUMN,
    RESONANT_TYPES,
    SINGLE_BOND_FORCE_CONSTANT,
    SP1_TYPES,
    SP2_TYPES,
    SP3_TYPES,
    TORSION_BY_CENTRAL_ATOM,
    VALENCE,
    VAN_DER_WAALS,
    TorsionParameters,
    element_of,
)
from openchem.chem.dreiding.typer import assign_types


@dataclass(frozen=True)
class EnergyBreakdown:
    """The total and its parts, all in kcal/mol.

    Reported per term rather than as one number because the parts are how
    a wrong implementation is found: a barrier that is right in total can
    be a torsion error cancelling a van der Waals one.
    """

    bond: float
    angle: float
    torsion: float
    inversion: float
    van_der_waals: float

    @property
    def total(self) -> float:
        return self.bond + self.angle + self.torsion + self.inversion + self.van_der_waals


#: What this implementation leaves out, named rather than implied.
UNSUPPORTED_TERMS = (
    "Electrostatics: DREIDING's charges are an input, not something the "
    "force field derives, and the paper's own reported results set them "
    "to zero.",
    "Hydrogen bonds: the explicit 12-10 term of equation 38 needs the "
    "H___HB atom type, which is a modelling choice rather than something "
    "connectivity determines.",
)


def _equilibrium_length(type_i: str, type_j: str) -> float:
    """Equation 6: bond lengths are ADDITIVE over atomic radii.

    This is what makes DREIDING generic -- no per-pair table, so a bond
    between any two of the 37 types is defined without anyone having
    fitted it.
    """
    return (
        VALENCE[type_i].bond_radius
        + VALENCE[type_j].bond_radius
        - BOND_RADIUS_CORRECTION
    )


def bond_energy(positions: np.ndarray, mol: Chem.Mol, types: list[str]) -> float:
    """Equation 4a, harmonic: E = 1/2 K (R - R0)^2.

    Harmonic is the DREIDING default; the Morse form (5a) is DREIDING/M.
    A bond of order n uses n times the single-bond constant (9a).
    """
    total = 0.0
    for bond in mol.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        order = bond.GetBondTypeAsDouble()
        force = SINGLE_BOND_FORCE_CONSTANT * order
        rest = _equilibrium_length(types[i], types[j])
        length = float(np.linalg.norm(positions[i] - positions[j]))
        total += 0.5 * force * (length - rest) ** 2
    return total


def _angle_triples(mol: Chem.Mol):
    for atom in mol.GetAtoms():
        neighbours = [n.GetIdx() for n in atom.GetNeighbors()]
        for i, k in itertools.combinations(neighbours, 2):
            yield i, atom.GetIdx(), k


def angle_energy(positions: np.ndarray, mol: Chem.Mol, types: list[str]) -> float:
    """Equation 10a, the harmonic COSINE form:

        E = 1/2 C [cos(theta) - cos(theta0)]^2,   C = K / sin^2(theta0)

    The paper prefers this over the harmonic-theta form (11) because (11)
    "does not generally lead to zero slope as theta approaches 180".

    A linear centre (theta0 = 180) would divide by sin^2(180) = 0, so it
    takes the separate form of equation 10': E = K [1 + cos(theta)].
    """
    total = 0.0
    for i, j, k in _angle_triples(mol):
        rest = VALENCE[types[j]].bond_angle
        left = positions[i] - positions[j]
        right = positions[k] - positions[j]
        norms = np.linalg.norm(left) * np.linalg.norm(right)
        if norms == 0:
            continue
        cosine = float(np.clip(np.dot(left, right) / norms, -1.0, 1.0))

        if abs(rest - 180.0) < 1e-9:
            total += ANGLE_FORCE_CONSTANT * (1.0 + cosine)
            continue
        rest_cosine = math.cos(math.radians(rest))
        constant = ANGLE_FORCE_CONSTANT / math.sin(math.radians(rest)) ** 2
        total += 0.5 * constant * (cosine - rest_cosine) ** 2
    return total


def torsion_for(type_j: str, type_k: str, bond: Chem.Bond, mol: Chem.Mol) -> TorsionParameters:
    """The torsion parameters for one central bond, from equations 14-23.

    Table IV covers the case where both central atoms are the same type;
    these are the mixed rules, applied in the paper's own order. The order
    matters -- (f) is written as an exception to (e), and (g) overrides
    everything because a bond to a monovalent atom or a metal has no
    torsion at all.
    """
    # **A PAIR, NOT A SET.** `{type_j, type_k}` collapses to one element
    # when both central atoms are the same type, so every "how many of
    # these are sp3" test silently answered 1 for ethane and every rule
    # below fell through to the Table IV fallback. It reached the right
    # answer for the symmetric cases by luck and the wrong one for
    # biphenyl and for HOOH.
    pair = (type_j, type_k)

    def count_in(family) -> int:
        return sum(1 for t in pair if t in family)

    # (g) equation 20: sp1 centres, monovalent atoms, metals. A bond to
    # any of these has no torsion at all, so it overrides everything.
    if count_in(SP1_TYPES) or any(
        TORSION_BY_CENTRAL_ATOM.get(t, TorsionParameters(0.0, 0, 0.0)).periodicity == 0
        for t in pair
    ):
        return TorsionParameters(0.0, 0, 0.0)

    order = bond.GetBondTypeAsDouble()
    resonant, sp2, sp3 = count_in(RESONANT_TYPES), count_in(SP2_TYPES), count_in(SP3_TYPES)

    # (h)/(i) equations 21-22: the oxygen column, whose p-pi lone pair is
    # why HOOH and HSSH sit near 90 degrees rather than anti.
    oxygen_column = count_in(OXYGEN_COLUMN)
    if oxygen_column:
        if oxygen_column == 2:
            return TorsionParameters(2.0, 2, 90.0)
        if sp2 or resonant:
            return TorsionParameters(2.0, 2, 180.0)
        return TorsionParameters(2.0, 3, 180.0)  # with an sp3 of another column, (14)

    # (c) equation 16: a double bond between two sp2 centres.
    if order == 2.0 and sp2 == 2:
        return TorsionParameters(45.0, 2, 180.0)
    # (d) equation 17: an aromatic bond between two resonant centres.
    if bond.GetIsAromatic() and resonant == 2:
        return TorsionParameters(25.0, 2, 180.0)
    # (f) equation 19: an EXOCYCLIC single bond between two aromatic
    # centres -- biphenyl's central bond. Checked before (e), which the
    # paper writes it as an exception to.
    if not bond.IsInRing() and resonant == 2 and order == 1.0:
        return TorsionParameters(10.0, 2, 180.0)
    # (e) equation 18: a single bond between two sp2-or-resonant centres,
    # such as the middle bond of butadiene.
    if order == 1.0 and sp2 + resonant == 2:
        return TorsionParameters(5.0, 2, 180.0)
    # (b) equation 15: one sp2/resonant centre and one sp3.
    if (sp2 or resonant) and sp3:
        return TorsionParameters(1.0, 6, 0.0)
    # (a) equation 14: the plain sp3-sp3 single bond.
    if sp3 == 2:
        return TorsionParameters(2.0, 3, 180.0)

    return TORSION_BY_CENTRAL_ATOM.get(type_j, TorsionParameters(0.0, 0, 0.0))


def _dihedral(positions: np.ndarray, i: int, j: int, k: int, l: int) -> float:
    """The IJKL dihedral in degrees, by the standard cross-product route."""
    b1 = positions[j] - positions[i]
    b2 = positions[k] - positions[j]
    b3 = positions[l] - positions[k]
    n1 = np.cross(b1, b2)
    n2 = np.cross(b2, b3)
    b2_norm = np.linalg.norm(b2)
    if b2_norm == 0 or np.linalg.norm(n1) == 0 or np.linalg.norm(n2) == 0:
        return 0.0
    m = np.cross(n1, b2 / b2_norm)
    x = float(np.dot(n1, n2))
    y = float(np.dot(m, n2))
    return math.degrees(math.atan2(y, x))


def torsion_energy(positions: np.ndarray, mol: Chem.Mol, types: list[str]) -> float:
    """Equation 13, renormalised by the dihedral count.

        E = 1/2 V {1 - cos[n (phi - phi0)]}

    **V IS THE TOTAL BARRIER FOR THE CENTRAL BOND, SHARED OUT AMONG EVERY
    DIHEDRAL ACROSS IT.** The paper is explicit and gives the arithmetic:
    "for a substituted ethane V_JK = 2.0 kcal/mol and the program uses a
    barrier of V_IJKL = 2/9 for each of the nine possibilities of I and
    L". Skip that division and ethane's barrier comes out at 18 rather
    than 2, which is the single largest thing to get wrong here.
    """
    total = 0.0
    for bond in mol.GetBonds():
        j, k = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        left = [n.GetIdx() for n in mol.GetAtomWithIdx(j).GetNeighbors() if n.GetIdx() != k]
        right = [n.GetIdx() for n in mol.GetAtomWithIdx(k).GetNeighbors() if n.GetIdx() != j]
        if not left or not right:
            continue
        parameters = torsion_for(types[j], types[k], bond, mol)
        if parameters.periodicity == 0 or parameters.barrier == 0.0:
            continue

        count = len(left) * len(right)
        share = parameters.barrier / count
        for i in left:
            for l in right:
                phi = _dihedral(positions, i, j, k, l)
                angle = math.radians(parameters.periodicity * (phi - parameters.phase))
                total += 0.5 * share * (1.0 - math.cos(angle))
    return total


def inversion_energy(positions: np.ndarray, mol: Chem.Mol, types: list[str]) -> float:
    """Equation 24, the spectroscopic form, for three-coordinate centres.

    Psi is the angle between the IL bond and the JIK plane, and Psi0 is
    zero for a planar centre. Only X_2 and X_R get a term at all: Table
    III gives X_3 a force constant of zero, since a tetrahedral centre's
    angle terms already hold it.
    """
    from openchem.chem.dreiding.parameters import (
        INVERSION_FORCE_CONSTANT,
        INVERSION_PLANAR_ANGLE,
    )

    total = 0.0
    for atom in mol.GetAtoms():
        if atom.GetDegree() != 3:
            continue
        centre_type = types[atom.GetIdx()]
        if centre_type not in SP2_TYPES and centre_type not in RESONANT_TYPES:
            continue
        centre = atom.GetIdx()
        j, k, l = [n.GetIdx() for n in atom.GetNeighbors()]
        # Averaged over the three choices of which bond is "IL", so the
        # answer does not depend on neighbour ordering -- which is an
        # arbitrary artefact of the molecule file.
        for a, b, c in ((j, k, l), (k, l, j), (l, j, k)):
            normal = np.cross(positions[a] - positions[centre], positions[b] - positions[centre])
            arm = positions[c] - positions[centre]
            norms = np.linalg.norm(normal) * np.linalg.norm(arm)
            if norms == 0:
                continue
            sine = float(np.clip(np.dot(normal, arm) / norms, -1.0, 1.0))
            psi = math.degrees(math.asin(sine))
            deviation = math.radians(abs(psi) - INVERSION_PLANAR_ANGLE)
            total += 0.5 * (INVERSION_FORCE_CONSTANT / 3.0) * deviation**2
    return total


def _excluded_pairs(mol: Chem.Mol) -> set[tuple[int, int]]:
    """1-2 and 1-3 pairs, which carry no van der Waals term.

    The paper: "Interactions are not calculated between atoms bonded to
    each other (1,2 interactions) or involved in angle terms (1,3
    interactions) since these are assumed to be contained in the bond and
    angle interactions."

    **1-4 pairs are included IN FULL**, with no scale factor -- unlike
    AMBER and friends, which halve them. On ethane the 1-4 hydrogens are
    the entire difference between the 2.0 torsion barrier and the 2.896
    the paper reports.
    """
    excluded: set[tuple[int, int]] = set()
    for bond in mol.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        excluded.add((min(i, j), max(i, j)))
    for i, _j, k in _angle_triples(mol):
        excluded.add((min(i, k), max(i, k)))
    return excluded


def van_der_waals_energy(positions: np.ndarray, mol: Chem.Mol, types: list[str]) -> float:
    """Equation 31', Lennard-Jones 12-6: E = D0 [rho^-12 - 2 rho^-6].

    LJ is the DREIDING default -- "we consider the LJ as the default and
    use DREIDING/X6 to denote cases where the exponential-6 form is used".

    **The combination rules are mixed, and this is the trap the paper
    sets.** It develops a geometric mean for both parameters (36a, 36b)
    and then says: "for DREIDING we use (36a) with (36c) as defaults" --
    geometric for the well depth, ARITHMETIC for the radius. The
    geometric radius belongs to X6.
    """
    excluded = _excluded_pairs(mol)
    wells = [VAN_DER_WAALS[element_of(t)] for t in types]

    total = 0.0
    for i, j in itertools.combinations(range(mol.GetNumAtoms()), 2):
        if (i, j) in excluded:
            continue
        radius = 0.5 * (wells[i].radius + wells[j].radius)  # (36c), arithmetic
        depth = math.sqrt(wells[i].well_depth * wells[j].well_depth)  # (36a), geometric
        distance = float(np.linalg.norm(positions[i] - positions[j]))
        if distance == 0:
            continue
        rho = radius / distance
        total += depth * (rho**12 - 2.0 * rho**6)
    return total


def dreiding_energy(
    mol: Chem.Mol, conformer_id: int = -1, types: list[str] | None = None
) -> EnergyBreakdown:
    """The DREIDING energy of one conformer, broken down by term.

    Needs explicit hydrogens and a 3D conformer.
    """
    if mol.GetNumConformers() == 0:
        raise ValueError("DREIDING needs a 3D conformer")
    positions = np.array(mol.GetConformer(conformer_id).GetPositions(), dtype=float)
    types = types if types is not None else assign_types(mol)
    return EnergyBreakdown(
        bond=bond_energy(positions, mol, types),
        angle=angle_energy(positions, mol, types),
        torsion=torsion_energy(positions, mol, types),
        inversion=inversion_energy(positions, mol, types),
        van_der_waals=van_der_waals_energy(positions, mol, types),
    )
