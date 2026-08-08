"""What a periodic structure can be asked, as opposed to a molecule.

Density and coordination, and both of them refuse rather than guess.

## Coordination number is a judgement, and is reported as one

There is no measurement that says where a coordination shell ends. The
common approaches are a fixed cutoff, a ratio to the nearest distance, or
finding the largest GAP in the sorted neighbour distances -- and they
disagree on exactly the interesting cases, which are the distorted and
the intermediate ones.

So this reports the sorted neighbour distances and the gap it found, and
names the rule it used. Halite's sodium is unambiguous: six chlorides at
2.82 A and the next shell at 3.99 A, a 41% jump. A structure where the
gap is small is one where the coordination number is genuinely arguable,
and the fact says so instead of picking a side.

## Neighbours are found as explicit images, not by minimum image

Minimum image gives the shortest distance but not WHICH image it was, and
a coordination polyhedron needs its neighbours as distinct objects -- six
chlorides around a sodium are six atoms, several of them belonging to
neighbouring cells.

So the search builds surrounding cells explicitly, and how many it needs
is DERIVED from the radius and the cell's shortest perpendicular width
rather than assumed. The first version fixed one shell and refused above
half the shortest edge -- the limit belonging to minimum image, not to
this -- and refused halite outright, whose Na-Cl distance is exactly half
the cell edge. Running it is what found that.

**Perpendicular width, not edge length.** For a sheared cell the two
differ, and it is the distance between opposite faces that limits how far
one shell of images reaches.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from openchem.domain.crystal import Crystal, ExpandedAtom

#: Avogadro's number, CODATA 2018 (exact by SI definition since 2019).
AVOGADRO = 6.02214076e23

#: A^3 -> cm^3.
_ANGSTROM3_PER_CM3 = 1e-24

#: How far to look for neighbours, in angstrom, before the shell is cut
#: off. Generous: the longest first-shell contacts in ordinary minerals
#: are around 3 A, and stopping short would truncate a shell rather than
#: report it fully.
DEFAULT_SEARCH_RADIUS = 4.0

#: The jump in sorted neighbour distances that is taken to end a shell. A
#: 15% step is comfortably larger than the spread WITHIN a distorted
#: polyhedron and comfortably smaller than the step to the next shell --
#: halite's is 41%. It is a threshold somebody chose, which is why it is
#: reported alongside the answer.
SHELL_GAP_FRACTION = 0.15

#: How many shells of surrounding cells the neighbour search will build
#: before declining. Each shell is (2n+1)^3 copies, so 4 is already 729 --
#: past that the caller wants a different tool, not more patience.
_MAX_REACH = 4


class CrystalAnalysisError(ValueError):
    """The question cannot be answered for this structure."""


@dataclass(frozen=True)
class Neighbour:
    element: str
    site_label: str
    distance: float


@dataclass(frozen=True)
class CoordinationShell:
    """What surrounds one crystallographic site."""

    site_label: str
    element: str
    neighbours: tuple[Neighbour, ...]
    #: The relative jump that ended the shell, or 0.0 if nothing beyond
    #: the search radius was found to compare against.
    gap_fraction: float
    search_radius: float

    @property
    def coordination_number(self) -> int:
        return len(self.neighbours)

    @property
    def mean_distance(self) -> float:
        if not self.neighbours:
            return 0.0
        return sum(n.distance for n in self.neighbours) / len(self.neighbours)

    @property
    def is_clear_cut(self) -> bool:
        """Whether the shell boundary is obvious or arguable.

        A small gap means the "coordination number" depends on the
        threshold, and a reader deserves to know that before quoting it.
        """
        return self.gap_fraction >= 2 * SHELL_GAP_FRACTION


def atomic_masses() -> dict[str, float]:
    """Relative atomic masses, from RDKit's periodic table.

    Imported lazily and read once. The chem layer may use RDKit; this is
    the only thing it is needed for here.
    """
    from rdkit.Chem import GetPeriodicTable

    table = GetPeriodicTable()
    masses: dict[str, float] = {}
    for number in range(1, 119):
        try:
            symbol = table.GetElementSymbol(number)
            masses[symbol] = table.GetAtomicWeight(number)
        except Exception:  # noqa: BLE001 - past the end of the table
            break
    return masses


def density(crystal: Crystal) -> float:
    """Grams per cubic centimetre, from the cell contents and volume.

        rho = sum(occupancy * mass) / (N_A * V)

    **This is the check that catches a wrong cell volume**, because the
    triclinic volume formula reduces to `abc` for an orthogonal cell -- so
    a cubic test cannot tell the real formula from a bare multiplication,
    while a computed density for a non-orthogonal cell can.

    Occupancies are honoured, so a partly-vacant site lowers the density
    exactly as it does in the real material.
    """
    masses = atomic_masses()
    unknown = sorted(set(crystal.composition()) - set(masses))
    if unknown:
        raise CrystalAnalysisError(
            f"no atomic mass is tabulated for {', '.join(unknown)}, so the cell "
            "contents cannot be weighed."
        )
    total_mass = sum(
        count * masses[element] for element, count in crystal.composition().items()
    )
    volume_cm3 = crystal.lattice.volume * _ANGSTROM3_PER_CM3
    if volume_cm3 <= 0:
        raise CrystalAnalysisError("the unit cell has no volume.")
    return total_mass / (AVOGADRO * volume_cm3)


def _images(atoms: tuple[ExpandedAtom, ...], reach: int):
    """Every atom of the cell and of the surrounding shells of cells.

    Built explicitly rather than by minimum image, because minimum image
    gives the shortest distance but NOT which image it was -- and a
    coordination polyhedron needs the neighbours as distinct objects. Six
    chlorides around a sodium are six atoms, several of them in
    neighbouring cells.
    """
    offsets = range(-reach, reach + 1)
    for atom in atoms:
        for i in offsets:
            for j in offsets:
                for k in offsets:
                    yield atom, (
                        atom.position[0] + i,
                        atom.position[1] + j,
                        atom.position[2] + k,
                    )


def _shortest_perpendicular_width(crystal: Crystal) -> float:
    """The smallest distance between opposite faces of the cell.

    **Not the shortest edge.** For a sheared cell the two differ, and it
    is the perpendicular width that limits how far one shell of image
    cells reaches -- a steeply monoclinic cell can have a long `c` and a
    thin gap between its ab faces.

        d_a = V / |b x c|

    which reduces to `a` for an orthogonal cell.
    """
    lattice = crystal.lattice
    a, b, c = (
        lattice.to_cartesian(1, 0, 0),
        lattice.to_cartesian(0, 1, 0),
        lattice.to_cartesian(0, 0, 1),
    )

    def cross_norm(u, v):
        return math.sqrt(
            (u[1] * v[2] - u[2] * v[1]) ** 2
            + (u[2] * v[0] - u[0] * v[2]) ** 2
            + (u[0] * v[1] - u[1] * v[0]) ** 2
        )

    volume = lattice.volume
    areas = [cross_norm(b, c), cross_norm(a, c), cross_norm(a, b)]
    return min(volume / area for area in areas if area > 0)


def coordination_shell(
    crystal: Crystal,
    site_label: str,
    *,
    search_radius: float = DEFAULT_SEARCH_RADIUS,
    gap_fraction: float = SHELL_GAP_FRACTION,
) -> CoordinationShell:
    """The first coordination shell around one site of the asymmetric unit.

    Reported per crystallographic SITE, not per atom: halite's four
    chlorides are one site with one answer, and listing them separately
    would imply four independent measurements of the same thing.
    """
    # **How many shells of neighbouring cells to search, derived rather
    # than assumed.** The first version fixed `reach=1` and refused above
    # half the shortest edge -- the limit that belongs to the MINIMUM
    # IMAGE convention, not to explicit images. It refused halite outright,
    # whose Na-Cl distance is exactly half the cell edge, which is how the
    # mistake surfaced. Explicit images are exact to one full perpendicular
    # cell width per shell, so the honest fix is to search further rather
    # than to decline.
    width = _shortest_perpendicular_width(crystal)
    if width <= 0:
        raise CrystalAnalysisError("the unit cell is degenerate; it has no thickness.")
    reach = max(1, math.ceil(search_radius / width))
    if reach > _MAX_REACH:
        raise CrystalAnalysisError(
            f"a search radius of {search_radius:.2f} A would need {reach} shells of "
            f"neighbouring cells around a {width:.2f} A cell, which is more structure "
            "than this is meant to build. Use a shorter radius."
        )

    atoms = crystal.expand()
    centre = next((atom for atom in atoms if atom.site_label == site_label), None)
    if centre is None:
        raise CrystalAnalysisError(
            f"no site labelled {site_label!r}; this structure has "
            f"{', '.join(sorted({a.site_label for a in atoms}))}."
        )

    found: list[Neighbour] = []
    for atom, position in _images(atoms, reach=reach):
        distance = crystal.lattice.distance(centre.position, position, periodic=False)
        if 1e-6 < distance <= search_radius:
            found.append(Neighbour(atom.element, atom.site_label, distance))
    found.sort(key=lambda n: n.distance)

    if not found:
        return CoordinationShell(site_label, centre.element, (), 0.0, search_radius)

    # Cut at the first relative jump larger than the threshold.
    cut = len(found)
    biggest = 0.0
    for index in range(1, len(found)):
        step = (found[index].distance - found[index - 1].distance) / found[index - 1].distance
        if step > gap_fraction:
            cut = index
            biggest = step
            break
    return CoordinationShell(
        site_label=site_label,
        element=centre.element,
        neighbours=tuple(found[:cut]),
        gap_fraction=biggest,
        search_radius=search_radius,
    )


def conversion_determinant(crystal: Crystal) -> float:
    """The determinant of the fractional-to-Cartesian matrix.

    **It must equal the cell volume**, and that identity is an independent
    check on both: the determinant is computed from the matrix used to
    place atoms, the volume from the closed-form triclinic expression, and
    they share no code. If the matrix is wrong the atoms are in the wrong
    places, and this is what notices.
    """
    lattice = crystal.lattice
    columns = [lattice.to_cartesian(*basis) for basis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = columns
    return abs(
        ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
    )


def describe_cell(crystal: Crystal) -> str:
    """One line naming the cell, for a report or a log. ASCII only."""
    lattice = crystal.lattice
    if lattice.is_orthogonal:
        return f"a={lattice.a:.4f} b={lattice.b:.4f} c={lattice.c:.4f} A, orthogonal"
    return (
        f"a={lattice.a:.4f} b={lattice.b:.4f} c={lattice.c:.4f} A, "
        f"alpha={lattice.alpha:.3f} beta={lattice.beta:.3f} gamma={lattice.gamma:.3f} deg"
    )


def volume_per_formula_unit(crystal: Crystal) -> float | None:
    """Cell volume divided by Z, or None if Z is not recorded."""
    if not crystal.formula_units_z:
        return None
    return crystal.lattice.volume / crystal.formula_units_z


#: The twelve edges of a parallelepiped, as pairs of corners in fractional
#: coordinates. Written out rather than derived because a derivation here
#: would be three lines of index arithmetic that nobody could check by
#: eye, and this can be read against a drawing of a box.
_CELL_EDGES: tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...] = (
    ((0, 0, 0), (1, 0, 0)), ((0, 0, 0), (0, 1, 0)), ((0, 0, 0), (0, 0, 1)),
    ((1, 0, 0), (1, 1, 0)), ((1, 0, 0), (1, 0, 1)),
    ((0, 1, 0), (1, 1, 0)), ((0, 1, 0), (0, 1, 1)),
    ((0, 0, 1), (1, 0, 1)), ((0, 0, 1), (0, 1, 1)),
    ((1, 1, 0), (1, 1, 1)), ((1, 0, 1), (1, 1, 1)), ((0, 1, 1), (1, 1, 1)),
)


def scene_for(crystal: Crystal) -> dict:
    """Everything a viewer needs to draw one unit cell, as plain data.

    **The expansion happens HERE, not in the viewer.** The spike measured
    3Dmol expanding a CIF's symmetry and leaving 3 of halite's 4 chlorides
    at or outside the cell -- the right set of atoms, the wrong
    representatives, and a picture that is not the conventional cell. So
    the viewer is handed atoms that are already expanded, wrapped and
    deduplicated, and draws exactly what it is given.

    That also keeps one source of truth. The atoms in the picture are the
    same objects the density and the coordination numbers were computed
    from, so the report and the render cannot disagree.

    Returns plain lists and dicts -- no domain objects -- because this
    crosses into `ui/` and then into JavaScript.
    """
    lattice = crystal.lattice
    atoms = [
        {
            "element": atom.element,
            "x": round(x, 6),
            "y": round(y, 6),
            "z": round(z, 6),
            "site": atom.site_label,
            "occupancy": round(atom.occupancy, 4),
        }
        for atom in crystal.expand()
        for x, y, z in (lattice.to_cartesian(*atom.position),)
    ]
    edges = [
        [
            [round(value, 6) for value in lattice.to_cartesian(*start)],
            [round(value, 6) for value in lattice.to_cartesian(*end)],
        ]
        for start, end in _CELL_EDGES
    ]
    scene = {
        "atoms": atoms,
        "edges": edges,
        "name": crystal.name,
        "spaceGroup": crystal.space_group,
        # The three cell vectors, for axis labels. Kept separate from the
        # edges so a viewer can draw them differently without unpicking
        # which of the twelve lines happened to start at the origin.
        "axes": [
            {"label": label, "vector": [round(v, 6) for v in lattice.to_cartesian(*basis)]}
            for label, basis in (("a", (1, 0, 0)), ("b", (0, 1, 0)), ("c", (0, 0, 1)))
        ],
    }
    # Built here rather than by the caller so the payload is complete and
    # the viewer backend stays a pass-through that computes nothing.
    scene["xyz"] = scene_as_xyz(scene)
    return scene


def scene_as_xyz(scene: dict) -> str:
    """The scene's atoms as an XYZ block.

    XYZ rather than a molblock because a unit cell has **no bonds** -- a
    molblock would have to invent a bond table, and inventing bonds for a
    periodic solid is exactly the mistake `domain/crystal.py` exists to
    avoid. 3Dmol reads XYZ directly and draws unbonded atoms happily.

    Occupancy is not expressible in XYZ and is dropped here; it survives
    in the scene dict for anything that wants it.
    """
    atoms = scene["atoms"]
    lines = [str(len(atoms)), scene.get("name", "") or "unit cell"]
    lines.extend(
        f"{atom['element']} {atom['x']:.6f} {atom['y']:.6f} {atom['z']:.6f}"
        for atom in atoms
    )
    return "\n".join(lines)
