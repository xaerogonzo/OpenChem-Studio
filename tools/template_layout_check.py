"""Screen every shipped structure template for a bad 2D layout.

Run: ``uv run --no-sync python tools/template_layout_check.py [--top N] [--all]``

Each shipped template is turned into a molblock by ``molblock_for``, the same
call the Template Library makes on insertion, then measured:

* ``overlap``  -- two atoms closer than ``OVERLAP_FRACTION`` of the median bond;
* ``bond_ratio`` -- longest / shortest bond (a bond far off the median is a
  distorted or stretched ring);
* ``crossings`` -- pairs of bonds that cross without sharing an atom;
* ``aspect``   -- bounding-box long side / short side.

The metrics are pure functions of coordinates and bonds (stdlib only); only
the molblock parsing uses RDKit. Output is a ranked list, worst first. It
reports and never edits a template.
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

Point = tuple[float, float]
Bond = tuple[int, int]

#: Atoms nearer than this fraction of the median bond overlap.
OVERLAP_FRACTION = 0.5
#: Longest/shortest bond above this is a stretched drawing.
BOND_RATIO_LIMIT = 2.0
#: Bounding-box long/short side above this is a ribbon, not a drawing (a
#: straight chain legitimately reaches it, so it is the weakest flag).
ASPECT_LIMIT = 6.0
ASPECT_CAP = 100.0


@dataclass(frozen=True)
class Layout:
    """What the screen measured on one drawing."""

    atoms: int
    min_atom_gap: float  # relative to the median bond; inf for < 2 atoms
    bond_ratio: float  # longest / shortest bond; 1.0 with < 2 bonds
    crossings: int
    aspect: float
    flags: tuple[str, ...] = field(default=())

    @property
    def score(self) -> float:
        """Rank key, larger is worse. Overlaps and crossings dominate."""
        return (
            1000.0 * (self.min_atom_gap < OVERLAP_FRACTION)
            + 100.0 * self.crossings
            + 10.0 * max(0.0, self.bond_ratio - 1.0)
            + min(5.0, max(0.0, self.aspect - 1.0))  # the weakest signal: capped
        )


def bond_lengths(points: list[Point], bonds: list[Bond]) -> list[float]:
    return [math.dist(points[a], points[b]) for a, b in bonds]


def min_atom_gap(points: list[Point], median_bond: float) -> float:
    """Smallest pairwise atom distance in units of the median bond."""
    if len(points) < 2 or median_bond <= 0:
        return math.inf
    best = math.inf
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            best = min(best, math.dist(points[i], points[j]))
    return best / median_bond


def _orient(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_cross(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    """True when the open segments p1p2 and p3p4 properly cross."""
    d1, d2 = _orient(p3, p4, p1), _orient(p3, p4, p2)
    d3, d4 = _orient(p1, p2, p3), _orient(p1, p2, p4)
    return d1 * d2 < 0 and d3 * d4 < 0


def count_crossings(points: list[Point], bonds: list[Bond]) -> int:
    """Pairs of bonds that cross and share no atom."""
    total = 0
    for i, (a, b) in enumerate(bonds):
        for c, d in bonds[i + 1 :]:
            if {a, b} & {c, d}:
                continue
            if segments_cross(points[a], points[b], points[c], points[d]):
                total += 1
    return total


def aspect_ratio(points: list[Point]) -> float:
    if len(points) < 2:
        return 1.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    wide, tall = max(xs) - min(xs), max(ys) - min(ys)
    short, long_ = sorted((wide, tall))
    if long_ <= 1e-9:
        return 1.0
    # A perfectly straight drawing has no short side: report the cap, not infinity.
    return min(ASPECT_CAP, long_ / max(short, 1e-9))


def measure(points: list[Point], bonds: list[Bond]) -> Layout:
    """All four measurements and the flags they trip."""
    lengths = bond_lengths(points, bonds)
    median = statistics.median(lengths) if lengths else 1.0
    gap = min_atom_gap(points, median)
    ratio = max(lengths) / min(lengths) if lengths and min(lengths) > 1e-9 else (math.inf if lengths else 1.0)
    crossings = count_crossings(points, bonds)
    aspect = aspect_ratio(points)
    flags = []
    if gap < OVERLAP_FRACTION:
        flags.append("overlap")
    if ratio > BOND_RATIO_LIMIT:
        flags.append("bond_ratio")
    if crossings:
        flags.append("crossing")
    # A two- or three-atom drawing is a line by nature.
    if aspect > ASPECT_LIMIT and len(points) > 4:
        flags.append("aspect")
    return Layout(len(points), gap, ratio, crossings, aspect, tuple(flags))


def layout_of_molblock(molblock: str) -> Layout:
    """Parse a molblock (hydrogens kept as drawn) and measure it."""
    from rdkit import Chem

    mol = Chem.MolFromMolBlock(molblock, removeHs=False, sanitize=False)
    if mol is None or mol.GetNumConformers() == 0:
        raise ValueError("no 2D coordinates")
    conf = mol.GetConformer()
    points = [(conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y) for i in range(mol.GetNumAtoms())]
    bonds = [(b.GetBeginAtomIdx(), b.GetEndAtomIdx()) for b in mol.GetBonds()]
    return measure(points, bonds)


def rank(rows: list[tuple[str, Layout]]) -> list[tuple[str, Layout]]:
    """Worst first; ties by id so the order is stable."""
    return sorted(rows, key=lambda row: (-row[1].score, row[0]))


def screen_shipped() -> list[tuple[str, Layout]]:
    """Every shipped template measured through the insertion path."""
    from openchem.chem.engine import ChemistryEngine
    from openchem.chem.structure_templates import load_shipped, molblock_for

    engine = ChemistryEngine()
    rows = []
    for category in load_shipped(engine):
        for entry in category.entries:
            rows.append((entry.id, layout_of_molblock(molblock_for(entry, engine))))
    return rank(rows)


def format_rows(rows: list[tuple[str, Layout]], top: int | None) -> str:
    shown = rows if top is None else rows[:top]
    lines = [f"{'template':54} {'atoms':>5} {'gap':>5} {'ratio':>6} {'cross':>5} {'aspect':>6}  flags"]
    for template_id, lay in shown:
        lines.append(
            f"{template_id:54} {lay.atoms:5d} {lay.min_atom_gap:5.2f} {lay.bond_ratio:6.2f} "
            f"{lay.crossings:5d} {lay.aspect:6.2f}  {','.join(lay.flags) or '-'}"
        )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--top", type=int, default=25, help="rows to print (default 25)")
    parser.add_argument("--all", action="store_true", help="print every template, flagged or not")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    rows = screen_shipped()
    flagged = [row for row in rows if row[1].flags]
    print(f"{len(rows)} templates screened, {len(flagged)} flagged")
    print(format_rows(rows if args.all else flagged, None if args.all else args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
