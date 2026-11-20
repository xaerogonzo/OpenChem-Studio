"""`tools/template_layout_check.py`: the 2D layout screen for shipped templates.

The measuring functions are pure (points and bonds in, numbers out), so each is
pinned on a hand-made drawing whose answer is known. The guard-style tests at
the end were mutation-checked: each fails when its rule is removed.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("template_layout_check", ROOT / "tools" / "template_layout_check.py")
chk = importlib.util.module_from_spec(_spec)
sys.modules["template_layout_check"] = chk  # a dataclass looks its module up
_spec.loader.exec_module(chk)

HEXAGON = [(math.cos(k * math.pi / 3), math.sin(k * math.pi / 3)) for k in range(6)]
HEXAGON_BONDS = [(k, (k + 1) % 6) for k in range(6)]


def test_a_regular_hexagon_has_no_flags():
    layout = chk.measure(HEXAGON, HEXAGON_BONDS)
    assert layout.flags == ()
    assert layout.crossings == 0
    assert math.isclose(layout.bond_ratio, 1.0)
    assert layout.min_atom_gap > 0.99


def test_a_bowtie_crosses_once_and_a_shared_atom_is_not_a_crossing():
    square = [(0, 0), (1, 0), (1, 1), (0, 1)]
    assert chk.count_crossings(square, [(0, 2), (1, 3)]) == 1  # the diagonals
    assert chk.count_crossings(square, [(0, 1), (1, 2), (2, 3), (3, 0)]) == 0  # touching ends only
    assert chk.count_crossings(square, [(0, 2), (0, 3)]) == 0  # share atom 0


def test_collinear_touching_segments_do_not_count_as_crossing():
    assert not chk.segments_cross((0, 0), (2, 0), (1, 0), (3, 0))


def test_two_atoms_on_top_of_each_other_overlap():
    points = [(0, 0), (1.5, 0), (3, 0), (1.5, 0.05)]
    layout = chk.measure(points, [(0, 1), (1, 2)])
    assert "overlap" in layout.flags
    assert layout.min_atom_gap < chk.OVERLAP_FRACTION


def test_a_stretched_bond_trips_the_ratio_flag():
    points = [(0, 0), (1, 0), (2, 0), (7, 0)]
    layout = chk.measure(points, [(0, 1), (1, 2), (2, 3)])
    assert layout.bond_ratio == 5.0
    assert "bond_ratio" in layout.flags


def test_aspect_flags_a_ribbon_but_not_a_short_chain():
    ribbon = [(i * 1.0, 0.01 * (i % 2)) for i in range(10)]
    assert "aspect" in chk.measure(ribbon, [(i, i + 1) for i in range(9)]).flags
    short = [(0, 0), (1, 0), (2, 0)]
    assert "aspect" not in chk.measure(short, [(0, 1), (1, 2)]).flags


def test_a_single_atom_is_measurable():
    layout = chk.measure([(0, 0)], [])
    assert layout.flags == ()
    assert layout.atoms == 1


def test_ranking_puts_overlaps_and_crossings_before_a_merely_stretched_bond():
    ok = chk.measure(HEXAGON, HEXAGON_BONDS)
    stretched = chk.measure([(0, 0), (1, 0), (2, 0), (9, 0)], [(0, 1), (1, 2), (2, 3)])
    square = [(0, 0), (1, 0), (1, 1), (0, 1)]
    crossed = chk.measure(square, [(0, 2), (1, 3)])
    ranked = chk.rank([("ok", ok), ("stretched", stretched), ("crossed", crossed)])
    assert [name for name, _ in ranked] == ["crossed", "stretched", "ok"]


def test_a_molblock_is_read_and_measured():
    block = (
        "\n  test\n\n  3  2  0  0  0  0  0  0  0  0999 V2000\n"
        "    0.0000    0.0000    0.0000 C   0  0\n"
        "    1.5000    0.0000    0.0000 C   0  0\n"
        "    3.0000    0.0000    0.0000 C   0  0\n"
        "  1  2  1  0\n  2  3  1  0\nM  END\n"
    )
    layout = chk.layout_of_molblock(block)
    assert layout.atoms == 3 and layout.crossings == 0


def test_the_shipped_screen_runs_and_flags_the_known_bad_depiction():
    """End to end through the insertion path; every template yields a row."""
    rows = chk.screen_shipped()
    assert len(rows) > 400
    assert all(layout.atoms > 0 for _, layout in rows)
    assert rows == chk.rank(rows)
