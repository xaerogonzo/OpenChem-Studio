"""Where a lone pair may be drawn, as rules rather than as a placement.

**THIS MODULE DOES NOT PLACE ANYTHING, AND THAT IS THE POINT.** The
placement lives in `tools/ketcher-host/src/main.jsx`, because only the
page knows the live viewport, the zoom, the label geometry and the current
atom positions. An earlier design had this module compute the same
placement in Python and a test require identical answers — two
implementations that have to stay mathematically identical, and when they
disagree the test cannot say which one is *right*.

So this is the JUDGE. `violations()` takes the dots the JS actually
produced and reports which geometric rules they break, by name. One
implementation, one independent checker, and a failure that says
*"a dot is inside the label box"* rather than *"the two disagree"*.

**A PAIR IS THE SEMANTIC OBJECT; TWO DOTS ARE ITS RENDERING.** A halide
carries three pairs, not six annotations. Everything here is expressed per
pair, which is also what makes the joint slot search tractable and what
will let a future full-Lewis mode put a *bonding* pair on an edge instead
of on a vertex.

No RDKit and no Qt: this is arithmetic on numbers, the same discipline
`chem/camera_orientation.py` follows, so the rules can be tested without a
molecule or a browser.

**The constants are shared with the JS by a source check**, not by import
— `tests/test_ketcher_bundle_is_current.py` asserts each value appears in
`main.jsx`, the way it already asserts bridge method names. A constant
that drifts on one side is the kind of thing nothing else would notice.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Minimum angle between two of ONE atom's pair slots, in degrees. Below
#: this the two pairs read as a single smudge of four dots.
MIN_SLOT_SEPARATION_DEGREES = 40.0

#: How close a slot may come to a bond direction, in degrees. A pair drawn
#: along a bond is indistinguishable from a decoration on that bond.
MIN_BOND_CLEARANCE_DEGREES = 25.0

#: Distance from the atom centre to a pair's dots, as a fraction of the
#: bond length. Far enough to clear a one-character label, close enough to
#: still read as belonging to this atom rather than to the space between
#: two.
SLOT_RADIUS_FRACTION = 0.33

#: Half the gap between the two dots of one pair, as a fraction of the
#: bond length.
PAIR_HALF_GAP_FRACTION = 0.055

#: Padding added around a label's measured box before it is treated as an
#: obstacle, in CSS pixels.
LABEL_PADDING_PX = 2.0


@dataclass(frozen=True)
class Box:
    """An axis-aligned label box in the same space as the dots."""

    left: float
    top: float
    right: float
    bottom: float

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom

    def padded(self, padding: float = LABEL_PADDING_PX) -> Box:
        return Box(
            self.left - padding,
            self.top - padding,
            self.right + padding,
            self.bottom + padding,
        )


def _angle(cx: float, cy: float, x: float, y: float) -> float:
    return math.degrees(math.atan2(y - cy, x - cx))


def _separation(a: float, b: float) -> float:
    """The smaller angle between two bearings, in degrees, always >= 0."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def pair_bearings(
    dots: list[tuple[float, float]], centre: tuple[float, float]
) -> list[float]:
    """The direction of each PAIR, from its two dots.

    Dots arrive as a flat list — the renderer draws circles, not pairs —
    so consecutive dots are re-associated here. Their midpoint is the slot
    direction, which is the quantity every rule below is about.
    """
    bearings = []
    for index in range(0, len(dots) - 1, 2):
        (x1, y1), (x2, y2) = dots[index], dots[index + 1]
        bearings.append(_angle(centre[0], centre[1], (x1 + x2) / 2, (y1 + y2) / 2))
    return bearings


def violations(
    dots: list[tuple[float, float]],
    centre: tuple[float, float],
    bond_directions: list[float],
    label_box: Box | None,
    bond_length: float,
    expected_pairs: int,
) -> list[str]:
    """Every rule these dots break, named. Empty means the drawing is sound.

    Reports ALL breaches rather than the first, because a placement that
    is wrong is usually wrong in more than one way and fixing them one per
    test run is how a geometry bug takes an afternoon.
    """
    breaches: list[str] = []

    if len(dots) != 2 * expected_pairs:
        breaches.append(
            f"{len(dots)} dots for {expected_pairs} pair(s); expected {2 * expected_pairs}"
        )
        return breaches
    if not dots:
        return breaches

    bearings = pair_bearings(dots, centre)

    for index, bearing in enumerate(bearings):
        for bond in bond_directions:
            gap = _separation(bearing, bond)
            if gap < MIN_BOND_CLEARANCE_DEGREES:
                breaches.append(
                    f"pair {index} is {gap:.1f} deg from a bond "
                    f"(minimum {MIN_BOND_CLEARANCE_DEGREES})"
                )

    for i in range(len(bearings)):
        for j in range(i + 1, len(bearings)):
            gap = _separation(bearings[i], bearings[j])
            if gap < MIN_SLOT_SEPARATION_DEGREES:
                breaches.append(
                    f"pairs {i} and {j} are {gap:.1f} deg apart "
                    f"(minimum {MIN_SLOT_SEPARATION_DEGREES})"
                )

    if label_box is not None:
        padded = label_box.padded()
        for index, (x, y) in enumerate(dots):
            if padded.contains(x, y):
                breaches.append(f"dot {index} is inside the atom's label box")

    # The dots must sit at a plausible distance: close in they collide with
    # the label, far out they read as belonging to the bond or to nothing.
    for index, (x, y) in enumerate(dots):
        distance = math.dist((x, y), centre)
        fraction = distance / bond_length if bond_length else 0.0
        if not 0.15 <= fraction <= 0.60:
            breaches.append(
                f"dot {index} sits at {fraction:.2f} bond lengths from the atom "
                f"(expected 0.15-0.60)"
            )

    return breaches


def slot_candidates(step_degrees: float = 10.0) -> list[float]:
    """The bearings a slot search may choose from.

    Exposed so the checker's tests and the JS agree on the resolution
    rather than each picking one. A coarse ring is deliberate: it makes the
    joint search over combinations cheap, and it is the thing that keeps
    two nearly-equivalent directions from trading places on a rounding
    difference.
    """
    count = int(round(360.0 / step_degrees))
    return [(-180.0 + index * step_degrees) for index in range(count)]
