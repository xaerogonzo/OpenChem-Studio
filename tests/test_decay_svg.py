"""The decay chart: where a nuclide lands, and what a line's weight means."""

from __future__ import annotations

import pytest

from openchem.chem import nuclides as N
from openchem.chem.decay import decay_tree, mode_family
from openchem.chem.decay_svg import (
    BRANCHING_WEIGHTS,
    CELL_H,
    CELL_W,
    FAMILY_COLOUR,
    UNMEASURED_WEIGHT,
    edge_weight,
    legend_lines,
    render_decay_svg,
)


def _chart(z: int, a: int):
    return render_decay_svg(decay_tree(N.nuclide(z, a)))


def _node(diagram, name: str):
    return next(n for n in diagram.nodes if n.name == name)


# --- the layout -------------------------------------------------------------


def test_no_two_nuclides_can_share_a_cell():
    """**INJECTIVE BY CONSTRUCTION, and asserted rather than reasoned.**
    (Z, N) determines A, so the chart of the nuclides cannot overlap the
    way a general graph layout has to be made not to. Measured across
    200+ chains when the layout was chosen: zero collisions.
    """
    for symbol in ("U", "Th", "Pu", "Au", "Cs", "Po", "I"):
        for nuclide in N.nuclides_for(symbol)[:6]:
            diagram = render_decay_svg(decay_tree(nuclide))
            cells = {(n.x, n.y) for n in diagram.nodes}

            assert len(cells) == len(diagram.nodes), f"{nuclide.name} overlaps"


def test_alpha_decay_is_two_cells_down_and_two_left():
    """The shape carries the meaning, which is the whole reason for using
    the textbook axes rather than a layout algorithm."""
    chart = _chart(92, 238)
    parent, daughter = _node(chart, "U-238"), _node(chart, "Th-234")

    assert daughter.x == pytest.approx(parent.x - 2 * CELL_W)
    assert daughter.y == pytest.approx(parent.y + 2 * CELL_H)


def test_beta_minus_is_one_cell_up_and_one_left():
    chart = _chart(92, 238)
    parent, daughter = _node(chart, "Th-234"), _node(chart, "Pa-234")

    assert daughter.x == pytest.approx(parent.x - CELL_W)
    assert daughter.y == pytest.approx(parent.y - CELL_H)


def test_the_uranium_series_reaches_the_lead_every_textbook_names():
    chart = _chart(92, 238)

    assert {n.name for n in chart.nodes} >= {
        "U-238", "Th-234", "Pa-234", "U-234", "Th-230", "Ra-226",
        "Rn-222", "Po-218", "Pb-214", "Bi-214", "Po-214", "Pb-210",
        "Bi-210", "Po-210", "Pb-206",
    }


def test_the_root_and_the_stable_nuclides_are_marked():
    chart = _chart(92, 238)

    assert _node(chart, "U-238").is_root
    assert not _node(chart, "Th-234").is_root
    assert _node(chart, "Pb-206").is_stable
    assert not _node(chart, "Rn-222").is_stable


def test_a_click_lands_on_the_box_under_it():
    chart = _chart(92, 238)
    node = _node(chart, "Ra-226")

    assert chart.node_at(node.x + 2, node.y + 2) is node
    assert chart.node_at(node.x + node.width / 2, node.y + node.height / 2) is node
    assert chart.node_at(node.x - 8, node.y - 8) is None


# --- what a line's weight says ---------------------------------------------


def test_a_dominant_branch_is_drawn_more_heavily_than_a_rare_one():
    """**THE FIRST RENDER WAS UNREADABLE AND THIS IS WHY.** On the chart
    of the nuclides a cluster emission is an enormous jump -- uranium's
    32Si branch moves 14 protons and 18 neutrons at once -- so at uniform
    weight a handful of decays with branchings near 1e-10% drew lines
    across the whole width while the actual uranium series was a faint
    zigzag underneath them.
    """
    heavy, _opacity = edge_weight(100.0)
    faint, _opacity = edge_weight(1e-10)

    assert heavy > faint


def test_the_rendered_chart_really_uses_the_weights():
    """**TESTING `edge_weight` IS NOT TESTING THE PICTURE**, and a
    mutation replacing the call with a constant survived a file that
    checked the helper four different ways. What matters is that the
    drawn lines differ.

    U-238's own two extremes: alpha at 100% against the double beta-minus
    to Pu-238 at 2.2e-10%.
    """
    tree = decay_tree(N.nuclide(92, 238))
    chart = render_decay_svg(tree)

    widths = set()
    for line in chart.svg.split("<line ")[1:]:
        widths.add(line.split('stroke-width="')[1].split('"')[0])

    assert len(widths) > 1, "every line is the same weight"
    assert str(_n_like(edge_weight(100.0)[0])) in widths
    assert str(_n_like(edge_weight(2.2e-10)[0])) in widths


def _n_like(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def test_weight_is_monotonic_in_branching():
    weights = [edge_weight(b)[0] for b in (100.0, 10.0, 0.5, 1e-3, 1e-9)]

    assert weights == sorted(weights, reverse=True)


def test_an_unmeasured_branching_is_not_drawn_as_a_vanishing_one():
    """**`?` IS THE COMMONEST QUALIFIER IN NUBASE at 1,755 entries**, and
    it means "this mode is expected, nobody has measured how often". Drawn
    at the lightest weight it would read as "vanishingly rare", which is a
    number the source never gave.
    """
    assert edge_weight(None) == UNMEASURED_WEIGHT
    assert edge_weight(None)[0] > BRANCHING_WEIGHTS[-1][1]


def test_nothing_is_dropped_however_faint():
    """**NOT A THRESHOLD IN DISGUISE.** Alex chose the full branching tree
    over a thresholded one, so weighting must not become filtering: every
    followable edge in the graph is a line in the SVG.
    """
    tree = decay_tree(N.nuclide(92, 238))
    drawable = sum(1 for edges in tree.edges.values() for e in edges if e.to is not None)
    chart = render_decay_svg(tree)

    assert chart.svg.count("<line ") == drawable
    assert drawable > 40, "the fixture must have enough edges to be worth counting"


def test_the_faintest_uranium_branch_is_still_drawn():
    """U-238's double beta-minus to Pu-238 runs at 2.2e-10%, which is the
    kind of branch a threshold would quietly remove."""
    chart = _chart(92, 238)

    assert any(n.name == "Pu-238" for n in chart.nodes)


# --- families ---------------------------------------------------------------


def test_every_mode_in_the_table_has_a_colour():
    """**DERIVED FROM `delta_for`, so a new NUBASE mode is coloured
    without anybody editing a table.** A parallel string table keyed on
    the same 45 tokens is the rot this module's grammar exists to avoid.
    """
    modes = {d.mode for n in N._by_key().values() for d in n.decays}

    assert len(modes) >= 40, "the fixture should be the whole mode vocabulary"
    for mode in modes:
        assert mode_family(mode) in FAMILY_COLOUR, mode


@pytest.mark.parametrize(
    "mode,family",
    [
        ("A", "alpha"),
        ("B-", "beta_minus"),
        ("2B-", "beta_minus"),
        ("B+", "beta_plus"),
        ("EC", "beta_plus"),
        ("14C", "cluster"),
        ("28Mg", "cluster"),
        ("p", "other"),
        ("SF", "other"),
    ],
)
def test_the_families_are_what_a_reader_would_call_them(mode, family):
    assert mode_family(mode) == family


def test_the_legend_names_only_families_the_chart_actually_drew():
    """A legend advertising cluster emission on carbon-14's two-node chain
    invites the reader to hunt for something that is not there."""
    carbon = legend_lines(_chart(6, 14))
    uranium = legend_lines(_chart(92, 238))

    assert [words for _colour, words in carbon] == ["beta-"]
    assert len(uranium) > len(carbon)
    assert any("cluster" in words for _colour, words in uranium)


# --- what the source says, and where it says two things at once ------------


def test_a_leaf_says_why_it_is_one():
    """A chain that simply stops reads as a rendering bug.

    **URANIUM-238 CANNOT SHOW THIS, which is why the fixture is not the
    obvious one.** It has seven unfollowable SF branches -- but every node
    carrying one ALSO has a followable alpha, so none of them is a leaf
    and the annotation never fires. It takes a nuclide whose only route
    out is one that has no single daughter.

    Measured over the whole table: 8,038 stable leaves, 109 unfollowable
    and 17 off-table. Fm-259 fissions outright; Li-3 has a daughter no
    ground state in the table carries.
    """
    fissions = _chart(100, 259)
    off_table = _chart(3, 3)

    assert "fissions" in fissions.svg
    assert "not in table" in off_table.svg

    # The control: a chain that ends in something stable says neither.
    ordinary = _chart(92, 238)
    assert "fissions" not in ordinary.svg and "not in table" not in ordinary.svg


def test_four_of_the_uranium_chains_stable_nuclides_also_carry_a_decay():
    """**A REAL CONTRADICTION IN NUBASE, CARRIED FAITHFULLY.** Pb-204,
    Pb-206, Pb-208 and Hg-204 are marked `stbl` AND list a decay nobody
    has ever observed (`A ?`, `2B- ?`), so they are stable and have an
    outgoing edge at the same time.

    That is why the chart continues past lead into mercury, and why the
    status line reports which stable nuclides a chain REACHES rather than
    where it "ends" -- `leaves()` answers the second question and named
    Hg-200, Hg-202 and Tl-205 while omitting Pb-206, which is where every
    textbook says the uranium series stops.

    Asserted so a future NUBASE that resolves it fails here rather than
    silently changing every chart.
    """
    tree = decay_tree(N.nuclide(92, 238))
    both = {
        node.name
        for key, node in tree.nodes.items()
        if node.is_stable and any(e.to is not None for e in tree.edges.get(key, []))
    }

    assert both == {"Pb-204", "Pb-206", "Pb-208", "Hg-204"}
    assert "Pb-206" not in {tree.nodes[k].name for k in tree.leaves()}


def test_a_two_node_chain_still_renders():
    """Carbon-14 is the ordinary case and the smallest one."""
    chart = _chart(6, 14)

    assert {n.name for n in chart.nodes} == {"C-14", "N-14"}
    assert chart.width > 0 and chart.height > 0
