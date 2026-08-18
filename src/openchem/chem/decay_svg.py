"""A decay chain, drawn on the chart of the nuclides.

**NO Qt.** Same split as `lewis_svg.py`: this produces an SVG string and
the placed geometry, and the dialog turns a click into a nuclide. That is
what makes "does the picture have the right shape" testable without
building a window.

## The layout needs no algorithm, because physics already chose one

x is the neutron number and y is the proton number, which is the chart
every nuclear chemistry textbook draws. Alpha decay is then two cells
down and two left, beta-minus one up and one left, beta-plus one down and
one right -- so the SHAPE of a chain carries meaning rather than being
whatever a force-directed layout settled on.

**IT IS INJECTIVE BY CONSTRUCTION, and that was measured rather than
hoped for.** (Z, N) determines A, so two different nuclides can never
land in the same cell; a sweep over 200+ chains from ten elements found
**zero collisions**. A general graph layout would have to solve overlap;
this one cannot have any.

## What the picture is FOR

"this wouldn't be so much for practical uses, but it would just be fun to
look at, and educational too" -- so it is optimised for reading, not for
compactness. Measured extents: U-238 is 37 nodes over 15 rows and 27
columns, U-235 is 35, thorium-232 is 25, and the largest chain in the
whole table (Au-169) is 161 over 22 by 21. The wide ones need the
zoom-and-scroll view the Lewis dialog already has, which is why they
share it.
"""

from __future__ import annotations

from dataclasses import dataclass

from openchem.chem.decay import (
    DecayTree,
    OFF_TABLE,
    STABLE,
    UNFOLLOWABLE_MODE,
    format_branching,
    format_mode,
    mode_family,
)
from openchem.chem.lewis_svg import BASELINE_SHIFT
from openchem.chem.nuclides import format_half_life

#: One grid cell. Wide enough for "Pa-234" beside a half-life.
CELL_W, CELL_H = 84.0, 54.0
BOX_W, BOX_H = 70.0, 40.0
MARGIN = 26.0

#: **COLOUR SAYS WHICH KIND OF DECAY, AND NEVER SAYS IT ALONE** -- the
#: legend names every family, and the edge's own mode is in the node
#: tooltip the dialog builds. Chosen to stay apart under the commonest
#: colour blindness: red/blue/orange rather than red/green.
FAMILY_COLOUR: dict[str, str] = {
    "alpha": "#c0392b",
    "beta_minus": "#2471a3",
    "beta_plus": "#b9770e",
    "cluster": "#7d3c98",
    "other": "#5d6d7e",
    # An isomeric transition goes nowhere on this chart -- same cell,
    # lower state -- so it is drawn as the marker on a stacked box rather
    # than as a line, and this colour is what marks it.
    "isomeric": "#117a65",
}

_ROOT_FILL = "#fdf3d0"
_STABLE_FILL = "#d7ead7"
_NODE_FILL = "#ffffff"
_OFF_TABLE_FILL = "#efefef"
_STROKE = "#7f8c8d"

#: Below this, a branching is worth writing on the edge. A chain is
#: mostly 100% steps and labelling those adds noise where the picture is
#: already unambiguous; the RARE branches are the interesting part, and
#: on U-238 there are 23 of them among 52 edges.
LABEL_BRANCHING_BELOW = 99.9

#: How heavily to draw an edge, by branching: (at least this %, width,
#: opacity). **NOTHING IS DROPPED** -- Alex chose the full branching tree
#: over a thresholded one, and this is not a threshold in disguise; every
#: edge is drawn and every one is clickable.
#:
#: It exists because the first render was UNREADABLE and the reason was
#: instructive. On the chart of the nuclides a cluster emission is an
#: enormous jump -- uranium-238's 32Si branch moves 14 protons and 18
#: neutrons at once -- so at uniform weight a handful of decays with
#: branchings around 1e-10% drew lines across the entire width while the
#: actual uranium series, the thing the picture is FOR, was a faint
#: zigzag underneath them. Weighting says which paths matter, which is
#: information the diagram was previously throwing away.
BRANCHING_WEIGHTS: tuple[tuple[float, float, float], ...] = (
    (50.0, 2.2, 0.90),
    (1.0, 1.5, 0.75),
    (1e-4, 0.9, 0.50),
    (0.0, 0.6, 0.35),
)

#: An unquantified branching (`?`, the commonest qualifier in NUBASE at
#: 1,755 entries) is drawn at the MIDDLE weight, not the lightest: "the
#: mode is expected and nobody has measured how often" is not the same
#: claim as "vanishingly rare", and drawing it as the latter would be the
#: diagram inventing a number.
UNMEASURED_WEIGHT = (1.5, 0.75)


@dataclass(frozen=True)
class PlacedNode:
    """One nuclide's box, in the diagram's own coordinates.

    Returned rather than re-derived by the dialog, for the reason the
    Lewis renderer returns its slots: two implementations of one layout
    is where a click starts landing on the wrong thing.
    """

    z: int
    a: int
    name: str
    x: float
    y: float
    width: float
    height: float
    is_root: bool
    is_stable: bool

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.x + self.width and self.y <= y <= self.y + self.height


@dataclass(frozen=True)
class DecayDiagram:
    svg: str
    nodes: tuple[PlacedNode, ...]
    width: float
    height: float
    families: tuple[str, ...]

    def node_at(self, x: float, y: float) -> PlacedNode | None:
        for node in self.nodes:
            if node.contains(x, y):
                return node
        return None


def render_decay_svg(tree: DecayTree) -> DecayDiagram:
    """The whole reachable graph, as one SVG."""
    zs = [z for z, _a in tree.nodes]
    ns = [a - z for z, a in tree.nodes]
    min_z, max_z = min(zs), max(zs)
    min_n, max_n = min(ns), max(ns)

    width = (max_n - min_n + 1) * CELL_W + 2 * MARGIN
    height = (max_z - min_z + 1) * CELL_H + 2 * MARGIN

    def centre(z: int, a: int) -> tuple[float, float]:
        # y is inverted: higher Z at the top, as every chart draws it.
        return (
            MARGIN + (a - z - min_n) * CELL_W + CELL_W / 2,
            MARGIN + (max_z - z) * CELL_H + CELL_H / 2,
        )

    placed = tuple(
        PlacedNode(
            z=z,
            a=a,
            name=nuclide.name,
            x=centre(z, a)[0] - BOX_W / 2,
            y=centre(z, a)[1] - BOX_H / 2,
            width=BOX_W,
            height=BOX_H,
            is_root=(z, a) == tree.root,
            is_stable=nuclide.is_stable,
        )
        for (z, a), nuclide in sorted(tree.nodes.items())
    )

    leaves = tree.leaves()
    families: list[str] = []
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_n(width)}" '
        f'height="{_n(height)}" viewBox="0 0 {_n(width)} {_n(height)}">',
        f'<rect width="{_n(width)}" height="{_n(height)}" fill="#ffffff"/>',
    ]

    # Edges first, so a box always sits on top of the lines reaching it.
    for (z, a), outgoing in sorted(tree.edges.items()):
        for edge in outgoing:
            if edge.to is None:
                continue
            family = mode_family(edge.mode)
            if family not in families:
                families.append(family)
            parts.append(_edge_svg(centre(z, a), centre(*edge.to), edge, family))

    for node in placed:
        nuclide = tree.nodes[(node.z, node.a)]
        reason = leaves.get((node.z, node.a), "")
        parts.append(_node_svg(node, format_half_life(nuclide.half_life), reason))

    parts.append("</svg>")
    return DecayDiagram(
        svg="".join(parts),
        nodes=placed,
        width=width,
        height=height,
        families=tuple(families),
    )


def legend_lines(diagram: DecayDiagram) -> list[tuple[str, str]]:
    """(colour, words) for every family the diagram actually drew.

    Derived from the diagram rather than listing all five: a legend
    naming decays that are not on screen invites the reader to hunt for
    them. Carbon-14's chain would otherwise advertise cluster emission.
    """
    return [(FAMILY_COLOUR[f], FAMILY_WORDS[f]) for f in diagram.families]


FAMILY_WORDS: dict[str, str] = {
    "alpha": "alpha",
    "beta_minus": "beta-",
    "beta_plus": "beta+ / electron capture",
    "cluster": "cluster emission",
    "other": "other (nucleon, delayed)",
    "isomeric": "isomeric transition",
}


def edge_weight(branching: float | None) -> tuple[float, float]:
    """(stroke width, opacity) for one branching ratio."""
    if branching is None:
        return UNMEASURED_WEIGHT
    for threshold, width, opacity in BRANCHING_WEIGHTS:
        if branching >= threshold:
            return width, opacity
    return BRANCHING_WEIGHTS[-1][1], BRANCHING_WEIGHTS[-1][2]


def _edge_svg(start, end, edge, family: str) -> str:
    colour = FAMILY_COLOUR[family]
    x1, y1 = start
    x2, y2 = end
    width, opacity = edge_weight(edge.branching)
    body = (
        f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}" '
        f'stroke="{colour}" stroke-width="{_n(width)}" opacity="{_n(opacity)}"/>'
    )
    text = ""
    readable = edge.branching is None or edge.branching >= 1e-4
    if readable and (edge.branching is None or edge.branching < LABEL_BRANCHING_BELOW):
        label = format_branching(edge.branching, edge.qualifier)
        if label:
            text = (
                f'<text x="{_n((x1 + x2) / 2)}" '
                f'y="{_n(_baseline((y1 + y2) / 2, 8.0))}" text-anchor="middle" '
                f'fill="{colour}" font-family="Arial" font-size="8" '
                f'>{_escape(label)}</text>'
            )
    return body + text


def _node_svg(node: PlacedNode, half_life: str, leaf_reason: str) -> str:
    fill = _NODE_FILL
    if node.is_stable:
        fill = _STABLE_FILL
    elif node.is_root:
        fill = _ROOT_FILL
    elif leaf_reason == OFF_TABLE:
        fill = _OFF_TABLE_FILL
    stroke_width = 2.4 if node.is_root else 1.0

    centre_x = node.x + node.width / 2
    parts = [
        f'<rect x="{_n(node.x)}" y="{_n(node.y)}" width="{_n(node.width)}" '
        f'height="{_n(node.height)}" rx="3" fill="{fill}" stroke="{_STROKE}" '
        f'stroke-width="{_n(stroke_width)}"/>',
        f'<text x="{_n(centre_x)}" y="{_n(_baseline(node.y + 13, 11.0))}" '
        f'text-anchor="middle" font-family="Arial" font-size="11" '
        f'fill="#111111">{_escape(node.name)}</text>',
        f'<text x="{_n(centre_x)}" y="{_n(_baseline(node.y + 27, 9.0))}" '
        f'text-anchor="middle" font-family="Arial" font-size="9" '
        f'fill="#444444">{_escape(half_life)}</text>',
    ]
    # **A LEAF SAYS WHY IT IS ONE.** A chain that simply stops reads as a
    # rendering bug; "SF" and the combined-cluster modes genuinely have no
    # single daughter, and a nuclide the table does not carry is a limit
    # of the data rather than of the physics.
    if leaf_reason in (UNFOLLOWABLE_MODE, OFF_TABLE):
        words = "fissions" if leaf_reason == UNFOLLOWABLE_MODE else "not in table"
        parts.append(
            f'<text x="{_n(centre_x)}" y="{_n(_baseline(node.y + node.height + 7, 8.0))}" '
            f'text-anchor="middle" font-family="Arial" font-size="8" '
            f'fill="#7f8c8d">{_escape(words)}</text>'
        )
    return "".join(parts)


def _baseline(centre: float, font_size: float) -> float:
    """See `lewis_svg.BASELINE_SHIFT` -- Qt ignores `dominant-baseline`.

    Imported rather than restated, because the value was measured once
    and a second copy is a second thing to be wrong.
    """
    return centre + BASELINE_SHIFT * font_size


def _n(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
