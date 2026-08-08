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
    #: Cartesian position, in Angstroms, of the periodic IMAGE that is
    #: actually this close -- not of the atom in the asymmetric unit.
    #:
    #: Carried because a distance alone cannot answer "what shape is this
    #: site": `chem/substance.classify_coordination_geometry` needs
    #: directions. It was omitted originally and that omission is what
    #: stopped the crystal path reporting a geometry at all, while
    #: `coordination_shell` had the positions in hand the whole time and
    #: threw them away.
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)


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
    #: Cartesian position of the central atom, so the neighbour positions
    #: above mean something on their own.
    centre: tuple[float, float, float] = (0.0, 0.0, 0.0)

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

    def geometry(self):
        """The coordination polyhedron, from the neighbour directions.

        Deliberately the SAME classifier the molecular path uses --
        `chem/substance.classify_coordination_geometry` takes bare
        coordinates precisely so a crystallographic site and a metal
        complex get one answer computed one way. Reusing rather than
        paralleling is this project's most repeatable mistake to avoid.
        """
        from openchem.chem.substance import classify_coordination_geometry

        return classify_coordination_geometry(
            self.centre, [n.position for n in self.neighbours]
        )


@dataclass(frozen=True)
class SiteEnvironment:
    """What one crystallographic site is surrounded by.

    Built for the question a click asks -- "what is this atom?" -- and so
    it carries the shell, the polyhedron and a one-line summary together
    rather than making three calls line up at the call site.
    """

    site_label: str
    element: str
    shell: CoordinationShell
    geometry: object  # substance.CoordinationGeometry; imported lazily

    @property
    def composition(self) -> str:
        """The neighbour elements, e.g. "3 H" or "2 F, 2 O".

        **Named, never just counted.** The shell is cut at the largest
        relative gap, and in a structure with hydrogens that gap usually
        falls between the H shell and the heavy-atom shell -- so a methyl
        carbon's shell is its three hydrogens and nothing else. Measured
        on COD 1511792's C1: three H at 0.986-0.996 A, with the C-C bond
        at 1.47 A beyond a 47.6% jump. Seeing "3 H" makes the resulting
        "irregular, closest to trigonal planar" read correctly instead of
        looking like a broken classifier.
        """
        tally: dict[str, int] = {}
        for neighbour in self.shell.neighbours:
            tally[neighbour.element] = tally.get(neighbour.element, 0) + 1
        return ", ".join(f"{count} {element}" for element, count in sorted(tally.items()))

    @property
    def summary(self) -> str:
        """One ASCII line, for a status bar. See `Component.label` in
        `chem/substance.py` for why this side of the split is ASCII."""
        if not self.shell.neighbours:
            return (
                f"{self.site_label} ({self.element}): nothing within "
                f"{self.shell.search_radius:.1f} A"
            )
        nearest = self.shell.neighbours[0]
        shape = self.geometry.name or "no polyhedron at this count"
        arguable = "" if self.shell.is_clear_cut else ", shell boundary arguable"
        return (
            f"{self.site_label} ({self.element}): {self.shell.coordination_number} "
            f"neighbours ({self.composition}), {shape}, nearest "
            f"{self.element}-{nearest.element} {nearest.distance:.3f} A{arguable}"
        )


def describe_site(
    crystal: Crystal,
    site_label: str,
    *,
    search_radius: float = DEFAULT_SEARCH_RADIUS,
) -> SiteEnvironment:
    """Everything a click on one site can be answered with."""
    shell = coordination_shell(crystal, site_label, search_radius=search_radius)
    return SiteEnvironment(
        site_label=shell.site_label,
        element=shell.element,
        shell=shell,
        geometry=shell.geometry(),
    )


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

    centre_cartesian = crystal.lattice.to_cartesian(*centre.position)
    found: list[Neighbour] = []
    for atom, position in _images(atoms, reach=reach):
        distance = crystal.lattice.distance(centre.position, position, periodic=False)
        if 1e-6 < distance <= search_radius:
            found.append(
                Neighbour(
                    atom.element,
                    atom.site_label,
                    distance,
                    # The IMAGE's position, not the asymmetric unit's --
                    # `position` is already the translated copy, and using
                    # the untranslated original would put half the shell
                    # in the wrong direction.
                    tuple(crystal.lattice.to_cartesian(*position)),
                )
            )
    found.sort(key=lambda n: n.distance)

    if not found:
        return CoordinationShell(
            site_label, centre.element, (), 0.0, search_radius, tuple(centre_cartesian)
        )

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
        centre=tuple(centre_cartesian),
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


def ionic_formula_unit(crystal: Crystal) -> list[tuple[float, int]] | None:
    """The formula unit as `[(count, charge), ...]`, or None.

    What the volume-based lattice energy needs, and the reason it could
    not previously be computed for an imported crystal: a CIF states ion
    charges only when the depositor wrote them into
    `_atom_site_type_symbol`, and most do not -- halite's own carries
    bare `Na` and `Cl`.

    Returns None rather than guessing whenever it cannot be sure:

    - any site silent about its charge (None is "not stated", NOT
      "neutral" -- see `Site.charge`);
    - no `Z`, so a cell cannot be reduced to a formula unit;
    - charges that do not balance, which means the file, the occupancies
      and the charges disagree and something is wrong with at least one.
    """
    if not crystal.formula_units_z:
        return None
    # No early "any site is silent" check: the expansion loop below
    # already returns None for an unstated charge, and a second guard
    # that cannot fail on its own is one a reader has to verify twice.
    # Measured -- mutating that early return away killed no test.
    charge_of_element = {site.element: site.charge for site in crystal.sites}
    # **A charge is per SITE, and two sites of one element may differ** --
    # magnetite's Fe(II) and Fe(III) are the case. Refuse rather than
    # pick one.
    for site in crystal.sites:
        if charge_of_element[site.element] != site.charge:
            return None

    totals: dict[int, float] = {}
    for atom in crystal.expand():
        charge = charge_of_element.get(atom.element)
        if charge is None:
            return None
        totals[charge] = totals.get(charge, 0.0) + atom.occupancy

    z = crystal.formula_units_z
    ions = [(count / z, charge) for charge, count in sorted(totals.items())]
    if abs(sum(count * charge for count, charge in ions)) > 1e-6:
        return None
    return ions
