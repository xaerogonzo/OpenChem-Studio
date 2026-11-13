"""An idealised 3D STARTING geometry for hypervalent molecules, from VSEPR shape and measured bond data.

WHY THIS EXISTS. Distance geometry plus a force field knows nothing of lone pairs. Measured with the
repository's RDKit (2025.09.6, Phase 0 of the hypervalent plan): XeF2 came out bent at 112 degrees, XeF4,
SF4 and SF6 with angles as small as 42 degrees, IF3 trigonal planar, and ClF3, BrF3 and ClF5 cannot be
embedded at all (RDKit allows chlorine and bromine one bond). So for the molecules in `REFERENCES` the
coordinates are built here instead, and for everything else the caller is told it is NOT covered.

WHAT IT IS NOT. It is a starting geometry, never an optimised one: the angles and lengths are the
published gas-phase (or, where stated, crystal) values for ONE molecule each, placed on the VSEPR
template for its shape. It has no energy, it is not a force-field minimum and it is not a quantum
minimum; ORCA is what refines it. Nothing here estimates a bond length from radii: a molecule with no
entry in `REFERENCES` gets a stated refusal, not a guess.

THE SHAPE COMES FROM THE GRAPH. For one centre with `n` terminal, singly bonded ligands and no formal
charge, the lone pairs are `(outer electrons - n) / 2`, and `(n, lone pairs)` names the shape (ClF3:
7 electrons, 3 bonds, 2 lone pairs, T-shaped). Lone pairs are never atoms and never occupy a ligand slot.

THREE OUTCOMES, kept apart because they need different handling (`VseprOutcome.kind`):

* `BUILT`        a supported molecule; `geometry` holds the coordinates.
* `UNSUPPORTED`  a hypervalent centre of the kind this module is about (one centre, terminal single
                 bonds, neutral, a valence the hypervalent table lists) but with no reference entry, or an
                 electron count the templates do not cover. The caller must NOT fall back to embedding:
                 that is the path known to give a wrong shape. `reason` says which.
* `NOT_APPLICABLE` anything else (a carbon, sulfate with its double bonds, a ring, a charged ion, a
                 normal valence): the ordinary conformer path is correct for it and is left alone.

The reference values are literature figures recorded with their source. The first seven rows (ClF3, BrF3, XeF2,
XeF4, SF4, SF6, PF5) were read from NIST's CCCBDB experimental-geometry table (2026-11-13) [source:nist_cccbdb_geometries], a compilation whose
original papers are not held; the last four (BrF5, IF5, ClF5, IF7) were read from the papers themselves, held in
the maintainer's library, and say what each paper does and does not determine. The angles are as measured: ClF3
87.45 degrees (so its trans pair is 174.9), BrF3 86.21, SF4 173.07 and 101.55. The held copy of Kuchitsu 1998 is
only an index of citations, so SF6's value could not be read off the held book. Lengths are `re`, `r0`, `ra` or
`rg` as the source gives them: they differ by a few thousandths of an Angstrom, far below what a starting
geometry needs, and ORCA refines them. ClF5 is the one row whose two lengths are an ASSUMPTION (see its method).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

#: Outer-shell electrons of the centres covered (group number), for the lone-pair count.
_OUTER_ELECTRONS = {"P": 5, "S": 6, "Cl": 7, "Br": 7, "I": 7, "Xe": 8}


class Kind(str, Enum):
    BUILT = "built"
    UNSUPPORTED = "unsupported"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class Reference:
    """Measured geometry of ONE molecule, in the roles of its template (`axial`/`equatorial`)."""

    centre: str
    ligand: str
    n_ligands: int
    #: Bond length of the axial / equatorial class, Angstrom. Equal when the shape has one class.
    axial: float
    equatorial: float
    #: Named angles, degrees; the template says which it reads (see `_PLACERS`). Absent means the ideal.
    angles: dict[str, float] = field(default_factory=dict)
    source: str = ""
    #: What the numbers were measured by ("gas-phase microwave", ...), so none is read as more than it is.
    method: str = ""
    #: True when the figures were compared with a published table (see the module docstring).
    checked: bool = False

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.centre, self.ligand, self.n_ligands)


# Axial and equatorial are the two classes of a T-shape, seesaw or trigonal bipyramid; a one-class shape
# (linear, square planar, octahedral) has `axial == equatorial`.
#: The measured geometries, one row per molecule (see `Reference`); `REFERENCES` is the lookup built from them.
_ENTRIES = (
    # Every row was read from NIST's CCCBDB experimental-geometry table on 2026-11-13 (the original paper in
    # each case is the "source"). CCCBDB's "axial" and "on axis" wording is not consistent across molecules,
    # so the classes here are the VSEPR ones: `axial` is the longer, trans pair (the T's bar, the seesaw's
    # near-linear pair, the bipyramid's apexes).
    Reference(
        "Cl",
        "F",
        3,
        1.697,
        1.597,
        {"ax-eq": 87.45},
        "Muller 2001, PCCP 3, 1570",
        "microwave, re structure",
        True,
    ),
    Reference(
        "Br",
        "F",
        3,
        1.810,
        1.721,
        {"ax-eq": 86.21},
        "Magnuson 1957, J Chem Phys 27, 223",
        "microwave",
        True,
    ),
    Reference(
        "Xe",
        "F",
        2,
        1.974,
        1.974,
        {},
        "Burger and Ma 1993, J Mol Spec 157, 536",
        "re",
        True,
    ),
    Reference(
        "Xe",
        "F",
        4,
        1.935,
        1.935,
        {},
        "Burger, Ma, Breidung and Thiel 1996, J Chem Phys 104, 4945",
        "r0",
        True,
    ),
    Reference(
        "S",
        "F",
        4,
        1.646,
        1.545,
        {"ax-ax": 173.07, "eq-eq": 101.55},
        "Tolles and Gwinn 1962, J Chem Phys 36, 1119",
        "microwave",
        True,
    ),
    Reference(
        "S",
        "F",
        6,
        1.561,
        1.561,
        {},
        "Kuchitsu 1998, Structure of Free Polyatomic Molecules",
        "gas phase",
        True,
    ),
    Reference(
        "P",
        "F",
        5,
        1.577,
        1.534,
        {},
        "Gurvich, Veyts and Alcock 1989 (compilation, as listed by NIST CCCBDB)",
        "compiled",
        True,
    ),
    # The four rows below were read from the PAPERS (held copies, 2026-11-13), not from a compilation. For the
    # square pyramids `axial` is the apical bond and `equatorial` the basal ones; `ax-eq` is F(apical)-X-F(basal).
    Reference(
        "Br",
        "F",
        5,
        1.689,
        1.774,
        {"ax-eq": 84.8},
        "Robiette, Bradley and Brier 1971, J Chem Soc D (23), 1567 [source:robiette1971]",
        "gas electron diffraction with microwave rotational constants (apical 0.008, basal 0.003, angle 0.1 esd)",
        True,
    ),
    Reference(
        "I",
        "F",
        5,
        1.844,
        1.869,
        {"ax-eq": 81.9},
        "Robiette, Bradley and Brier 1971, J Chem Soc D (23), 1567 [source:robiette1971]",
        "gas electron diffraction with microwave rotational constants (apical 0.025, basal 0.005, angle 0.1 esd; "
        "the apical-basal difference is poorly determined)",
        True,
    ),
    Reference(
        "Cl",
        "F",
        5,
        1.65,
        1.65,
        {"ax-eq": 86.5},
        "Bodenseh, Huttner and Nowicki 1976, Z Naturforsch 31a, 1638 [source:bodenseh1976]",
        "microwave, two rotational constants: only the angle (86.5, esd 1.0) is determined; the paper states that a "
        "complete structure is not possible and that both lengths are about 1.65 A, so one value is used for both",
        True,
    ),
    Reference(
        "I",
        "F",
        7,
        1.786,
        1.858,
        {},
        "Adams, Thompson and Bartell 1970, J Chem Phys 53, 4040 [source:adams1970]",
        "gas electron diffraction, D5h average (axial 0.007, equatorial 0.004 esd); the molecule is puckered by "
        "7.5 degrees and axially bent by 4.5 degrees on average, which the ideal pentagonal bipyramid here omits",
        True,
    ),
)
# `key` is derived from the entry, so the table cannot disagree with the lookup.
#: `(centre, ligand, number of ligands)` -> its measured geometry. A molecule not here is refused, never estimated.
REFERENCES: dict[tuple[str, str, int], Reference] = {r.key: r for r in _ENTRIES}


@dataclass(frozen=True)
class VseprGeometry:
    """The built coordinates and how they were made."""

    #: One (x, y, z) per atom, in the molecule's own atom order, Angstrom. The centre is at the origin.
    coordinates: tuple[tuple[float, float, float], ...]
    centre_index: int
    ligand_indices: tuple[int, ...]
    #: `"AX3E2"` style: bonds and lone pairs on the centre.
    classification: str
    shape: str
    #: Which ligands were placed in which class: indices in slot order.
    axial_indices: tuple[int, ...]
    equatorial_indices: tuple[int, ...]
    reference: Reference
    diagnostics: dict[str, float] = field(default_factory=dict)
    #: Always the same statement, so no consumer can mistake this for an optimised structure.
    provenance: str = "idealised VSEPR template with published bond lengths and angles; not optimised, no energy"


@dataclass(frozen=True)
class VseprOutcome:
    kind: Kind
    reason: str = ""
    geometry: VseprGeometry | None = None


#: A fixed rotation applied to every built geometry. The templates sit on the axes (a linear molecule along z, a
#: planar one in a coordinate plane), and the 3D viewer looks down z: ClF3 then drew as a line and XeF2 as a dot,
#: found in the real window. Tilting about x then y changes no length or angle and makes no template edge-on.
_VIEW_TILT = (
    np.array([[math.cos(math.radians(35)), 0.0, math.sin(math.radians(35))], [0.0, 1.0, 0.0],
              [-math.sin(math.radians(35)), 0.0, math.cos(math.radians(35))]])
    @ np.array([[1.0, 0.0, 0.0], [0.0, math.cos(math.radians(25)), -math.sin(math.radians(25))],
                [0.0, math.sin(math.radians(25)), math.cos(math.radians(25))]])
)


# --- the templates ---------------------------------------------------------------------------------------
#
# Each placer returns (axial vectors, equatorial vectors) as unit vectors for the given reference. The
# centre is the origin; the lone pairs are simply absent. Slot order is the order ligands are assigned.


def _t_shape(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    # Equatorial ligand on +x; the axial pair tilts TOWARD it by (90 - ax-eq) because the two lone pairs
    # in the equatorial plane push it that way, so ax-eq < 90 (ClF3 87.5).
    a = math.radians(ref.angles.get("ax-eq", 90.0))
    return (
        [
            np.array([math.cos(a), 0.0, math.sin(a)]),
            np.array([math.cos(a), 0.0, -math.sin(a)]),
        ],
        [np.array([1.0, 0.0, 0.0])],
    )


def _linear(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    return [np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, -1.0])], []


def _square_planar(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    v = [np.array(p, float) for p in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0))]
    return v, []


def _seesaw(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    # Lone pair on -x in the equatorial plane. The axial pair is bent toward +x (away from it), so that
    # ax-ax = 180 - 2t; the two equatorial ligands subtend eq-eq about +x.
    ax = math.radians(ref.angles.get("ax-ax", 180.0))
    eq = math.radians(ref.angles.get("eq-eq", 120.0))
    t = (math.pi - ax) / 2
    return (
        [
            np.array([math.sin(t), 0.0, math.cos(t)]),
            np.array([math.sin(t), 0.0, -math.cos(t)]),
        ],
        [
            np.array([math.cos(eq / 2), math.sin(eq / 2), 0.0]),
            np.array([math.cos(eq / 2), -math.sin(eq / 2), 0.0]),
        ],
    )


def _trigonal_bipyramid(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    eq = [
        np.array([math.cos(math.radians(a)), math.sin(math.radians(a)), 0.0])
        for a in (0, 120, 240)
    ]
    return [np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, -1.0])], eq


def _octahedron(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    v = [
        np.array(p, float)
        for p in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
    ]
    return v, []


def _square_pyramid(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    # Apical ligand on +z; the four basal ligands at `ax-eq` from it, 90 degrees apart about z. The lone pair sits
    # opposite the apex and pushes the basal bonds TOWARD it, so ax-eq < 90 (BrF5 84.8, IF5 81.9, ClF5 86.5).
    t = math.radians(ref.angles.get("ax-eq", 90.0))
    basal = [
        np.array([math.sin(t) * math.cos(math.radians(p)), math.sin(t) * math.sin(math.radians(p)), math.cos(t)])
        for p in (0, 90, 180, 270)
    ]
    return [np.array([0.0, 0.0, 1.0])], basal


def _pentagonal_bipyramid(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    # The IDEAL D5h shape (72 and 90 degrees); the measured puckering and axial bend are averages, not a structure.
    equatorial = [
        np.array([math.cos(math.radians(p)), math.sin(math.radians(p)), 0.0]) for p in (0, 72, 144, 216, 288)
    ]
    return [np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, -1.0])], equatorial


#: (bonds, lone pairs) -> (classification, shape, placer). XeF6 (a distorted mean structure, not one shape) and
#: every shape with more than seven bonds are not here.
_TEMPLATES = {
    (2, 3): ("AX2E3", "linear", _linear),
    (3, 2): ("AX3E2", "T-shaped", _t_shape),
    (4, 2): ("AX4E2", "square planar", _square_planar),
    (4, 1): ("AX4E", "seesaw", _seesaw),
    (5, 0): ("AX5", "trigonal bipyramidal", _trigonal_bipyramid),
    (5, 1): ("AX5E", "square pyramidal", _square_pyramid),
    (6, 0): ("AX6", "octahedral", _octahedron),
    (7, 0): ("AX7", "pentagonal bipyramidal", _pentagonal_bipyramid),
}


# --- applicability ------------------------------------------------------------------------------------


def _hypervalent_centre(mol: Any) -> tuple[int, list[int]] | None:
    """The one centre and its ligands, when `mol` has the shape this module is about; else None.

    One connected fragment; every other atom terminal and singly bonded to the centre; no formal charge
    anywhere; the centre's element in the hypervalent table with `n` bonds a permitted valence other than
    its preferred one. Anything else belongs to the ordinary conformer path.
    """
    from openchem.chem.checkers.valence import hypervalent_rules

    n_atoms = mol.GetNumAtoms()
    if n_atoms < 3 or len(_fragments(mol)) != 1:
        return None
    if any(a.GetFormalCharge() for a in mol.GetAtoms()):
        return None
    centre = max(mol.GetAtoms(), key=lambda a: a.GetDegree())
    if centre.GetDegree() != n_atoms - 1:
        return None
    ligands = [a.GetIdx() for a in mol.GetAtoms() if a.GetIdx() != centre.GetIdx()]
    for index in ligands:
        atom = mol.GetAtomWithIdx(index)
        bond = mol.GetBondBetweenAtoms(index, centre.GetIdx())
        if atom.GetDegree() != 1 or bond is None or bond.GetBondTypeAsDouble() != 1.0:
            return None
    rule = hypervalent_rules().get(centre.GetSymbol())
    n = centre.GetDegree()
    if (
        not rule
        or n not in rule["permitted_valences"]
        or n == rule["preferred_valence"]
    ):
        return None
    return centre.GetIdx(), ligands


def _fragments(mol: Any) -> list[Any]:
    from rdkit import Chem

    return list(Chem.GetMolFrags(mol))


def build_vsepr_geometry(mol: Any) -> VseprOutcome:
    """Coordinates for `mol` if it is a supported hypervalent molecule; see the module docstring for the outcomes.

    `mol` is the Mol of `ChemistryEngine.hypervalent_mol_from_molblock` (or any Mol; it is only read: atoms,
    bonds, charges). The input is never modified.
    """
    found = _hypervalent_centre(mol)
    if found is None:
        return VseprOutcome(
            Kind.NOT_APPLICABLE,
            "not a single hypervalent centre with terminal single bonds",
        )
    centre_index, ligand_indices = found
    centre = mol.GetAtomWithIdx(centre_index)
    symbol, n = centre.GetSymbol(), len(ligand_indices)
    outer = _OUTER_ELECTRONS.get(symbol)
    if outer is None:
        return VseprOutcome(
            Kind.UNSUPPORTED,
            f"no electron count is recorded for the centre element {symbol}",
        )
    lone_pairs, remainder = divmod(outer - n, 2)
    if remainder or lone_pairs < 0 or (n, lone_pairs) not in _TEMPLATES:
        return VseprOutcome(
            Kind.UNSUPPORTED,
            f"{symbol} with {n} bonds and {outer - n} left-over electrons has no template here",
        )
    classification, shape, placer = _TEMPLATES[(n, lone_pairs)]
    ligand_symbols = {mol.GetAtomWithIdx(i).GetSymbol() for i in ligand_indices}
    if len(ligand_symbols) != 1:
        return VseprOutcome(
            Kind.UNSUPPORTED,
            f"mixed ligands ({'/'.join(sorted(ligand_symbols))}) have no measured geometry here",
        )
    ligand = ligand_symbols.pop()
    reference = REFERENCES.get((symbol, ligand, n))
    if reference is None:
        return VseprOutcome(
            Kind.UNSUPPORTED,
            f"no measured geometry is recorded for {symbol}{ligand}{n}",
        )

    axial_vectors, equatorial_vectors = (
        [_VIEW_TILT @ v for v in group] for group in placer(reference)
    )
    slots = [(v, reference.axial) for v in axial_vectors] + [
        (v, reference.equatorial) for v in equatorial_vectors
    ]
    assert len(slots) == n, (classification, len(slots), n)
    coordinates: list[tuple[float, float, float]] = [
        (0.0, 0.0, 0.0)
    ] * mol.GetNumAtoms()
    for index, (vector, length) in zip(
        ligand_indices, slots
    ):  # ligands in atom order: deterministic
        point = vector / np.linalg.norm(vector) * length
        coordinates[index] = (float(point[0]), float(point[1]), float(point[2]))
    geometry = VseprGeometry(
        coordinates=tuple(coordinates),
        centre_index=centre_index,
        ligand_indices=tuple(ligand_indices),
        classification=classification,
        shape=shape,
        axial_indices=tuple(ligand_indices[: len(axial_vectors)]),
        equatorial_indices=tuple(ligand_indices[len(axial_vectors) :]),
        reference=reference,
    )
    problems = validate(geometry)
    if problems:
        return VseprOutcome(
            Kind.UNSUPPORTED,
            "the built geometry failed its own checks: " + "; ".join(problems),
        )
    return VseprOutcome(
        Kind.BUILT,
        geometry=VseprGeometry(
            **{**geometry.__dict__, "diagnostics": _diagnostics(geometry)}
        ),
    )


# --- checks ---------------------------------------------------------------------------------------------


def _diagnostics(geometry: VseprGeometry) -> dict[str, float]:
    points = np.array(geometry.coordinates)
    ligands = [points[i] for i in geometry.ligand_indices]
    angles = [
        math.degrees(
            math.acos(
                np.clip(
                    np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)), -1.0, 1.0
                )
            )
        )
        for i, a in enumerate(ligands)
        for b in ligands[i + 1 :]
    ]
    gaps = [
        np.linalg.norm(a - b) for i, a in enumerate(ligands) for b in ligands[i + 1 :]
    ]
    return {
        "smallest_angle": min(angles),
        "largest_angle": max(angles),
        "closest_ligands": float(min(gaps)),
    }


def validate(geometry: VseprGeometry) -> list[str]:
    """What is wrong with `geometry`, as sentences; empty when it is sound.

    Finite coordinates, the centre at the origin, each centre-ligand distance equal to its reference
    class, ligands not on top of each other, and not all in one point: the checks an angle assertion
    alone would miss.
    """
    problems: list[str] = []
    points = np.array(geometry.coordinates, dtype=float)
    if not np.all(np.isfinite(points)):
        return ["a coordinate is not finite"]
    if np.linalg.norm(points[geometry.centre_index]) > 1e-9:
        problems.append("the centre is not at the origin")
    expected = {i: geometry.reference.axial for i in geometry.axial_indices}
    expected.update(
        {i: geometry.reference.equatorial for i in geometry.equatorial_indices}
    )
    for index, length in expected.items():
        actual = float(np.linalg.norm(points[index]))
        if abs(actual - length) > 1e-6:
            problems.append(
                f"atom {index} is {actual:.4f} A from the centre, not {length:.4f}"
            )
    ligands = [points[i] for i in geometry.ligand_indices]
    for i, a in enumerate(ligands):
        for b in ligands[i + 1 :]:
            if np.linalg.norm(a - b) < 1.5:
                problems.append("two ligands are closer than 1.5 A")
    return problems
