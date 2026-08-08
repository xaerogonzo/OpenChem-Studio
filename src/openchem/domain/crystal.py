"""A periodic solid, which is not a molecule and does not inherit from one.

**No inheritance in either direction.** A crystal has no molecular weight,
no rotatable bonds and no logP; a molecule has no lattice, no space group
and no occupancy. Making either a subclass of the other buys one shared
attribute -- a list of atoms -- and then obliges every molecular
calculator to decide what it means for an infinite periodic structure.
Most of them mean nothing for one, and the honest answer is a refusal
rather than a number computed about one arbitrary formula unit.

## The pieces

    Lattice             the cell: a, b, c, alpha, beta, gamma
    SymmetryOperation   one 'x,y+1/2,z' from the CIF, as matrix + shift
    Site                one entry in the asymmetric unit, with occupancy
    Crystal             all of the above, plus what they expand to

## Fractional coordinates are the state; Cartesian is an output

The same discipline `chem/electron_shells.py` applies to configurations.
A site lives at a fraction of the cell edges, and that is what symmetry
operates on, what wraps, and what a CIF stores. Cartesian coordinates are
derived on demand through the lattice's conversion matrix, because they
are what a *viewer* needs and nothing else.

Storing Cartesian would also silently pick a cell orientation. The
convention here is the standard crystallographic one -- **a along x, b in
the xy plane** -- and it is stated because any other choice produces
coordinates that are equally valid and will not match anybody else's.

## Expansion wraps, and the spike is why

3Dmol applies symmetry operators and leaves the results wherever they
land: measured on halite, 3 of the 4 chlorides came back at or outside
`[0, a)`. The *set* is right, the representatives are not. Anything that
counts cell contents, computes a density or finds a coordination number
has to wrap for itself, and wrapping needs a **tolerance rather than a
modulo** -- a coordinate at exactly 1.0 must fold to 0.0, and floating
point will not give you exactly 1.0.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field

#: How close two fractional coordinates must be to count as the same
#: point. 1e-5 of a cell edge is ~6e-5 A on a 6 A cell -- far below any
#: real displacement, and far above the noise of applying a few symmetry
#: operations in double precision.
POSITION_TOLERANCE = 1e-5


def _wrap(value: float, tolerance: float = POSITION_TOLERANCE) -> float:
    """Fold a fractional coordinate into [0, 1).

    **Not `value % 1.0`.** A coordinate that should be exactly 1.0 arrives
    as 0.9999999999 or 1.0000000001 after a couple of operations; the
    first stays at 0.99999... and the second becomes 1e-10, so the same
    atom lands at opposite ends of the cell depending on rounding. Snap to
    the boundary first, then wrap.
    """
    wrapped = value % 1.0
    if wrapped > 1.0 - tolerance or wrapped < tolerance:
        return 0.0
    return wrapped


@dataclass(frozen=True)
class Lattice:
    """The unit cell. Angles in degrees, lengths in angstrom."""

    a: float
    b: float
    c: float
    alpha: float = 90.0
    beta: float = 90.0
    gamma: float = 90.0

    @property
    def volume(self) -> float:
        """The general triclinic volume.

            V = abc * sqrt(1 - cos²a - cos²b - cos²g + 2 cos a cos b cos g)

        Reduces to `abc` for an orthogonal cell, which is the ONLY case a
        cubic test exercises -- so a cubic-only check cannot tell this
        formula from a bare multiplication. `test_crystal.py` compares
        against a computed density for a non-orthogonal cell, where the
        two answers differ.
        """
        ca = math.cos(math.radians(self.alpha))
        cb = math.cos(math.radians(self.beta))
        cg = math.cos(math.radians(self.gamma))
        factor = 1.0 - ca * ca - cb * cb - cg * cg + 2.0 * ca * cb * cg
        return self.a * self.b * self.c * math.sqrt(max(factor, 0.0))

    @property
    def is_orthogonal(self) -> bool:
        return all(
            abs(angle - 90.0) < 1e-6 for angle in (self.alpha, self.beta, self.gamma)
        )

    def to_cartesian(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        """Fractional to Cartesian, in the standard crystallographic setting.

        **a along x, b in the xy plane.** Any rotation of this is equally
        valid crystallography and will not match another program's output,
        so the convention is fixed here rather than left implicit.
        """
        ca = math.cos(math.radians(self.alpha))
        cb = math.cos(math.radians(self.beta))
        cg = math.cos(math.radians(self.gamma))
        sg = math.sin(math.radians(self.gamma))

        # The c row is the one that carries the triclinic distortion; for
        # an orthogonal cell every off-diagonal term below is zero.
        cz_term = 1.0 - ca * ca - cb * cb - cg * cg + 2.0 * ca * cb * cg
        cz = self.c * math.sqrt(max(cz_term, 0.0)) / sg

        return (
            self.a * x + self.b * cg * y + self.c * cb * z,
            self.b * sg * y + self.c * (ca - cb * cg) / sg * z,
            cz * z,
        )

    def distance(
        self,
        first: tuple[float, float, float],
        second: tuple[float, float, float],
        *,
        periodic: bool = True,
    ) -> float:
        """Distance between two FRACTIONAL positions, in angstrom.

        `periodic` applies the minimum-image convention: the shortest
        separation over all lattice translations, which is the only
        meaningful distance in a crystal. Two ions on opposite faces of
        the cell are neighbours, and a non-periodic distance would call
        them a cell-width apart.

        Minimum image is exact only while the cutoff stays below half the
        shortest cell edge. That holds for coordination distances in the
        cells this handles, and `coordination_shell` refuses when it does
        not -- see `chem/crystal_analysis.py`.
        """
        deltas = [s - f for f, s in zip(first, second)]
        if periodic:
            deltas = [d - round(d) for d in deltas]
        x, y, z = self.to_cartesian(*deltas)
        return math.sqrt(x * x + y * y + z * z)


@dataclass(frozen=True)
class SymmetryOperation:
    """One `_symmetry_equiv_pos_as_xyz` entry, as a matrix and a shift."""

    #: 3x3, rows are the coefficients of x, y, z in the output.
    rotation: tuple[tuple[float, float, float], ...]
    translation: tuple[float, float, float]
    #: The string it was parsed from, kept for display and for debugging a
    #: structure whose operations are unusual.
    text: str = ""

    def apply(self, position: tuple[float, float, float]) -> tuple[float, float, float]:
        return tuple(
            sum(coefficient * value for coefficient, value in zip(row, position)) + shift
            for row, shift in zip(self.rotation, self.translation)
        )

    @property
    def is_identity(self) -> bool:
        return self.rotation == ((1, 0, 0), (0, 1, 0), (0, 0, 1)) and self.translation == (
            0.0,
            0.0,
            0.0,
        )


_TERM = re.compile(r"([+-]?)\s*(?:(\d+)\s*/\s*(\d+)|(\d*\.?\d+))?\s*\*?\s*([xyz])?")


def parse_symmetry_operation(text: str) -> SymmetryOperation:
    """Parse `'-x, y+1/2, -z+1/2'` into a matrix and a translation.

    **Fractions, not decimals.** CIFs write `1/2`, `1/3`, `2/3` and `5/6`,
    and 1/3 is the case that matters: writing 0.333 instead loses enough
    precision that a trigonal structure's atoms miss their symmetry
    partners by more than `POSITION_TOLERANCE`. Parsed as a ratio and
    divided once.
    """
    rows: list[tuple[float, float, float]] = []
    shifts: list[float] = []

    parts = [part.strip() for part in text.replace("'", "").replace('"', "").split(",")]
    if len(parts) != 3:
        raise ValueError(f"a symmetry operation needs three components: {text!r}")

    for part in parts:
        coefficients = {"x": 0.0, "y": 0.0, "z": 0.0}
        shift = 0.0
        for sign, numerator, denominator, decimal, axis in _TERM.findall(part):
            if not (numerator or decimal or axis):
                continue
            factor = -1.0 if sign == "-" else 1.0
            if numerator and denominator:
                magnitude = float(numerator) / float(denominator)
            elif decimal:
                magnitude = float(decimal)
            else:
                magnitude = 1.0
            if axis:
                coefficients[axis] += factor * magnitude
            else:
                shift += factor * magnitude
        rows.append((coefficients["x"], coefficients["y"], coefficients["z"]))
        shifts.append(shift)

    return SymmetryOperation(
        rotation=tuple(rows), translation=tuple(shifts), text=text.strip()
    )


IDENTITY = parse_symmetry_operation("x,y,z")


@dataclass(frozen=True)
class Site:
    """One entry of the asymmetric unit."""

    label: str
    element: str
    #: FRACTIONAL. See the module docstring for why this is the state.
    position: tuple[float, float, float]
    #: Fractional occupancy. Below 1 means the site is shared or partly
    #: vacant, which is ordinary in minerals and is NOT an error.
    occupancy: float = 1.0

    @property
    def is_fully_occupied(self) -> bool:
        return abs(self.occupancy - 1.0) < 1e-6


@dataclass(frozen=True)
class ExpandedAtom:
    """One atom of the expanded cell, and where it came from."""

    element: str
    position: tuple[float, float, float]
    occupancy: float
    #: Which `Site` of the asymmetric unit generated it, so a coordination
    #: number can be reported per crystallographic site rather than per
    #: atom -- the four chlorides of halite are one site, not four.
    site_label: str


@dataclass(frozen=True)
class Crystal:
    """A periodic structure: cell, symmetry, and an asymmetric unit."""

    lattice: Lattice
    sites: tuple[Site, ...]
    operations: tuple[SymmetryOperation, ...] = (IDENTITY,)
    space_group: str = ""
    space_group_number: int | None = None
    formula_units_z: int | None = None
    name: str = ""
    source: str = ""
    #: Anything the reader could not use. Kept rather than dropped: a
    #: structure with disorder or anisotropic parameters is still worth
    #: showing, and silently ignoring the fields is how a tool starts
    #: pretending it understood more than it did.
    unhandled: tuple[str, ...] = field(default_factory=tuple)

    def expand(self) -> tuple[ExpandedAtom, ...]:
        """Every atom of one unit cell, wrapped into it, deduplicated.

        **Deduplication is required, not tidy.** A site on a special
        position is mapped onto itself by many operations -- halite's
        sodium is invariant under all of them -- so a naive product of
        sites and operations gives 4 sodiums from 4 operations but would
        give 192 from the full Fm-3m list. The count only comes out right
        if coincident images collapse.
        """
        atoms: list[ExpandedAtom] = []
        for site in self.sites:
            seen: list[tuple[float, float, float]] = []
            for operation in self.operations:
                wrapped = tuple(_wrap(value) for value in operation.apply(site.position))
                if any(_same_position(wrapped, other) for other in seen):
                    continue
                seen.append(wrapped)
                atoms.append(
                    ExpandedAtom(
                        element=site.element,
                        position=wrapped,
                        occupancy=site.occupancy,
                        site_label=site.label,
                    )
                )
        return tuple(atoms)

    def cartesian(self) -> tuple[tuple[str, float, float, float], ...]:
        """The expanded cell in Cartesian coordinates, for a viewer."""
        return tuple(
            (atom.element, *self.lattice.to_cartesian(*atom.position))
            for atom in self.expand()
        )

    def composition(self) -> dict[str, float]:
        """Atoms per unit cell, by element, weighted by occupancy.

        Fractional on purpose. A half-occupied site really does contribute
        half an atom to the cell, and rounding it away would silently turn
        a solid solution into a stoichiometric compound.
        """
        totals: dict[str, float] = {}
        for atom in self.expand():
            totals[atom.element] = totals.get(atom.element, 0.0) + atom.occupancy
        return totals


def _same_position(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
    tolerance: float = POSITION_TOLERANCE,
) -> bool:
    """Whether two wrapped fractional positions are the same point.

    Compares across the periodic boundary: 0.0 and 0.99999 are the same
    place, and a plain componentwise difference would not say so.
    """
    return all(
        min(abs(f - s), 1.0 - abs(f - s)) < tolerance for f, s in zip(first, second)
    )


@dataclass(slots=True)
class CrystalModel:
    """A crystal as a project DOCUMENT: identity, a name, and its source.

    Separate from `Crystal` above, which is the crystallography and has no
    business carrying a uuid. The split mirrors `MoleculeModel` beside an
    RDKit `Mol`, and `MacromoleculeModel` beside a structure file.

    **It stores the CIF TEXT, not the parsed `Crystal`**, following
    `MacromoleculeModel.structure_text`. Three reasons, and the third
    decided it:

    - a round trip through `Lattice`/`Site`/`SymmetryOperation` would need
      four more `to_dict`/`from_dict` pairs to serialise something the
      file already states perfectly well;
    - `Crystal.unhandled` records what the reader could not use, and
      freezing a parse would freeze that ignorance with it;
    - **a reader improvement then reaches projects already saved.**
      Reparse and an old project gains whatever the reader learned since;
      store the parse and it is stuck with the reader that first read it.

    The cost is reparsing on load, which is milliseconds.

    **There is deliberately no `to_crystal()` here.** `domain/` may not
    import `openchem.chem` -- `test_the_crystal_domain_model_imports_no_`
    `chemistry_toolkit` enforces it, and caught the first version of this
    class doing exactly that behind a deferred import. Callers already
    hold the chem layer, so they call `read_cif(model.cif_text)`
    themselves. Not caching a parse beside the text is right for a second
    reason anyway: two answers to the same question the moment either
    changed.
    """

    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    display_name: str = "Untitled crystal"
    #: The CIF exactly as read, including everything the reader ignored.
    cif_text: str = ""
    #: Where it came from, for a report header. Deliberately a NAME and
    #: not a live path -- a project must open on a machine that never had
    #: the original file.
    source_name: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "uuid": self.uuid,
            "display_name": self.display_name,
            "cif_text": self.cif_text,
            "source_name": self.source_name,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> CrystalModel:
        return cls(
            uuid=data["uuid"],
            display_name=data.get("display_name", "Untitled crystal"),
            cif_text=data.get("cif_text", ""),
            source_name=data.get("source_name", ""),
            metadata=dict(data.get("metadata", {})),
        )
