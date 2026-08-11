"""The Lewis renderer, on diagrams built by hand.

**NO RDKit ANYWHERE IN THIS FILE.** Every fixture is three dataclasses, so
a renderer regression cannot masquerade as a chemistry regression -- which
is the entire reason the model exists as a separate layer.

The assertions are STRUCTURAL rather than visual. A screenshot can look
entirely plausible while carrying the wrong number of electrons, and this
is a diagram whose only job is to carry the right number.
"""

from __future__ import annotations

import math
import re

import pytest

from openchem.chem.electron_layout import violations
from openchem.chem.lewis_diagram import (
    Atom,
    BondPairs,
    Known,
    LewisDiagram,
    Region,
    Status,
    Unknown,
)
from openchem.chem.lewis_svg import BASELINE_SHIFT, BOND_LENGTH, Rendered, render

GROUP = {"H": 1, "C": 4, "N": 5, "O": 6, "S": 6}


def text_centre(svg: str, css_class: str):
    """Where a text element is drawn, NOT its `y` attribute.

    They differ, and asserting on the raw attribute is how these tests
    would silently start measuring the wrong thing. SVG positions text by
    a baseline, so the renderer writes `centre + BASELINE_SHIFT * font`;
    this reads that back out. See `lewis_svg.BASELINE_SHIFT` for why the
    shift is in `y` at all rather than in `dominant-baseline`.
    """
    match = re.search(
        rf'class="{css_class}" x="(-?[\d.]+)" y="(-?[\d.]+)"[^>]*?'
        rf'font-size="(-?[\d.]+)"',
        svg,
    )
    assert match, f"no {css_class} text in {svg[:200]}"
    x, y, font = (float(match.group(i)) for i in (1, 2, 3))
    return x, y - BASELINE_SHIFT * font


def _atom(index, symbol, lone_pairs, x, y, charge=0):
    return Atom(
        index=index,
        symbol=symbol,
        x=x,
        y=y,
        lone_pairs=lone_pairs if isinstance(lone_pairs, (Known, Unknown)) else Known(lone_pairs),
        valence_electrons=GROUP[symbol],
        formal_charge=charge,
    )


def water():
    """Bent, as it is drawn: oxygen at the origin, hydrogens below."""
    return LewisDiagram(
        status=Status.SUPPORTED,
        atoms=(
            _atom(0, "O", 2, 0.0, 0.0),
            _atom(1, "H", 0, -BOND_LENGTH, BOND_LENGTH * 0.6),
            _atom(2, "H", 0, BOND_LENGTH, BOND_LENGTH * 0.6),
        ),
        bond_pairs=(BondPairs(0, 1, Known(1)), BondPairs(0, 2, Known(1))),
    )


def carbon_dioxide():
    """Linear, and both bonds DOUBLE -- the case where one connection
    carries two pairs and must draw four dots in two columns."""
    return LewisDiagram(
        status=Status.SUPPORTED,
        atoms=(
            _atom(0, "C", 0, 0.0, 0.0),
            _atom(1, "O", 2, -BOND_LENGTH, 0.0),
            _atom(2, "O", 2, BOND_LENGTH, 0.0),
        ),
        bond_pairs=(BondPairs(0, 1, Known(2)), BondPairs(0, 2, Known(2))),
    )


def benzene():
    """A hexagon with a six-electron ring region and no double bonds."""
    atoms = []
    bonds = []
    for i in range(6):
        angle = math.radians(60 * i)
        atoms.append(_atom(i, "C", 0, BOND_LENGTH * math.cos(angle), BOND_LENGTH * math.sin(angle)))
    for i in range(6):
        bonds.append(BondPairs(i, (i + 1) % 6, Known(1)))
    return LewisDiagram(
        status=Status.SUPPORTED,
        atoms=tuple(atoms),
        bond_pairs=tuple(bonds),
        regions=(Region(tuple(range(6)), Known(6), is_ring=True),),
    )


def _svg(diagram) -> str:
    return render(diagram).svg


def _count(svg: str, klass: str) -> int:
    return len(re.findall(rf'class="{klass}"', svg))


# --- the counts, which are the whole point -----------------------------------


def test_water_draws_two_bonding_pairs_and_two_lone_pairs():
    """Four bonding dots and four lone-pair dots. A picture with three of
    either is a different molecule."""
    svg = _svg(water())

    assert _count(svg, "bond-pair") == 4, svg
    assert _count(svg, "lone-pair") == 4, svg
    assert _count(svg, "atom") == 3


def test_a_DOUBLE_bond_draws_two_pairs_not_one():
    """Carbon dioxide: eight bonding dots, not four. The commonest way to
    lose electrons silently is to draw one pair per CONNECTION rather than
    per PAIR."""
    svg = _svg(carbon_dioxide())

    assert _count(svg, "bond-pair") == 8, svg
    assert _count(svg, "lone-pair") == 8, svg


def test_benzene_draws_a_REGION_and_no_double_bonds():
    """Six single-pair ring bonds and one dashed circle. Three doubles and
    three singles would be a Kekule structure the molecule does not
    assert, and it would be visible as twelve extra dots."""
    svg = _svg(benzene())

    assert _count(svg, "bond-pair") == 12, "six ring bonds, one pair each"
    assert _count(svg, "region") == 1
    assert "6 e" in svg
    assert 'stroke-dasharray' in svg


def test_a_region_whose_count_is_unknown_says_so_rather_than_zero():
    """Pyrrole. The ring is delocalised and the number is not
    determinable, and "0 e-" would be a lie.

    The marker is deliberately SHORT -- "? e−" rather than a sentence --
    because "e− not determined" is wider than a five-membered ring and
    was drawn straight across pyrrole's own structure. The reason lives
    in the dialog's analysis panel, which has room for it.
    """
    diagram = LewisDiagram(
        status=Status.SUPPORTED,
        atoms=tuple(
            _atom(i, "C", 0, BOND_LENGTH * math.cos(math.radians(72 * i)),
                  BOND_LENGTH * math.sin(math.radians(72 * i)))
            for i in range(5)
        ),
        bond_pairs=tuple(BondPairs(i, (i + 1) % 5, Known(1)) for i in range(5)),
        regions=(Region(tuple(range(5)), Unknown("a lone pair completes it"), is_ring=True),),
    )

    svg = _svg(diagram)

    assert "? e" in svg
    assert "0 e" not in svg


# --- shape, not colour --------------------------------------------------------


def test_the_three_things_differ_by_SHAPE_not_only_colour():
    """Greyscale, printing, a pasted screenshot, a colour-blind reader.

    A localised pair is a filled dot, a region is a DASHED outline, an
    abstained bond is a SOLID line. Strip every colour from the output and
    all three are still distinguishable.
    """
    diagram = LewisDiagram(
        status=Status.SUPPORTED_WITH_ABSTENTIONS,
        atoms=(
            _atom(0, "S", 0, 0.0, 0.0),
            _atom(1, "O", 2, BOND_LENGTH, 0.0),
            _atom(2, "O", 2, 0.0, BOND_LENGTH),
        ),
        bond_pairs=(
            BondPairs(0, 1, Known(1)),
            BondPairs(0, 2, Unknown("an expanded octet is contested")),
        ),
        regions=(Region((0, 1), Known(2), is_ring=False),),
    )

    svg = _svg(diagram)
    without_colour = re.sub(r'(fill|stroke)="#[0-9a-f]{3,6}"', "", svg)

    assert _count(without_colour, "bond-pair") == 2, "the localised pair"
    assert "stroke-dasharray" in without_colour, "the region is dashed"
    assert _count(without_colour, "abstained") == 1, "the abstained bond is a line"
    assert "<line" in without_colour and "<circle" in without_colour


def test_an_abstained_bond_is_the_only_line_in_the_picture():
    """Which is what makes a line READ as "not represented as electrons"
    rather than as one bond among the dots."""
    plain = _svg(water())
    assert "<line" not in plain, "a fully localised molecule has no lines at all"


# --- geometry never drops an electron ----------------------------------------


def test_an_unplaceable_lone_pair_is_REPORTED_not_silently_dropped():
    """A quietly missing dot is a wrong Lewis structure that looks like a
    right one, so the renderer names the atom instead of drawing fewer.

    **TEN PAIRS IS NOT CHEMISTRY, and that is the finding.** Slots are
    kept 40 degrees apart, so nine fit around an atom and real chemistry
    never asks for more than four -- a halide's three, a chloride's four.
    The first version of this test used six and passed trivially, because
    six fit. The reporting path is a safety net that ordinary input does
    not reach, and the only way to test a safety net is to jump into it.
    """
    crowded = LewisDiagram(
        status=Status.SUPPORTED,
        atoms=(_atom(0, "O", 10, 0.0, 0.0),),
    )

    result = render(crowded)

    assert not result.complete
    assert result.unplaceable, "the renderer dropped pairs without saying so"
    assert "O0" in result.unplaceable[0]
    # And nothing was drawn for that atom rather than a partial set.
    assert _count(result.svg, "lone-pair") == 0


def test_the_realistic_crowding_cases_all_still_fit():
    """The other side of it: a chloride's four pairs and a halide's three
    place cleanly, so the safety net above is not quietly firing on
    ordinary molecules."""
    for pairs in (1, 2, 3, 4):
        diagram = LewisDiagram(
            status=Status.SUPPORTED,
            atoms=(_atom(0, "O", pairs, 0.0, 0.0), _atom(1, "H", 0, BOND_LENGTH, 0.0)),
            bond_pairs=(BondPairs(0, 1, Known(1)),),
        )
        result = render(diagram)
        assert result.complete, (pairs, result.unplaceable)
        assert _count(result.svg, "lone-pair") == 2 * pairs


def test_a_placeable_diagram_reports_nothing_unplaceable():
    """The control: without it the test above passes on a renderer that
    calls everything unplaceable."""
    assert render(water()).complete
    assert render(benzene()).complete
    assert render(carbon_dioxide()).complete


def test_no_lone_pair_dot_lands_inside_an_atom_label():
    """Judged by `chem/electron_layout.violations`, the same checker the
    canvas overlay is graded by -- one judge for both renderers."""
    from openchem.chem.electron_layout import Box
    from openchem.chem.lewis_svg import CHARACTER_HALF_WIDTH, LABEL_HALF_HEIGHT

    diagram = water()
    svg = render(diagram).svg
    dots = [
        (float(x), float(y))
        for x, y in re.findall(
            r'class="lone-pair" cx="(-?[\d.]+)" cy="(-?[\d.]+)"', svg
        )
    ]
    oxygen = diagram.atoms[0]
    half_width = len(oxygen.label) * CHARACTER_HALF_WIDTH * BOND_LENGTH
    half_height = LABEL_HALF_HEIGHT * BOND_LENGTH
    box = Box(
        oxygen.x - half_width, oxygen.y - half_height,
        oxygen.x + half_width, oxygen.y + half_height,
    )

    breaches = violations(
        dots,
        (oxygen.x, oxygen.y),
        [
            math.degrees(math.atan2(a.y - oxygen.y, a.x - oxygen.x))
            for a in diagram.atoms[1:]
        ],
        box,
        BOND_LENGTH,
        expected_pairs=2,
    )

    assert breaches == [], breaches


# --- determinism and robustness ----------------------------------------------


def test_the_same_diagram_renders_byte_identically():
    """Two runs, one string. A renderer that reorders its output makes
    every diff unreadable and every screenshot comparison a coin flip."""
    assert _svg(benzene()) == _svg(benzene())
    assert _svg(water()) == _svg(water())


def test_an_empty_diagram_renders_a_message_not_malformed_svg():
    empty = LewisDiagram(status=Status.CHEMISTRY_REFUSED, reason="an unpaired electron")

    svg = _svg(empty)

    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "unpaired electron" in svg


def test_a_label_with_a_charge_is_escaped_and_drawn():
    diagram = LewisDiagram(
        status=Status.SUPPORTED,
        atoms=(_atom(0, "N", 0, 0.0, 0.0, charge=1),),
    )

    svg = _svg(diagram)

    assert ">N+<" in svg


def test_the_renderer_imports_no_rdkit_and_no_qt():
    """The other half of the split, asserted the same way as the model's:
    an AST walk, which sees a lazy import inside a function."""
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "src/openchem/chem/lewis_svg.py"
    ).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    offenders = [n for n in imported if n.split(".")[0] in {"rdkit", "PySide6", "PyQt5", "PyQt6"}]
    assert not offenders, f"lewis_svg.py imports {offenders}"
    assert imported


def test_the_viewbox_contains_every_atom():
    """A diagram drawn outside its own frame is invisible, and nothing
    else would notice."""
    svg = _svg(benzene())
    left, top, width, height = (float(v) for v in re.search(
        r'viewBox="(-?[\d.]+) (-?[\d.]+) ([\d.]+) ([\d.]+)"', svg
    ).groups())

    for atom in benzene().atoms:
        assert left <= atom.x <= left + width, atom
        assert top <= atom.y <= top + height, atom


def test_a_lone_pair_goes_on_the_side_AWAY_from_the_bonds():
    """**Caught by looking at the picture, and it broke no rule.**

    Scoring bond clearance and slot spread as a SUM put one of water's
    lone pairs directly BELOW the oxygen, between the two hydrogens: 180
    degrees of spread outweighed the lost clearance, every rule was
    satisfied, and the diagram suggested electron density exactly where
    the hydrogens are.

    Clearance is now compared first and spread only breaks ties, so both
    pairs sit on the far side -- which is what VSEPR says and what a
    textbook draws.
    """
    diagram = water()
    svg = render(diagram).svg
    dots = [
        (float(x), float(y))
        for x, y in re.findall(r'class="lone-pair" cx="(-?[\d.]+)" cy="(-?[\d.]+)"', svg)
    ]
    oxygen = diagram.atoms[0]

    assert len(dots) == 4
    # The hydrogens are BELOW the oxygen (+y in SVG), so every lone-pair
    # dot must be above it.
    assert all(a.y > oxygen.y for a in diagram.atoms[1:]), "fixture moved"
    assert all(y < oxygen.y for _, y in dots), dots


def test_the_scoring_is_lexicographic_rather_than_a_weighted_sum():
    """Asserted on the behaviour that distinguishes them, because a sum
    with the right coefficients would pass the test above by luck.

    Carbon dioxide's oxygen has ONE bond, so the clear half-plane is
    large: both its pairs must clear that bond by more than the 40-degree
    minimum separation they keep from each other. A spread-dominated
    score would push them to 180 degrees apart, which puts one straight
    through the bond.
    """
    diagram = carbon_dioxide()
    svg = render(diagram).svg
    dots = [
        (float(x), float(y))
        for x, y in re.findall(r'class="lone-pair" cx="(-?[\d.]+)" cy="(-?[\d.]+)"', svg)
    ]
    left_oxygen = diagram.atoms[1]
    carbon = diagram.atoms[0]
    bond_bearing = math.degrees(
        math.atan2(carbon.y - left_oxygen.y, carbon.x - left_oxygen.x)
    )
    near = [
        d for d in dots if math.dist(d, (left_oxygen.x, left_oxygen.y)) < BOND_LENGTH * 0.6
    ]
    assert near, dots
    for x, y in near:
        bearing = math.degrees(math.atan2(y - left_oxygen.y, x - left_oxygen.x))
        gap = abs((bearing - bond_bearing + 180) % 360 - 180)
        assert gap > 40.0, f"a lone pair is {gap:.0f} deg from the bond"


def test_a_dot_is_kept_out_of_a_WIDE_label_even_when_that_is_the_clear_side():
    """**Water could not catch this**, and a mutation proved it.

    Water's hydrogens are below, so the clearest direction is straight up
    -- which is outside the label anyway. Deleting the label filter
    entirely changed nothing about water, and the guard that names label
    collisions passed.

    This fixture forces the collision: a wide label with bonds ABOVE and
    BELOW, so the only directions clear of the bonds run horizontally,
    straight through the text. Either the renderer avoids the label or it
    reports the atom as unplaceable; what it must not do is put a dot on
    a letter.
    """
    from openchem.chem.lewis_svg import CHARACTER_HALF_WIDTH, LABEL_HALF_HEIGHT

    centre = _atom(0, "N", 1, 0.0, 0.0, charge=2)
    diagram = LewisDiagram(
        status=Status.SUPPORTED,
        atoms=(
            centre,
            _atom(1, "C", 0, 0.0, -BOND_LENGTH),
            _atom(2, "C", 0, 0.0, BOND_LENGTH),
        ),
        bond_pairs=(BondPairs(0, 1, Known(1)), BondPairs(0, 2, Known(1))),
    )
    assert len(centre.label) >= 3, "the label must be wide enough to be in the way"

    result = render(diagram)
    dots = [
        (float(x), float(y))
        for x, y in re.findall(r'class="lone-pair" cx="(-?[\d.]+)" cy="(-?[\d.]+)"', result.svg)
    ]

    half_width = len(centre.label) * CHARACTER_HALF_WIDTH * BOND_LENGTH
    half_height = LABEL_HALF_HEIGHT * BOND_LENGTH
    for x, y in dots:
        inside = abs(x - centre.x) <= half_width and abs(y - centre.y) <= half_height
        assert not inside, f"a dot at ({x}, {y}) is inside the label box"


def test_every_coordinate_is_ROUNDED_so_the_output_cannot_drift():
    """The determinism test above compares two renders in one process,
    which agree even with full float precision -- so a mutation that
    stopped rounding survived it.

    Rounding is what makes the output stable across machines and across
    a float that arrives as 59.99999999999999. Asserted on the emitted
    text, which is the thing that has to be stable.
    """
    svg = _svg(benzene())
    numbers = re.findall(r'(?:cx|cy|x1|y1|x2|y2|r|x|y)="(-?[\d.]+)"', svg)

    assert numbers, "nothing numeric in the output"
    for value in numbers:
        _, _, fraction = value.partition(".")
        assert len(fraction) <= 2, f"{value} carries more precision than is emitted"


def test_an_open_regions_label_is_pushed_CLEAR_of_its_atoms():
    """**Acetate's centroid lands on the carbon**, so the label was drawn
    straight through it. A ring's centroid is empty by construction and
    keeps the centre; an open system is pushed out to whichever direction
    has the most room.
    """
    open_system = LewisDiagram(
        status=Status.SUPPORTED,
        atoms=(
            _atom(0, "C", 0, 0.0, 0.0),
            _atom(1, "O", 2, -BOND_LENGTH, BOND_LENGTH),
            _atom(2, "O", 3, BOND_LENGTH, BOND_LENGTH, charge=-1),
        ),
        bond_pairs=(BondPairs(0, 1, Known(1)), BondPairs(0, 2, Known(1))),
        regions=(Region((0, 1, 2), Known(2), is_ring=False, bonds=((0, 1), (0, 2))),),
    )

    svg = render(open_system).svg
    lx, ly = text_centre(svg, "region-label")

    for atom in open_system.atoms:
        assert math.dist((lx, ly), (atom.x, atom.y)) > BOND_LENGTH * 0.3, (
            f"the label sits on {atom.label}{atom.index}"
        )


def test_a_RING_keeps_its_label_in_the_middle():
    """The control for the test above -- without it, a renderer that
    always pushed the label out would pass, and benzene's count belongs
    inside its circle."""
    svg = render(benzene()).svg
    lx, ly = text_centre(svg, "region-label")

    assert abs(lx) < 1.0 and abs(ly) < 1.0, "benzene's label left the centre of its ring"
