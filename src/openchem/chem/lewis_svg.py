"""A Lewis diagram as SVG. No RDKit, no Qt, no chemistry.

Takes a `LewisDiagram` and emits a string. **It never asks a chemistry
question** -- every count it draws was decided by the builder, so a
placement bug cannot be mistaken for a chemistry bug and the whole
renderer is testable from three hand-written dataclasses.

**WHY WE EMIT THIS OURSELVES.** A Lewis structure REPLACES each bond line
with two dots, and RDKit's drawer will not omit bond lines -- measured,
`bondLineWidth = 0` still emits every bond path. Post-processing its
output would mean parsing generated markup. This project already draws
three of its own charts by hand, and an SVG string is assertable in a test
where a `QPainter` surface is not.

**LOCALISED PAIRS, DELOCALISED REGIONS AND ABSTENTIONS MUST BE TELLABLE
APART WITHOUT COLOUR** -- greyscale, printing, a screenshot pasted into a
document, a colour-blind reader. So the vocabulary is shape and line
style, and colour only reinforces it:

    localised pair       two filled dots
    delocalised region   a dashed outline, labelled with its electrons
    abstained bond       a plain solid line, and a stated reason

**GEOMETRY NEVER DROPS AN ELECTRON.** If a pair cannot be placed clear of
the labels the renderer says so -- `unplaceable` comes back naming the
atoms -- and the caller turns that into `RENDERING_FAILED`. A quietly
missing dot would be a wrong Lewis structure that looks like a right one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from openchem.chem.electron_layout import (
    MIN_SLOT_SEPARATION_DEGREES,
    PAIR_HALF_GAP_FRACTION,
    SLOT_RADIUS_FRACTION,
    Box,
)
from openchem.chem.lewis_diagram import Known, LewisDiagram, Unknown

#: One bond length, in SVG units. Everything else is a fraction of it, so
#: the diagram scales by changing this one number.
BOND_LENGTH = 60.0

#: Half the width of a character, and half a line's height, as fractions
#: of the bond length. A deliberate over-estimate on the horizontal, for
#: the reason the canvas overlay learned the hard way: a label box that
#: under-covers puts a dot through a letter, and the judge cannot see it
#: because it was handed the same box.
CHARACTER_HALF_WIDTH = 0.11
LABEL_HALF_HEIGHT = 0.19

#: Where a bonding pair sits between two atoms, as a fraction of the way
#: along. Not the midpoint: a pair drawn dead centre between two labelled
#: atoms reads as belonging to neither.
BOND_PAIR_POSITION = 0.5

#: The gap between the two dots of a bonding pair, across the bond.
BOND_PAIR_GAP = 0.075

DOT_RADIUS = 0.035
FONT_SIZE = 0.30
REGION_PADDING = 0.30

#: How far BELOW the anchor a label's baseline goes, in ems, so the glyph
#: is centred on the point rather than sitting above it.
#:
#: **`dominant-baseline` IS IGNORED BY Qt's SVG RENDERER, and so is `dy`.**
#: This is the label-box failure the canvas overlay already recorded, in a
#: new renderer: the checker centres its box on the atom, the page drew
#: the glyph half an em higher, and both agreed the dot was clear.
#: Measured at scale 60 (font 18) with the attribute in place -- label ink
#: 74..87 against a box of 78.6..101.4, so the glyph poked 4.6 px out of
#: the top while the bottom 14 px of the box was empty.
#:
#: Only `x` and `y` move a glyph in both renderers, so the shift is
#: written into `y`. **This changes nothing in a browser**: measured in
#: Chromium via `getBBox`, `dominant-baseline="central"` shifts a text
#: element by exactly +6.00 px at font-size 18 -- +0.333 em -- which is
#: (ascent - descent)/2 for Arial and is what this constant is. An
#: exported SVG is therefore byte-equivalent in placement to the standards
#: form, and the dialog's own preview finally agrees with the checker.
BASELINE_SHIFT = 1.0 / 3.0


@dataclass(frozen=True)
class Rendered:
    """The SVG, and what it could not do.

    `unplaceable` is the load-bearing half. An empty tuple means every
    electron the diagram claims is on the page.
    """

    svg: str
    unplaceable: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.unplaceable


def _label_box(atom, scale: float) -> Box:
    """The space an atom's text occupies, centred on it.

    Centred is right HERE and was wrong on the canvas: this renderer
    writes the label centred on the atom, because a Lewis structure has no
    implicit hydrogens hanging off one side. The canvas's asymmetry came
    from Ketcher's own convention, not from labels in general.
    """
    half_width = max(len(atom.label), 1) * CHARACTER_HALF_WIDTH * scale
    half_height = LABEL_HALF_HEIGHT * scale
    return Box(atom.x - half_width, atom.y - half_height, atom.x + half_width, atom.y + half_height)


def _neighbour_bearings(diagram: LewisDiagram, index: int) -> list[float]:
    positions = {atom.index: (atom.x, atom.y) for atom in diagram.atoms}
    here = positions.get(index)
    bearings = []
    for bond in diagram.bond_pairs:
        other = bond.end if bond.begin == index else bond.begin if bond.end == index else None
        if other is None or other not in positions or here is None:
            continue
        dx = positions[other][0] - here[0]
        dy = positions[other][1] - here[1]
        bearings.append(math.degrees(math.atan2(dy, dx)))
    return bearings


def _separation(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _lone_pair_slots(diagram: LewisDiagram, atom, scale: float, count: int):
    """Directions for an atom's lone pairs, or None if they will not fit.

    The same discipline as the canvas overlay: candidates scored against
    the bonds, chosen as a SET rather than greedily so two nearly-equal
    directions cannot trade places, with a fixed tie-break.
    """
    if count <= 0:
        return []
    bonds = _neighbour_bearings(diagram, atom.index)
    box = _label_box(atom, scale)
    candidates = [
        bearing
        for bearing in range(-180, 180, 15)
        if not _slot_hits_label(bearing, atom, box, scale)
    ]
    if len(candidates) < count:
        return None

    best = None
    best_score = (-math.inf, -math.inf)
    chosen: list[float] = []

    def score(slots):
        """**CLEARANCE FIRST, SPREAD ONLY AS A TIE-BREAK**, and this is
        chemistry rather than taste.

        A lone pair belongs on the side of the atom AWAY from its bonds --
        that is what VSEPR says and what a textbook draws. Scoring
        clearance and spread as a SUM gets water visibly wrong: with the
        hydrogens below, the best-scoring set is one pair above and one
        BELOW, straight between the two H atoms, because 180 degrees of
        spread outweighs the loss of clearance. It breaks no rule and it
        suggests electron density exactly where the hydrogens are.

        Compared as a tuple, so no weighting has to be invented: the
        worst clearance in the set decides, and spread separates
        arrangements that are equally clear. Water then puts both pairs on
        the far side, which is the picture everyone has seen.
        """
        clearance = min(
            (min((_separation(s, b) for b in bonds), default=180.0) for s in slots),
            default=180.0,
        )
        spread = min(
            (_separation(a, b) for i, a in enumerate(slots) for b in slots[i + 1 :]),
            default=180.0,
        )
        return (clearance, spread)

    def walk(start):
        nonlocal best, best_score
        if len(chosen) == count:
            value = score(chosen)
            # Strictly greater, over candidates walked in ascending
            # order, so an exact tie keeps the same arrangement every
            # time rather than swapping on a rounding difference.
            if value > best_score:
                best_score = value
                best = list(chosen)
            return
        for i in range(start, len(candidates)):
            bearing = float(candidates[i])
            if any(_separation(bearing, s) < MIN_SLOT_SEPARATION_DEGREES for s in chosen):
                continue
            chosen.append(bearing)
            walk(i + 1)
            chosen.pop()

    walk(0)
    return best


def _slot_hits_label(bearing: float, atom, box: Box, scale: float) -> bool:
    for x, y in _pair_dots(atom.x, atom.y, float(bearing), scale):
        if box.left <= x <= box.right and box.top <= y <= box.bottom:
            return True
    return False


def _pair_dots(cx: float, cy: float, bearing: float, scale: float):
    radians = math.radians(bearing)
    x = cx + SLOT_RADIUS_FRACTION * scale * math.cos(radians)
    y = cy + SLOT_RADIUS_FRACTION * scale * math.sin(radians)
    px = -math.sin(radians) * PAIR_HALF_GAP_FRACTION * scale
    py = math.cos(radians) * PAIR_HALF_GAP_FRACTION * scale
    return [(x + px, y + py), (x - px, y - py)]


def _bond_pair_dots(ax, ay, bx, by, pairs: int, scale: float):
    """`pairs` pairs strung along a bond, offset across it.

    A double bond is two pairs side by side, which is what a textbook
    draws -- four dots in two columns, not four in a row.
    """
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    midx = ax + dx * BOND_PAIR_POSITION
    midy = ay + dy * BOND_PAIR_POSITION
    dots = []
    for slot in range(pairs):
        offset = (slot - (pairs - 1) / 2) * BOND_PAIR_GAP * scale * 2
        cx, cy = midx + nx * offset, midy + ny * offset
        gap = BOND_PAIR_GAP * scale
        dots.append((cx + ux * gap, cy + uy * gap))
        dots.append((cx - ux * gap, cy - uy * gap))
    return dots


def render(diagram: LewisDiagram, scale: float = BOND_LENGTH) -> Rendered:
    """The diagram as an SVG string.

    Deterministic: the same diagram gives byte-identical output, because
    everything is emitted in the order the model carries it and every
    number is rounded before it is written.
    """
    if not diagram.atoms:
        return Rendered(_empty_svg(diagram))

    xs = [atom.x for atom in diagram.atoms]
    ys = [atom.y for atom in diagram.atoms]
    margin = scale
    left, right = min(xs) - margin, max(xs) + margin
    top, bottom = min(ys) - margin, max(ys) + margin
    width, height = right - left, bottom - top

    body: list[str] = []
    unplaceable: list[str] = []
    positions = {atom.index: atom for atom in diagram.atoms}

    # Abstained bonds keep an ordinary line -- the one place a line
    # appears at all, which is what makes it read as "not represented as
    # electrons" rather than as a bond among dots.
    abstained = {
        (bond.begin, bond.end)
        for bond in diagram.bond_pairs
        if isinstance(bond.pairs, Unknown)
    }
    for begin, end in sorted(abstained):
        a, b = positions.get(begin), positions.get(end)
        if a is None or b is None:
            continue
        body.append(
            f'<line class="abstained" x1="{_n(a.x)}" y1="{_n(a.y)}" '
            f'x2="{_n(b.x)}" y2="{_n(b.y)}" stroke="#666" stroke-width="1.5"/>'
        )

    for region in diagram.regions:
        body.append(_region_shape(region, positions, scale))

    for bond in diagram.bond_pairs:
        if isinstance(bond.pairs, Unknown):
            continue
        a, b = positions.get(bond.begin), positions.get(bond.end)
        if a is None or b is None:
            continue
        for x, y in _bond_pair_dots(a.x, a.y, b.x, b.y, bond.pairs.value, scale):
            body.append(_dot(x, y, scale, "bond-pair"))

    for atom in diagram.atoms:
        if isinstance(atom.lone_pairs, Unknown):
            continue
        slots = _lone_pair_slots(diagram, atom, scale, atom.lone_pairs.value)
        if slots is None:
            unplaceable.append(f"{atom.label}{atom.index}")
            continue
        for bearing in slots:
            for x, y in _pair_dots(atom.x, atom.y, bearing, scale):
                body.append(_dot(x, y, scale, "lone-pair"))

    for atom in diagram.atoms:
        body.append(
            f'<text class="atom" x="{_n(atom.x)}" '
            f'y="{_n(_baseline(atom.y, FONT_SIZE * scale))}" '
            f'text-anchor="middle" '
            f'font-family="Arial" font-size="{_n(FONT_SIZE * scale)}">{_escape(atom.label)}</text>'
        )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{_n(left)} {_n(top)} {_n(width)} {_n(height)}" '
        f'width="{_n(width)}" height="{_n(height)}">'
        + "".join(body)
        + "</svg>"
    )
    return Rendered(svg, tuple(unplaceable))


def _region_shape(region, positions, scale: float) -> str:
    """A dashed outline plus its electron count.

    Dashed, not coloured: the difference between a localised pair and a
    delocalised system has to survive greyscale. A ring gets a circle, an
    open system an outline through its atoms.
    """
    points = [(positions[i].x, positions[i].y) for i in region.atom_indices if i in positions]
    if not points:
        return ""
    cx = sum(x for x, _ in points) / len(points)
    cy = sum(y for _, y in points) / len(points)
    # **SHORT ON THE DIAGRAM, FULL IN THE DETAILS.** "e− not determined"
    # is wider than a five-membered ring, so pyrrole's label ran straight
    # across its own structure. The reason lives in the dialog's analysis
    # panel, where there is room for a sentence.
    label = (
        f"{region.electrons.value} e−" if isinstance(region.electrons, Known) else "? e−"
    )
    label_x, label_y = _region_label_position(points, cx, cy, scale, region.is_ring)
    if region.is_ring and len(points) > 2:
        radius = max(math.dist((cx, cy), p) for p in points) - REGION_PADDING * scale
        radius = max(radius, 0.25 * scale)
        shape = (
            f'<circle class="region" cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(radius)}" '
            f'fill="none" stroke="#444" stroke-width="1.2" stroke-dasharray="4 3"/>'
        )
    else:
        path = " ".join(f"{_n(x)},{_n(y)}" for x, y in points)
        shape = (
            f'<polyline class="region" points="{path}" fill="none" stroke="#444" '
            f'stroke-width="1.2" stroke-dasharray="4 3"/>'
        )
    return shape + (
        f'<text class="region-label" x="{_n(label_x)}" '
        f'y="{_n(_baseline(label_y, 0.20 * scale))}" '
        f'text-anchor="middle" font-family="Arial" '
        f'font-size="{_n(0.20 * scale)}">{_escape(label)}</text>'
    )


def _region_label_position(points, cx: float, cy: float, scale: float, is_ring: bool):
    """Where a region's electron count goes.

    **A RING'S CENTRE IS EMPTY AND AN OPEN SYSTEM'S IS NOT.** Acetate's
    three atoms are O-C-O, so their centroid lands on the carbon and the
    label was drawn straight through it; benzene's lands in the middle of
    the ring, which is exactly where the label belongs.

    So a ring keeps the centre and an open system is pushed out along
    whichever direction has the most room -- sampled rather than derived,
    because the region can be any shape.
    """
    if is_ring and len(points) > 2:
        return cx, cy
    best = (cx, cy)
    best_clearance = -1.0
    for step in range(12):
        angle = math.radians(step * 30)
        x = cx + 0.65 * scale * math.cos(angle)
        y = cy + 0.65 * scale * math.sin(angle)
        clearance = min(math.dist((x, y), p) for p in points)
        if clearance > best_clearance:
            best_clearance = clearance
            best = (x, y)
    return best


def _dot(x: float, y: float, scale: float, kind: str) -> str:
    return (
        f'<circle class="{kind}" cx="{_n(x)}" cy="{_n(y)}" '
        f'r="{_n(DOT_RADIUS * scale)}" fill="#111"/>'
    )


def _empty_svg(diagram: LewisDiagram) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 60" '
        'width="200" height="60">'
        f'<text class="empty" x="100" y="{_n(_baseline(30, 12))}" '
        f'text-anchor="middle" font-family="Arial" font-size="12">'
        f"{_escape(diagram.summary())}</text></svg>"
    )


def _baseline(centre: float, font_size: float) -> float:
    """The `y` that puts a glyph's centre on `centre`, in BOTH renderers.

    See `BASELINE_SHIFT`. Written as its own function so there is exactly
    one place that knows text is not positioned by its middle, and so a
    mutation of it is caught everywhere at once.
    """
    return centre + BASELINE_SHIFT * font_size


def _n(value: float) -> str:
    """Rounded before it is written, so the output is byte-stable."""
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
