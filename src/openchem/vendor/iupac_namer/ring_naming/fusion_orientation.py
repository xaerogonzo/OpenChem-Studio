"""Orientation (P-25.3.2.3) and numbering (P-25.3.3) of a fused ring system.

Naming round 5, N3. The numbering of a fused ring system is not a property
of its graph alone: the book first DRAWS the system -- every ring in one of
the permitted shapes, as many rings as possible in a horizontal row, then as
many as possible up and to the right -- and numbers clockwise from the
uppermost-right ring of that drawing. Heteroatom and fusion-atom criteria
only choose among the numberings the preferred drawings allow. Without the
drawing, cyclohepta[b]quinoline's nitrogen would take locant 1; with it, the
nitrogen sits where the book puts it.

**THE DRAWING MODEL.** Every permitted shape (pdf p. 214: three- to eight-
membered rings) has vertical left and right sides, so each side of a ring
faces one of eight compass directions, 0 = E, 1 = NE, 2 = N ... 7 = SE, and a
ring's sides, taken counterclockwise, face the directions of its shape:

    3  (0,3,5) or (1,4,7)        6  (0,1,3,4,5,7)
    4  (0,2,4,6)                 7  (0,1,2,3,4,5,7) or (0,1,3,4,5,6,7)
    5  (0,1,3,4,6) or (0,2,4,5,7)    8  (0,1,...,7)

Two fused rings share a side, which faces opposite ways in each; their
centres differ by a lattice step in that direction (E = (2, 0), NE = (1, 1),
N = (0, 2) ...), exact for hexagons and close enough for the quadrant counts
the criteria need. A drawing is a choice of shape and rotation for every
ring that agrees on every shared side and puts no two rings in one place;
`drawings` enumerates them, and both faces of the paper are tried.

**WHAT IS REFUSED** (`Unsupported`, never a guess): rings larger than eight
(the book's distorted shapes), rings sharing more than one bond (bridged
fused, P-25.4), a system with no planar drawing in these shapes, and interior
atoms whose locant rule the module does not implement.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Iterator

from openchem.vendor.iupac_namer.types import Locant, Numbering

#: Unit step between the centres of two rings sharing a side that faces
#: direction d (from the first ring). Hexagonal lattice, doubled x.
VEC: dict[int, tuple[int, int]] = {
    0: (2, 0), 1: (1, 1), 2: (0, 2), 3: (-1, 1),
    4: (-2, 0), 5: (-1, -1), 6: (0, -2), 7: (1, -1),
}

#: Directions faced by a ring's sides, counterclockwise (pdf p. 214).
SHAPES: dict[int, tuple[tuple[int, ...], ...]] = {
    3: ((0, 3, 5), (1, 4, 7)),
    4: ((0, 2, 4, 6),),
    5: ((0, 1, 3, 4, 6), (0, 2, 4, 5, 7)),
    6: ((0, 1, 3, 4, 5, 7),),
    7: ((0, 1, 2, 3, 4, 5, 7), (0, 1, 3, 4, 5, 6, 7)),
    8: ((0, 1, 2, 3, 4, 5, 6, 7),),
}

#: P-25.3.3.1.2 (b): the element order for low locants among heteroatoms.
HETERO_ORDER = (
    "F", "Cl", "Br", "I", "O", "S", "Se", "Te", "N", "P", "As", "Sb", "Bi",
    "Si", "Ge", "Sn", "Pb", "B", "Al", "Ga", "In", "Tl",
)


class Unsupported(Exception):
    """The system is outside what this module orients and numbers. The
    message says why; a caller must not fall back to a guessed numbering.

    `code` says what KIND of refusal it is, so a caller decides by a field and
    never by the prose: `NEEDS_UNBUILT_CONSTRUCTION` means a fusion name
    exists and needs a construction this round does not build (a
    second-order or multiparent name), so no older fusion route may stand in
    for it; `OUTSIDE_CLASS` is everything else."""

    NEEDS_UNBUILT_CONSTRUCTION = "NEEDS_UNBUILT_CONSTRUCTION"
    OUTSIDE_CLASS = "OUTSIDE_CLASS"

    def __init__(self, message: str, code: str = "OUTSIDE_CLASS") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FusedSystem:
    """Rings as counterclockwise atom cycles in ONE planar embedding."""

    rings: tuple[tuple[int, ...], ...]
    #: (ring, bond index) -> (other ring, its bond index), for shared sides.
    partner: dict[tuple[int, int], tuple[int, int]]

    @property
    def atoms(self) -> frozenset[int]:
        return frozenset(a for r in self.rings for a in r)

    def mirrored(self) -> "FusedSystem":
        rings = tuple(tuple(reversed(r)) for r in self.rings)
        return _with_partners(rings)


def _bond(ring: tuple[int, ...], i: int) -> tuple[int, int]:
    return ring[i], ring[(i + 1) % len(ring)]


def _with_partners(rings: tuple[tuple[int, ...], ...]) -> FusedSystem:
    where: dict[tuple[int, int], tuple[int, int]] = {}
    for r, ring in enumerate(rings):
        for i in range(len(ring)):
            where[_bond(ring, i)] = (r, i)
    partner: dict[tuple[int, int], tuple[int, int]] = {}
    for (u, v), (r, i) in where.items():
        other = where.get((v, u))
        if other is not None:
            partner[(r, i)] = other
    return FusedSystem(rings=rings, partner=partner)


def prepare(mol, ring_atom_tuples) -> FusedSystem:
    """Orient every ring consistently, or refuse.

    *ring_atom_tuples* are the rings' atoms in ring order (RDKit's
    `AtomRings` order is). A shared bond must run opposite ways in the two
    rings for one planar embedding; that fixes each ring's direction from its
    neighbour's, and a ring reached two ways that disagrees means there is no
    such embedding.
    """
    rings = [tuple(r) for r in ring_atom_tuples]
    for ring in rings:
        if len(ring) > 8:
            raise Unsupported(f"a {len(ring)}-membered ring needs a distorted shape")
    for a, b in itertools.combinations(range(len(rings)), 2):
        shared = set(rings[a]) & set(rings[b])
        if len(shared) > 2:
            raise Unsupported("two rings share more than one bond (bridged fused, P-25.4)")
        if len(shared) == 1:
            raise Unsupported("two rings share one atom (spiro)")
        if len(shared) == 2:
            u, v = shared
            if mol.GetBondBetweenAtoms(u, v) is None:
                raise Unsupported("two rings share two unbonded atoms")

    for i, ring in enumerate(rings):
        if len(ring) >= 7:
            fused = sum(
                1 for j, other in enumerate(rings)
                if j != i and len(set(ring) & set(other)) == 2
            )
            if fused >= 3:
                # Measured on the book's P-25 examples (2026-09-19): of the
                # 8 systems with this shape, 4 numbered as OPSIN numbers
                # them and 4 did not -- their drawings need a shape this
                # model does not have (a hexagon on an octagon's horizontal
                # side). A coin flip is refused, not shipped.
                raise Unsupported(
                    f"a {len(ring)}-membered ring fused on {fused} sides may need a "
                    "shape this drawing model lacks"
                )

    def bonds(ring):
        return {_bond(ring, i) for i in range(len(ring))}

    fixed: dict[int, tuple[int, ...]] = {0: rings[0]}
    queue = [0]
    while queue:
        r = queue.pop()
        for s in range(len(rings)):
            if s == r or len(set(rings[r]) & set(rings[s])) != 2:
                continue
            forward = bonds(fixed[r])
            candidate = rings[s]
            if bonds(candidate) & forward:  # same direction: flip it
                candidate = tuple(reversed(candidate))
            if s in fixed:
                if fixed[s] != candidate and bonds(fixed[s]) != bonds(candidate):
                    raise Unsupported("the rings admit no single planar embedding")
                continue
            fixed[s] = candidate
            queue.append(s)
    if len(fixed) != len(rings):
        raise Unsupported("the rings are not one fused system")
    system = _with_partners(tuple(fixed[i] for i in range(len(rings))))
    if _is_helicene(system):
        raise Unsupported(
            "a helicene is oriented and numbered by its own rule (P-25.3.3.1.1: "
            "a terminal ring in the upper right quadrant)"
        )
    return system


def _is_helicene(system: FusedSystem) -> bool:
    """An unbranched chain of five or more hexagons, every middle ring fused
    on sides one apart (an angular, phenanthrene-like bend) and every bend
    turning the SAME way. Picene's zigzag alternates, and is numbered by the
    general rule."""
    rings = system.rings
    if len(rings) < 5 or any(len(r) != 6 for r in rings):
        return False
    links: dict[int, list[tuple[int, int]]] = {}
    for (r, i), (s, _j) in system.partner.items():
        links.setdefault(r, []).append((i, s))
    if any(len(v) > 2 for v in links.values()):
        return False
    ends = [r for r in range(len(rings)) if len(links.get(r, [])) == 1]
    if len(ends) != 2:
        return False
    turns = []
    for r, sides in links.items():
        if len(sides) != 2:
            continue
        (i, _a), (k, _b) = sides
        gap = (k - i) % 6
        if gap not in (2, 4):  # 3 is a straight, anthracene-like, ring
            return False
        turns.append(gap)
    # Walk the chain so each middle ring's turn is read in travel order.
    order = [ends[0]]
    while len(order) < len(rings):
        nxt = [s for _i, s in links[order[-1]] if s not in order]
        if not nxt:
            return False
        order.append(nxt[0])
    signs = set()
    for prev, r, nxt in zip(order, order[1:], order[2:]):
        side_in = next(i for i, s in links[r] if s == prev)
        side_out = next(i for i, s in links[r] if s == nxt)
        signs.add((side_out - side_in) % 6)
    return len(signs) == 1


@dataclass(frozen=True)
class Drawing:
    system: FusedSystem
    #: per ring: the direction each of its bonds faces
    faces: tuple[tuple[int, ...], ...]
    positions: tuple[tuple[int, int], ...]


def drawings(system: FusedSystem, limit: int = 20000) -> Iterator[Drawing]:
    """Every drawing of *system* in the permitted shapes (this face of the
    paper). Backtracking in ring order from ring 0."""
    rings = system.rings
    n = len(rings)
    order = [0]
    seen = {0}
    for r in order:
        for (a, _i), (b, _j) in system.partner.items():
            if a == r and b not in seen:
                seen.add(b)
                order.append(b)
    if len(order) != n:
        raise Unsupported("the rings are not one fused system")

    faces: list[tuple[int, ...] | None] = [None] * n
    pos: list[tuple[int, int] | None] = [None] * n
    produced = 0

    def options(r: int):
        ring = rings[r]
        size = len(ring)
        placed_links = [
            (i, other) for i in range(size)
            if (other := system.partner.get((r, i))) is not None and faces[other[0]] is not None
        ]
        for shape in SHAPES[size]:
            offsets = range(size)
            if placed_links:
                i, (s, j) = placed_links[0]
                need = (faces[s][j] + 4) % 8  # type: ignore[index]
                if need not in shape:
                    continue
                offsets = [(shape.index(need) - i) % size]
            for k in offsets:
                f = tuple(shape[(i + k) % size] for i in range(size))
                if placed_links:
                    i, (s, j) = placed_links[0]
                    step = VEC[faces[s][j]]  # type: ignore[index]
                    p = (pos[s][0] + step[0], pos[s][1] + step[1])  # type: ignore[index]
                else:
                    p = (0, 0)
                ok = True
                for i2, (s2, j2) in placed_links:
                    if (faces[s2][j2] + 4) % 8 != f[i2]:  # type: ignore[index]
                        ok = False
                        break
                    step = VEC[faces[s2][j2]]  # type: ignore[index]
                    if (pos[s2][0] + step[0], pos[s2][1] + step[1]) != p:  # type: ignore[index]
                        ok = False
                        break
                if ok and any(q == p for q in pos if q is not None):
                    ok = False
                if ok:
                    yield f, p

    def place(depth: int):
        nonlocal produced
        if produced >= limit:
            return
        if depth == n:
            produced += 1
            yield Drawing(system, tuple(faces), tuple(pos))  # type: ignore[arg-type]
            return
        r = order[depth]
        for f, p in options(r):
            faces[r], pos[r] = f, p
            yield from place(depth + 1)
            faces[r], pos[r] = None, None

    yield from place(0)


# --- P-25.3.2.3.3: which drawing -------------------------------------------


def _rows(d: Drawing) -> list[list[int]]:
    """Maximal chains of rings joined by vertical common sides (E/W)."""
    east: dict[int, int] = {}
    for (r, i), (s, _j) in d.system.partner.items():
        if d.faces[r][i] == 0:
            east[r] = s
    has_west = set(east.values())
    rows = []
    for start in range(len(d.system.rings)):
        if start in has_west:
            continue
        row = [start]
        while row[-1] in east:
            row.append(east[row[-1]])
        rows.append(row)
    return rows


def _weights(x: float, y: float, cx: float, cy: float) -> tuple[float, float, float]:
    """(upper right, lower left, above) share of one ring."""
    def split(v, c):
        return 1.0 if v > c else (0.5 if v == c else 0.0)
    right, up = split(x, cx), split(y, cy)
    left, down = split(-x, -cx), split(-y, -cy)
    return right * up, left * down, up


def orientation_key(d: Drawing) -> tuple:
    """(a) most rings in a horizontal row, (b) most in the upper right
    quadrant, (c) fewest in the lower left, (d) most above the row. Larger is
    better; the best over the drawing's longest rows."""
    rows = _rows(d)
    longest = max(len(r) for r in rows)
    best = None
    for row in rows:
        if len(row) != longest:
            continue
        xs = sorted(d.positions[r][0] for r in row)
        cy = d.positions[row[0]][1]
        mid = len(xs) // 2
        cx = xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2
        ur = ll = above = 0.0
        for (x, y) in d.positions:
            a, b, c = _weights(x, y, cx, cy)
            ur, ll, above = ur + a, ll + b, above + c
        key = (longest, ur, -ll, above)
        if best is None or key > best:
            best = key
    return best


def preferred_drawings(system: FusedSystem) -> list[Drawing]:
    everything: list[Drawing] = []
    for face in (system, system.mirrored()):
        everything.extend(drawings(face))
    if not everything:
        raise Unsupported("no drawing in the permitted shapes")
    keyed = [(orientation_key(d), d) for d in everything]
    top = max(k for k, _d in keyed)
    return [d for k, d in keyed if k == top]


# --- P-25.3.3: numbering ------------------------------------------------------


def _ring_count(system: FusedSystem) -> dict[int, int]:
    count: dict[int, int] = {}
    for ring in system.rings:
        for a in ring:
            count[a] = count.get(a, 0) + 1
    return count


def _clockwise_periphery(system: FusedSystem) -> dict[int, int]:
    """successor of each peripheral atom, walking the periphery clockwise:
    a peripheral bond belongs to one ring, and clockwise around the system
    runs it against that ring's counterclockwise direction."""
    succ: dict[int, int] = {}
    for r, ring in enumerate(system.rings):
        for i in range(len(ring)):
            if (r, i) in system.partner:
                continue
            u, v = _bond(ring, i)
            if v in succ:
                raise Unsupported("the periphery passes through an atom twice")
            succ[v] = u
    return succ


def numberings_for(d: Drawing, mol) -> list[dict[int, Locant]]:
    """The numberings P-25.3.3.1.1 allows for one preferred drawing."""
    system = d.system
    count = _ring_count(system)
    succ = _clockwise_periphery(system)
    peripheral = set(succ)
    interior = [a for a in system.atoms if a not in peripheral]
    uppermost = max(range(len(system.rings)),
                    key=lambda r: (d.positions[r][1], d.positions[r][0]))

    def element(a):
        return mol.GetAtomWithIdx(a).GetSymbol()

    starts = [a for a in system.rings[uppermost]
              if a in peripheral and count[a] == 1
              and not (succ_pred(succ).get(a) in system.rings[uppermost]
                       and count[succ_pred(succ)[a]] == 1)]
    if not starts:
        # P-25.3.3.1.1: no nonfusion atom -- start in the next ring clockwise.
        a = next(x for x in system.rings[uppermost] if x in peripheral)
        for _ in range(len(succ)):
            a = succ[a]
            if count[a] == 1:
                starts = [a]
                break
    out = []
    for start in starts:
        loc: dict[int, Locant] = {}
        number = 0
        letter = 0
        a = start
        for _ in range(len(succ)):
            if count[a] == 1 or element(a) != "C":
                number += 1
                letter = 0
                loc[a] = Locant.numeric(number)
            else:
                loc[a] = Locant.numeric(number, chr(ord("a") + letter))
                letter += 1
            a = succ[a]
        if interior:
            hetero = [x for x in interior if element(x) != "C"]
            carbon = [x for x in interior if element(x) == "C"]
            if hetero:
                raise Unsupported("interior heteroatoms (P-25.3.3.2) are not numbered here")
            for x in carbon:
                loc[x] = _interior_carbon_locant(mol, x, loc, peripheral)
        out.append(loc)
    return out


def succ_pred(succ: dict[int, int]) -> dict[int, int]:
    return {v: u for u, v in succ.items()}


def _interior_carbon_locant(mol, atom, loc, peripheral) -> Locant:
    """P-25.3.3.3.1: the nearest peripheral atom's locant with a superscript
    for the bond count; the lowest such locant when there is a choice."""
    frontier, seen, dist = [atom], {atom}, 0
    while frontier:
        dist += 1
        nxt = []
        hits = []
        for a in frontier:
            for nb in mol.GetAtomWithIdx(a).GetNeighbors():
                b = nb.GetIdx()
                if b in seen:
                    continue
                seen.add(b)
                if b in peripheral and b in loc:
                    hits.append(loc[b])
                elif b not in peripheral:
                    nxt.append(b)
        if hits:
            base = min(hits, key=locant_key)
            return Locant.numeric(base._numeric_value or 0, f"{base.suffix}{dist}")
        frontier = nxt
    raise Unsupported("an interior atom reaches no peripheral atom")


def locant_key(loc: Locant) -> tuple[int, str]:
    return (loc._numeric_value or 0, loc.suffix)


def _criteria(loc: dict[int, Locant], mol, count, indicated_candidates) -> tuple:
    """P-25.3.3.1.2 (a)-(d) and (f), as a key where smaller is preferred."""
    def el(a):
        return mol.GetAtomWithIdx(a).GetSymbol()

    hetero = sorted((locant_key(loc[a]) for a in loc if el(a) != "C"))
    by_element = []
    for e in HETERO_ORDER:
        by_element.extend(sorted(locant_key(loc[a]) for a in loc if el(a) == e))
    fusion_carbon = sorted(locant_key(loc[a]) for a in loc if el(a) == "C" and count.get(a, 1) > 1)
    fusion_hetero = sorted(locant_key(loc[a]) for a in loc if el(a) != "C" and count.get(a, 1) > 1)
    indicated = sorted(locant_key(loc[a]) for a in indicated_candidates if a in loc)
    return (
        tuple(hetero), tuple(by_element), tuple(fusion_carbon),
        tuple(fusion_hetero), tuple(indicated[:1]),
    )


def indicated_hydrogen_candidates(mol, atoms) -> frozenset[int]:
    """Atoms of the MANCUDE system that can carry the indicated hydrogen:
    those whose removal from the double-bond system leaves a perfect
    matching. Empty when the system needs none (an even, fully matchable
    system such as naphthalene)."""
    atoms = sorted(atoms)
    adj = {a: [nb.GetIdx() for nb in mol.GetAtomWithIdx(a).GetNeighbors()
               if nb.GetIdx() in set(atoms)] for a in atoms}

    def sp2_capable(a):
        atom = mol.GetAtomWithIdx(a)
        # a ring heteroatom with a lone pair (O, S, NH) takes no double bond
        # in the mancude form only when it must; keep it matchable.
        return atom.GetSymbol() not in ("O", "S", "Se", "Te")

    base = [a for a in atoms if sp2_capable(a)]

    def matchable(pool):
        pool = set(pool)
        match: dict[int, int] = {}

        def augment(u, seen):
            for v in adj[u]:
                if v not in pool or v in seen:
                    continue
                seen.add(v)
                if v not in match or augment(match[v], seen):
                    match[v] = u
                    match[u] = v
                    return True
            return False

        size = 0
        for u in sorted(pool):
            if u in match:
                continue
            if augment(u, {u}):
                size += 1
        return 2 * size == len(pool)

    if matchable(base):
        return frozenset()
    return frozenset(a for a in base if matchable([b for b in base if b != a]))


def preferred_numberings(mol, ring_atom_tuples) -> list[Numbering]:
    """The numberings of the whole fused system that survive the preferred
    orientation (P-25.3.2.3.3) and P-25.3.3.1.2 (a)-(d), (f). More than one
    only when they are equivalent by symmetry."""
    system = prepare(mol, ring_atom_tuples)
    count = _ring_count(system)
    indicated = indicated_hydrogen_candidates(mol, system.atoms)
    candidates: list[dict[int, Locant]] = []
    for drawing in preferred_drawings(system):
        candidates.extend(numberings_for(drawing, mol))
    if not candidates:
        raise Unsupported("the preferred drawing yields no numbering")
    keyed = [(_criteria(c, mol, count, indicated), c) for c in candidates]
    best = min(k for k, _c in keyed)
    unique: dict[tuple, dict[int, Locant]] = {}
    for k, c in keyed:
        if k == best:
            unique[tuple(sorted((a, l.label) for a, l in c.items()))] = c
    return [
        Numbering(
            _assignments=tuple(sorted(c.items())),
            locant_set=tuple(sorted(c.values(), key=locant_key)),
        )
        for c in unique.values()
    ]
